"""Constants for the Sunrise Alarm integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "sunrise_alarm"
PLATFORMS: Final = ["binary_sensor", "button", "sensor", "switch"]

# Config / options keys ------------------------------------------------------
CONF_PERSON: Final = "person"
CONF_LIGHT: Final = "light"
CONF_SPEAKER: Final = "speaker"
CONF_NOTIFY: Final = "notify"
CONF_ALARM_SENSOR: Final = "alarm_sensor"
CONF_LEAD_MIN: Final = "lead_min"
CONF_RAMP_MIN: Final = "ramp_min"
CONF_BRIGHTNESS_MAX: Final = "brightness_max"
CONF_KELVIN_START: Final = "kelvin_start"
CONF_KELVIN_END: Final = "kelvin_end"
CONF_AUDIO: Final = "audio"
CONF_AUDIO_TYPE: Final = "audio_type"
CONF_AUDIO_DELAY_MIN: Final = "audio_delay_min"
CONF_VOLUME_MAX: Final = "volume_max"
CONF_SNOOZE_MIN: Final = "snooze_min"
CONF_SNOOZE_MAX: Final = "snooze_max"
CONF_CLOCK_PACKAGES: Final = "clock_packages"
CONF_WINDOW_START: Final = "window_start"
CONF_WINDOW_END: Final = "window_end"

# Defaults -------------------------------------------------------------------
DEFAULT_LEAD_MIN: Final = 30
DEFAULT_RAMP_MIN: Final = 30
DEFAULT_BRIGHTNESS_MAX: Final = 100
DEFAULT_KELVIN_START: Final = 2000
DEFAULT_KELVIN_END: Final = 6500
DEFAULT_AUDIO_TYPE: Final = "music"
DEFAULT_AUDIO_DELAY_MIN: Final = 10
DEFAULT_VOLUME_MAX: Final = 0.5
DEFAULT_SNOOZE_MIN: Final = 9
DEFAULT_SNOOZE_MAX: Final = 3
CONF_SNOOZE_FADE_SEC: Final = "snooze_fade_sec"
CONF_REQUIRE_HOME: Final = "require_home"
DEFAULT_REQUIRE_HOME: Final = True
# Auto-dismiss when the person is clearly up and about (Companion sensors).
CONF_AWAKE_STOP: Final = "awake_stop"
DEFAULT_AWAKE_STOP: Final = False
CONF_AWAKE_LOCKED: Final = "awake_locked_sensor"
CONF_AWAKE_INTERACTIVE: Final = "awake_interactive_sensor"
CONF_AWAKE_CHARGING: Final = "awake_charging_sensor"
CONF_AWAKE_STEPS: Final = "awake_steps_sensor"
CONF_AWAKE_ACTIVITY: Final = "awake_activity_sensor"
CONF_AWAKE_DEBOUNCE_SEC: Final = "awake_debounce_sec"
DEFAULT_AWAKE_DEBOUNCE_SEC: Final = 30
# Steps must climb by at least this much since the run started to count as moving.
AWAKE_STEP_DELTA: Final = 5
AWAKE_MOVING: Final = ("walking", "running", "on_foot")
DEFAULT_SNOOZE_FADE_SEC: Final = 45
DEFAULT_WINDOW_START: Final = "03:00"
DEFAULT_WINDOW_END: Final = "11:00"

# Android clock apps whose alarms are treated as genuine wake alarms.
# Everything else (calendar reminders, Samsung Routines, timers) is ignored.
DEFAULT_CLOCK_PACKAGES: Final = [
    "com.google.android.deskclock",
    "com.sec.android.app.clockpackage",
]

# Ramp granularity (seconds between steps).
STEP_SECONDS: Final = 20
# Shortest ramp used when the alarm surfaces inside the lead window and the
# routine has to start late (see _maybe_late_start).
MIN_LATE_RAMP_MIN: Final = 1

# Dispatcher signal used to notify entities of a controller state change.
SIGNAL_UPDATE: Final = "sunrise_alarm_update_{entry_id}"

# Service names.
SERVICE_START: Final = "start"
SERVICE_SNOOZE: Final = "snooze"
SERVICE_DISMISS: Final = "dismiss"
SERVICE_STOP: Final = "stop"
SERVICE_STOP_TODAY: Final = "stop_today"

# ----- Phase 2: notifications -----------------------------------------------
CONF_PREALARM_LEAD_SEC: Final = "prealarm_lead_sec"
CONF_DASHBOARD: Final = "dashboard_path"
DEFAULT_PREALARM_LEAD_SEC: Final = 60
DEFAULT_DASHBOARD: Final = ""

# Companion notification-action event and the action ids we register (suffixed
# with the entry_id so each profile's buttons are unambiguous).
EVENT_NOTIFICATION_ACTION: Final = "mobile_app_notification_action"
ACTION_SNOOZE: Final = "SUNRISE_SNOOZE"
ACTION_DISMISS: Final = "SUNRISE_DISMISS"
ACTION_CANCEL: Final = "SUNRISE_CANCEL"
# Two-level notification menu (Android allows three buttons per notification).
ACTION_MORE: Final = "SUNRISE_MORE"
ACTION_STOP_ASK: Final = "SUNRISE_STOP_ASK"
ACTION_STOP_CONFIRM: Final = "SUNRISE_STOP_CONFIRM"
ACTION_KEEP: Final = "SUNRISE_KEEP"
ACTION_SNOOZE_FOR: Final = "SUNRISE_SNOOZE_FOR"  # + _<minutes>_<entry_id>
SNOOZE_CHOICES: Final = (10, 20, 30)
# The stop confirmation clears itself after this long and does nothing.
STOP_CONFIRM_TIMEOUT_SEC: Final = 60
NOTIFY_TAG: Final = "sunrise_alarm_{entry_id}"

# ----- Phase 3: phone-side integration --------------------------------------
# Companion sensors (per profile). Optional; the phone-side features only
# activate for whichever ones are configured.
CONF_DND_SENSOR: Final = "dnd_sensor"
CONF_ALARM_VOL_SENSOR: Final = "alarm_vol_sensor"
CONF_LAST_NOTIF_SENSOR: Final = "last_notification_sensor"
CONF_LAST_REMOVED_SENSOR: Final = "last_removed_notification_sensor"
CONF_PHONE_STATE_SENSOR: Final = "phone_state_sensor"

CONF_PREMUTE_SEC: Final = "premute_sec"
CONF_ESCALATE: Final = "escalate"
CONF_FAILSAFE_EXTRA_MIN: Final = "failsafe_extra_min"
CONF_MUTE_HOLD_RETRIES: Final = "mute_hold_retries"
CONF_MUTE_HOLD_INTERVAL_SEC: Final = "mute_hold_interval_sec"
CONF_FIRING_CHANNEL: Final = "firing_channel"
CONF_SNOOZED_CHANNEL: Final = "snoozed_channel"
CONF_FIRING_PACKAGE: Final = "firing_package"

DEFAULT_PREMUTE_SEC: Final = 90
DEFAULT_ESCALATE: Final = True
DEFAULT_FAILSAFE_EXTRA_MIN: Final = 5
DEFAULT_MUTE_HOLD_RETRIES: Final = 8
DEFAULT_MUTE_HOLD_INTERVAL_SEC: Final = 13
DEFAULT_FIRING_CHANNEL: Final = "Firing"
DEFAULT_SNOOZED_CHANNEL: Final = "Snoozed Alarms v2"
DEFAULT_FIRING_PACKAGE: Final = "com.google.android.deskclock"

# Companion `command_*` notify payloads.
CMD_DND: Final = "command_dnd"
CMD_VOLUME: Final = "command_volume_level"
DND_TOTAL_SILENCE: Final = "total_silence"
DND_VALID: Final = ("off", "priority_only", "alarm_only", "total_silence")
ALARM_STREAM: Final = "alarm_stream"

# Persisted runtime state (so a restart never leaves the phone muted).
STORAGE_VERSION: Final = 1
STORAGE_KEY: Final = "sunrise_alarm.{entry_id}"
