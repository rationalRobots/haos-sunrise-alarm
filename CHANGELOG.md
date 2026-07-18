# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/) and this project adheres to
[Semantic Versioning](https://semver.org/).

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
