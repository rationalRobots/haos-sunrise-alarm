# Limitations and design notes

## The phone's OS alarm is read-only
The Companion app exposes the next alarm as a read-only sensor and offers no
snooze/dismiss service for the system clock. Android also blocks the app from
starting alarm activities (`SET_ALARM` / `SNOOZE_ALARM` / `DISMISS_ALARM`) from
the background, so Home Assistant cannot programmatically change the phone's
alarm. The integration's snooze/dismiss therefore control the HA routine (lamp +
speaker), not the phone. Practical options: run early enough to dismiss the phone
alarm before it sounds, or rely on the lamp/speaker and keep the phone alarm as a
backstop.

## Single-alarm masking
`next_alarm` only ever holds the single soonest alarm from any app. A non-clock
alarm (calendar/Routine) scheduled inside the lead window, in front of the real
wake alarm, hides the real one during the minutes the routine needed to arm.
No amount of source-gating removes this, and in practice a weekday Routine
can sit exactly there every morning. Since 0.5.1 the routine copes: when the
real alarm surfaces with the start already in the past, it starts at once with
the ramp shortened to the time left, and logs a warning. The lamp still reaches
full brightness at the alarm; you just get a shorter sunrise. The fix on the
phone side is to move the masking Routine or calendar alert out of the
`[alarm - lead, alarm)` window.

## Colour temperature
The sunrise ramps `color_temp_kelvin` from the configured start to end. If a lamp
is brightness-only, the colour steps are ignored and only brightness ramps.

## Phone muting / DND
Silencing the phone/watch as the HA wake takes over is device- and
OEM-specific (DND modes, alarm-stream volume, notification channels) and is
intentionally out of scope for 0.1.0. It is on the roadmap as an opt-in,
per-device feature.
