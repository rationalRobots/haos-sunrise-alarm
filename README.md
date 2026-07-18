# Sunrise Alarm for Home Assistant

A gentle, per-person **sunrise wake** integration. Some minutes before your phone
alarm, your bedside lamp fades up from almost-off and warm to bright, cool
daylight — and, optionally, a speaker fades in radio or music. Snooze and dismiss
from a button, a voice assistant, or a service call.

Everything is configured from the UI. Add one **profile** per sleeper; each drives
its own lamp and timings and can share a speaker.

> Status: 0.1.0 preview. See [known limitations](#limitations).

## Why another wake-light?

The routine only fires for a **genuine clock-app alarm inside your morning
window**. The Home Assistant Companion app's `next_alarm` sensor also surfaces
calendar reminders, Samsung Routines and timers — a common cause of false
sunrises. Sunrise Alarm gates on the alarm's source package **and** its
time-of-day before it will arm, so a 3 p.m. calendar reminder can't start your
bedroom lighting up.

## Requirements

- Home Assistant 2024.4 or newer.
- A `light` entity that supports colour temperature (brightness-only lamps work
  too — the colour steps are simply ignored by such lamps).
- Optional: a `media_player` for audio, a `notify` service for phone
  notifications, and the Companion app **Next alarm** sensor
  (`sensor.<device>_next_alarm`) so the routine can read your phone's alarm.

See [`docs/setup-companion-app.md`](docs/setup-companion-app.md) for the phone
side.

## Install (HACS)

1. HACS → three-dot menu → **Custom repositories**.
2. Add `https://github.com/rationalRobots/haos-sunrise-alarm` as an
   **Integration**.
3. Install **Sunrise Alarm**, then restart Home Assistant.
4. Settings → Devices & Services → **Add Integration** → *Sunrise Alarm*.

Manual install: copy `custom_components/sunrise_alarm/` into your HA
`config/custom_components/` and restart.

## Configure

Adding the integration creates one **profile**. Pick the lamp, and optionally the
speaker, notify service and the phone's Next-alarm sensor. Add the integration
again for each additional person.

Per-profile timings live under the profile's **Configure** (options): lead time,
sunrise duration, max brightness, start/end colour temperature, audio media id
and type, audio delay, max volume, snooze duration and cap, and the morning
window that gates which alarms count.

Each profile exposes: an **Enabled** switch, an **Active** binary sensor, an
**Effective alarm** and **Routine starts** timestamp sensor, and **Snooze /
Dismiss / Stop** buttons. See [`examples/dashboard-card.yaml`](examples/dashboard-card.yaml).

## Services

| Service | Effect |
|---|---|
| `sunrise_alarm.start` | Start the routine now for a profile. |
| `sunrise_alarm.snooze` | Snooze; re-runs a short sunrise, auto-dismisses at the cap. |
| `sunrise_alarm.dismiss` | Stop the routine, leave the lamp on, stop audio. |
| `sunrise_alarm.stop` | Hard stop; lamp off, audio off. |

Each takes `entry_id` (the profile's config-entry id). Point a voice-assistant
routine or automation at these to snooze/dismiss by voice or speaker.

## Limitations

- **HA cannot snooze/dismiss the phone's OS alarm.** The `next_alarm` sensor is
  read-only and Android blocks the Companion app from firing alarm intents in the
  background. Run the routine early enough to dismiss the phone alarm yourself, or
  treat HA as the alarm and keep the phone as a backstop.
- **Masking:** the sensor holds only the single soonest alarm, so a non-clock
  alarm scheduled *inside* the lead window in front of the real one can hide it.
  Rare, but real.
- **Phone muting / DND control** (silencing the phone as the wake takes over) is
  device-specific and not part of 0.1.0.

Details in [`docs/limitations.md`](docs/limitations.md).

## Roadmap

- Phone-side mute / DND handoff (opt-in, per-device).
- Post-dismiss briefing (time / weather) with a house-wide speech volume.
- Blueprint export for users who prefer automations over an integration.

## License

MIT — see [LICENSE](LICENSE).
