"""The Sunrise Alarm integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ALARM_SENSOR,
    CONF_AWAKE_ACTIVITY,
    CONF_AWAKE_CHARGING,
    CONF_AWAKE_INTERACTIVE,
    CONF_AWAKE_LOCKED,
    CONF_AWAKE_STEPS,
    CONF_AWAKE_STOP,
    CONF_DND_SENSOR,
    CONF_PHONE_STATE_SENSOR,
    DOMAIN,
    PLATFORMS,
    SERVICE_DISMISS,
    SERVICE_SNOOZE,
    SERVICE_START,
    SERVICE_STOP,
    SERVICE_STOP_TODAY,
)
from .coordinator import SunriseAlarmController

_SERVICE_SCHEMA = vol.Schema({vol.Required("entry_id"): cv.string})


# Companion suffix per awake config key; the phone's entity slug is shared
# across all its sensors, so we can derive these from any wired companion
# sensor without touching the registry's device graph.
_AWAKE_DERIVE: dict[str, tuple[str, str]] = {
    CONF_AWAKE_LOCKED: ("binary_sensor", "device_locked"),
    CONF_AWAKE_INTERACTIVE: ("binary_sensor", "interactive"),
    CONF_AWAKE_CHARGING: ("binary_sensor", "is_charging"),
    CONF_AWAKE_STEPS: ("sensor", "daily_steps"),
    CONF_AWAKE_ACTIVITY: ("sensor", "detected_activity"),
}
# Known companion sensors we can read the phone's entity slug from.
_SLUG_FROM = {
    CONF_ALARM_SENSOR: "_next_alarm",
    CONF_PHONE_STATE_SENSOR: "_phone_state",
    CONF_DND_SENSOR: "_do_not_disturb_sensor",
}


def _phone_slug(data: dict) -> str | None:
    """Recover the phone's entity slug (e.g. 's24u') from a wired sensor."""
    for key, suffix in _SLUG_FROM.items():
        eid = data.get(key)
        if eid and "." in eid:
            obj = eid.split(".", 1)[1]
            if obj.endswith(suffix):
                return obj[: -len(suffix)]
    return None


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """v1 -> v2: wire the awake-detection sensors and turn the feature on.

    0.7.0 added "stop when I'm up". Existing profiles have none of the awake
    sensors in their config, so this derives them from the phone slug already
    present, verifies each exists, and enables awake_stop. The feature fails
    closed, so any sensor it can't resolve simply leaves that profile's
    detection partial rather than misfiring.
    """
    if entry.version > 2:
        # Written by a newer version; this code can't safely downgrade it.
        return False
    if entry.version == 2:
        return True
    options = dict(entry.options)
    slug = _phone_slug({**entry.data, **options})
    if slug:
        reg = er.async_get(hass)
        for key, (domain, suffix) in _AWAKE_DERIVE.items():
            if key in options or key in entry.data:
                continue
            candidate = f"{domain}.{slug}_{suffix}"
            if reg.async_get(candidate):
                options[key] = candidate
    options.setdefault(CONF_AWAKE_STOP, True)
    hass.config_entries.async_update_entry(entry, options=options, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Sunrise Alarm profile from a config entry."""
    controller = SunriseAlarmController(hass, entry)
    await controller.async_setup()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    _async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        controller: SunriseAlarmController = hass.data[DOMAIN].pop(entry.entry_id)
        await controller.async_unload()
        if not hass.data[DOMAIN]:
            _async_remove_services(hass)
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register the domain services once."""
    if hass.services.has_service(DOMAIN, SERVICE_START):
        return

    def _controller(call: ServiceCall) -> SunriseAlarmController:
        entry_id = call.data["entry_id"]
        controllers = hass.data.get(DOMAIN, {})
        if entry_id not in controllers:
            raise ValueError(f"Unknown Sunrise Alarm entry_id: {entry_id}")
        return controllers[entry_id]

    async def _start(call: ServiceCall) -> None:
        await _controller(call).async_start_run()

    async def _snooze(call: ServiceCall) -> None:
        await _controller(call).async_snooze()

    async def _dismiss(call: ServiceCall) -> None:
        await _controller(call).async_dismiss()

    async def _stop(call: ServiceCall) -> None:
        await _controller(call).async_stop()

    async def _stop_today(call: ServiceCall) -> None:
        await _controller(call).async_stop_today()

    hass.services.async_register(DOMAIN, SERVICE_START, _start, schema=_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SNOOZE, _snooze, schema=_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISMISS, _dismiss, schema=_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP, _stop, schema=_SERVICE_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_STOP_TODAY, _stop_today, schema=_SERVICE_SCHEMA
    )


def _async_remove_services(hass: HomeAssistant) -> None:
    for service in (
        SERVICE_START,
        SERVICE_SNOOZE,
        SERVICE_DISMISS,
        SERVICE_STOP,
        SERVICE_STOP_TODAY,
    ):
        hass.services.async_remove(DOMAIN, service)
