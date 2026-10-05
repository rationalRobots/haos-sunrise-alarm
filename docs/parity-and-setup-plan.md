# Parity gap analysis + person-centric setup proposal

Status of the `sunrise_alarm` integration (v0.1.2) vs the original homelab YAML
`wakeup_*` package. **Planning document — nothing here is built yet.**

Legend: ✅ present · 🟡 partial · ❌ missing.

## 1. Parity gap table

### Core sunrise

| Feature (old YAML) | New integration | Notes / what porting needs |
|---|---|---|
| Light ramp, warm→cool + dim→bright | ✅ | `kelvin_start→kelvin_end`, brightness 1→max over `ramp_min`. |
| Audio fade-in (radio/music) after delay | ✅ | Audio branch: `play_media` at vol 0, ramp to `volume_max`. |
| Configurable ramp/lead/brightness/volume/kelvin | 🟡 | Values exist as options, but the **options flow is 400-broken on HA 2026.7** (fix pending in 0.1.2) and doesn't cover notify/light/speaker. |

### Alarm sourcing

| Feature | New | Notes |
|---|---|---|
| Read phone `next_alarm` | ✅ | Per-profile `alarm_sensor`. |
| Source gate (clock-app package allowlist) | ✅ | In `_resolve_alarm()` — the key fix that stops calendar/Routine false-fires. |
| Morning-window gate | ✅ | `window_start/end`. |
| Once-per-day guard | ✅ | `_last_run_date`, persisted in the profile's store since 0.5.1 (survives a restart). |
| Manual mode (dashboard time instead of phone) | ❌ | No manual time input; integration only reads `alarm_sensor`. |

### Controls

| Feature | New | Notes |
|---|---|---|
| Snooze (button + service) | ✅ | Re-runs a short 2-min sunrise. |
| Dismiss (button + service) | ✅ | Lamp to 100%, audio stop. |
| Snooze cap → auto-dismiss | ✅ | `snooze_max`. |
| No-stack guard (don't start if active/ran today) | ✅ | Checks `active` + last-run date. |
| Cancel / stop-everything | 🟡 | Per-profile `stop` button/service only; **no global cancel**. |
| Master kill switch (off stops a *running* routine) | ❌ | Per-profile `enable` switch exists, but turning it off only affects scheduling, not an in-flight ramp. |
| Test mode (bypass window + once-per-day) | 🟡 | `start` service bypasses everything; no persistent test toggle. |
| Snooze-count tracking | 🟡 | Internal counter, surfaced as an attribute on the active sensor (no dedicated entity). |

### Notifications

| Feature | New | Notes |
|---|---|---|
| Wake notification | 🟡 | Sends title/message **only if `notify` is set** (optional field; the live profile had it blank → silent). |
| Actionable Snooze/Dismiss buttons on the notification | ❌ | `_notify()` sends no `actions`. |
| Deep-link `clickAction` to a dashboard | ❌ | Not sent. |
| 1-minute pre-alarm heads-up (actionable Snooze/Cancel) | ❌ | No pre-alarm concept in the integration. |
| Notification-action handler (`mobile_app_notification_action`) | ❌ | No event listener, so notification buttons wouldn't route back. |
| Robust notify target | 🟡 | Manual, optional, easy to leave blank. Addressed by the person-centric design below. |

### Phone-side integration (all ❌ — none ported)

| Feature | New | Notes |
|---|---|---|
| Pre-mute before alarm (+ hold-mute retry loop) | ❌ | |
| Phone firing → mute phone + watch, escalate | ❌ | |
| Escalation (lamp 100% + audio max when still asleep) | ❌ | |
| Phone snooze mirror | ❌ | |
| Phone dismiss mirror | ❌ | |
| Failsafe unmute (phone as hard backstop) | ❌ | |
| DND override (`total_silence` + alarm-vol snapshot/restore) | ❌ | |
| DND watchdog (never leave phone muted) | ❌ | |
| Call-through (release DND when a call arrives) | ❌ | |

### Extra UX

| Feature | New | Notes |
|---|---|---|
| Per-person profiles | ✅ | One config entry per person. |
| Speaker-pause = snooze | ❌ | No listener on the speaker's `playing→paused`. |
| Briefing on dismiss (TTS time/weather) | ❌ | Dismiss sends no TTS. |
| Dashboard control surface | 🟡 | Entities exist; only an example Lovelace card, no bundled panel. |

**Summary:** the *sunrise mechanics* (light + audio ramp, source-gated scheduling,
snooze/dismiss) are at parity or close. The **entire phone-side layer** (mute/DND,
mirrors, failsafe, escalate, pre-mute), the **notification layer** (actionable +
pre-alarm + action routing + deep-link), **manual mode**, **global master/cancel**,
**briefing**, and **speaker-pause snooze** are not yet ported.

## 2. Proposed person-centric setup

### Goal

Replace "pick a light, a speaker, and manually type a notify service" with:
**pick the person → the integration infers their phone, notify service and companion
sensors → you then set lamp, speaker, timings and audio.**

### How Home Assistant lets you infer notify-from-person

The chain, all available to a config flow via the registries:

1. **Person → trackers.** `person.<name>` exposes a `device_trackers` attribute — a
   list of `device_tracker.*` entity ids (plus `user_id`, `source`).
2. **Tracker → device.** For each tracker, the **entity registry**
   (`entity_registry.async_get(hass).async_get(entity_id)`) gives `.platform`
   (`"mobile_app"` for the Companion app) and `.device_id`. Filter to
   `platform == "mobile_app"` to drop router/GPS trackers.
3. **Device → registration.** The **device registry**
   (`device_registry.async_get(hass).async_get(device_id)`) gives the device, its
   `config_entries`, `name`, `model`, and the `("mobile_app", <id>)` identifier.
4. **Device → notify service.** The Companion app registers
   `notify.mobile_app_<slug>` where `<slug> = slugify(device_name)`. Resolve it by
   listing `notify` services and matching the slug against the device name (then let
   the user confirm the pre-selected one).
5. **Device → companion sensors, for free.** Every other Companion entity for that
   person's phone shares the same `device_id`: `sensor.<dev>_next_alarm`,
   `..._do_not_disturb_sensor`, `..._phone_state`, `..._volume_level_alarm`, etc.
   So picking the person auto-wires the alarm source **and** everything the future
   phone-side features (mute/DND/mirrors/call-through) will need — in one step.

### Proposed flow

- **Step 1 — Person.** `EntitySelector(domain="person")` (+ optional display-name
  override). Also offer a "no person / manual" escape hatch.
- **Step 2 — Phone (auto-resolved, confirm).** Resolve the person's mobile_app
  device(s); pre-select the phone. Show, editable: **notify target**, and the
  auto-detected **next-alarm / DND / phone-state** sensors. Optionally a second
  **watch** device (for `total_silence` muting later).
- **Step 3 — Devices.** Default **lamp** (`light` selector; can suggest a light in
  the person's area) and default **speaker** (`media_player` selector).
- **Step 4 — Timings.** Wake window start/end, ramp duration, pre-alarm lead,
  snooze duration/cap, max brightness, start/end colour temperature, max volume.
- **Step 5 — Audio.** Radio/audio `media_content_id` + type (music/playlist/tts).

Options flow mirrors steps 3–5 (all editable) plus a **"re-detect phone"** action
that re-runs step 2 if the device or notify slug changes.

**Data model:** store `person`, resolved `device_id`, `notify`, and the sensor ids
in `entry.data`; put timings/audio/window in `entry.options` (editable). Re-resolve
on demand rather than caching forever.

### Limitations / edge cases

- **Multiple trackers per person** (phone + watch + router/GPS). Must filter to
  `platform == "mobile_app"`; if several mobile devices, present a choice
  (distinguish phone vs watch by `next_alarm`-sensor presence or device model).
- **No clean "device → notify service" API.** The slug derivation is best-effort;
  always show the resolved target pre-selected for the user to confirm/override.
- **Person with no mobile_app device** (router/GPS only) → can't infer notify or
  next-alarm; fall back to manual notify + manual-mode alarm time.
- **No Persons configured at all** → the "manual" path picks notify + sensors
  directly (today's behaviour, kept as a fallback).
- **Selector help:** `EntitySelectorConfig(integration="mobile_app")` can narrow the
  phone-sensor pickers; a `DeviceSelector` filtered to `mobile_app` is a cleaner
  alternative to person→device if the person route is ambiguous.
- HA has **no built-in person→notify helper** — this resolution is custom async code
  in the config flow using the entity/device registries.

## 3. Suggested build order (for discussion)

1. **Fix + finish the flow** (0.1.2 options-flow fix) and make `notify` editable —
   unblocks the immediate "no popup" problem.
2. **Notification parity:** actionable wake + 1-min pre-alarm, action-event handler,
   deep-link; global master/cancel; persist once-per-day; manual mode; briefing.
3. **Phone-side layer:** pre-mute/hold, DND override + snapshot/restore + watchdog,
   phone firing/snooze/dismiss mirrors, failsafe, call-through, escalate,
   speaker-pause snooze.
4. **Person-centric setup + auto-inference** and a bundled dashboard.
