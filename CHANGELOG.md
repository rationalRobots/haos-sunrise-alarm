# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.5.0] - 2026-07-18

### Added (person-centric setup)
- Setup now starts by **picking a person**. Their phone's **notify service** and
  Companion **sensors** (next alarm, DND, alarm volume, last/removed notification,
  phone state) are inferred from the person's `mobile_app` device — wiring the
  entire phone-side layer in one step. Falls back to a manual notify/alarm-sensor
  step when a person has no Companion device.

## [0.4.0] - 2026-07-18

### Added (phone-side layer)
- **Pre-mute + hold-retry**: mutes the phone `premute_sec` before the alarm and
  keeps re-sending the mute across the window (the Companion command channel is
  unreliable).
- **DND override with snapshot/restore**: records the phone's prior DND mode and
  alarm-stream volume before muting, and restores them exactly afterwards. State
  is **persisted**, so a restart never leaves the phone silenced (restore on load).
- **Phone-firing mirror**: the phone's own alarm firing mutes the phone + watch and
  (optionally) escalates the HA wake (lamp 100% + audio max).
- **Phone snooze mirror**: a phone snooze restores the phone and snoozes HA.
- **Phone dismiss mirror**: dismissing on the phone stops the HA routine.
- **Failsafe un-mute**: if still muted `snooze + failsafe_extra_min` after the alarm,
  the phone is un-muted as a hard backstop.
- **Call-through**: an incoming call during the override releases it if DND was off.
- **DND-override binary sensor** for dashboards.

## [0.3.0] - 2026-07-18

### Added (notification parity)
- **1-minute pre-alarm heads-up** with actionable **Snooze / Cancel** (configurable
  `prealarm_lead_sec`).
- **Actionable wake notification** with **Snooze / Dismiss** buttons.
- **Deep-link**: tapping a notification opens a configurable dashboard path
  (`dashboard_path`).
- **Notification-action handler**: the Companion `mobile_app_notification_action`
  events route back to snooze / dismiss / cancel, scoped per profile by entry id.

## [0.2.0] - 2026-07-18

### Added
- Options flow now edits the **lamp, speaker, notify service and next-alarm sensor**
  too, not just timings — so a profile created without a notify target (silent
  wake notification) can be fixed without re-adding it.

### Fixed
- (Carried from 0.1.2, unreleased) Options flow 400 on HA 2026.7.

## [0.1.2] - 2026-07-18

### Fixed
- Options flow returned "400: Bad Request" on Home Assistant 2026.7. Reworked it
  to the current docs pattern: a static schema with `add_suggested_values_to_schema`
  instead of schema-embedded defaults, and `NumberSelector` no longer passes
  `unit_of_measurement=None` for unit-less numbers.

## [0.1.1] - 2026-07-18

### Fixed
- Import `DeviceInfo` from `homeassistant.helpers.device_registry` (the previous
  `homeassistant.helpers.device_info` module does not exist and broke setup on
  current Home Assistant).
- Simplified `hacs.json` (dropped `content_in_root`).

### Added
- Auto-release workflow: bumping `version` in the manifest and pushing to `main`
  cuts a matching GitHub Release so HACS offers the update.

## [0.1.0] - 2026-07-18

Initial public preview.

### Added
- Config-flow setup: add one wake **profile** per person (lamp, optional speaker,
  optional notify service, optional phone "Next alarm" sensor).
- Source-gated alarm resolution: the routine only arms for alarms from an allowed
  clock app **and** inside a configurable morning window, so calendar reminders,
  Samsung Routines and timers can no longer trigger a false sunrise.
- Sunrise engine: lamp fades from ~1 % / warm (2000 K) to max brightness / cool
  (6500 K); optional speaker audio fades in after a delay.
- Snooze / dismiss / stop via buttons or services; snooze re-runs a short sunrise
  and auto-dismisses after the configured attempt cap.
- Entities per profile: enable switch, active binary sensor, effective-alarm and
  start-time timestamp sensors, and snooze/dismiss/stop buttons.

### Known limitations
- Home Assistant cannot snooze or dismiss the phone's own OS alarm (the Companion
  `next_alarm` sensor is read-only). Run early enough to dismiss on the phone, or
  treat HA as the alarm and keep the phone as a backstop.
- Phone-side muting / DND control is device-specific and out of scope for 0.1.0.
