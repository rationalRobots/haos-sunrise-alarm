"""Constants for the Sunrise Alarm integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "sunrise_alarm"
PLATFORMS: Final = ["binary_sensor", "button", "sensor", "switch"]

# Config / options keys ------------------------------------------------------
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

# Dispatcher signal used to notify entities of a controller state change.
SIGNAL_UPDATE: Final = "sunrise_alarm_update_{entry_id}"

# Service names.
SERVICE_START: Final = "start"
SERVICE_SNOOZE: Final = "snooze"
SERVICE_DISMISS: Final = "dismiss"
SERVICE_STOP: Final = "stop"
