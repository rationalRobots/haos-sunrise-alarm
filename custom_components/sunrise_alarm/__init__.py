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


# Awake config key -> (domain, Companion entity suffix) on the phone's device.
_AWAKE_DERIVE: dict[str, tuple[str, str]] = {
    CONF_AWAKE_LOCKED: ("binary_sensor", "device_locked"),
    CONF_AWAKE_INTERACTIVE: ("binary_sensor", "interactive"),
    CONF_AWAKE_CHARGING: ("binary_sensor", "is_charging"),
    CONF_AWAKE_STEPS: ("sensor", "daily_steps"),
    CONF_AWAKE_ACTIVITY: ("sensor", "detected_activity"),
}
# Already-wired companion sensors whose registry entry names the phone device.
_DEVICE_SOURCE_KEYS = (CONF_ALARM_SENSOR, CONF_PHONE_STATE_SENSOR, CONF_DND_SENSOR)


def _phone_device_id(reg, data: dict) -> str | None:
    """The device_id of the phone, via a companion sensor already on the profile."""
    for key in _DEVICE_SOURCE_KEYS:
        eid = data.get(key)
        if not eid:
            continue
        ent = reg.async_get(eid)
        if ent and ent.device_id:
            return ent.device_id
    return None


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """v1 -> v2: wire the awake-detection sensors and turn the feature on.

    0.7.0 added "stop when I'm up"; profiles created earlier have none of the
    awake sensors configured. This finds the phone's device from a companion
    sensor already on the profile and discovers the awake sensors *on that
    device* (not by name-guessing, which renames would break), then enables
    awake_stop. The feature fails closed, so any sensor it can't resolve just
    leaves detection partial rather than misfiring on another device.
    """
    if entry.version > 2:
        # Written by a newer version; this code can't safely downgrade it.
        return False
    if entry.version == 2:
        return True
    options = dict(entry.options)
    reg = er.async_get(hass)
    device_id = _phone_device_id(reg, {**entry.data, **options})
    if device_id:
        on_device = er.async_entries_for_device(
            reg, device_id, include_disabled_entities=True
        )
        for key, (domain, suffix) in _AWAKE_DERIVE.items():
            if key in options or key in entry.data:
                continue
            match = next(
                (
                    e.entity_id
                    for e in on_device
                    if e.entity_id.startswith(f"{domain}.")
                    and e.entity_id.endswith(f"_{suffix}")
                ),
                None,
            )
            if match:
                options[key] = match
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
