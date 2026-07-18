"""The Sunrise Alarm integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    PLATFORMS,
    SERVICE_DISMISS,
    SERVICE_SNOOZE,
    SERVICE_START,
    SERVICE_STOP,
)
from .coordinator import SunriseAlarmController

_SERVICE_SCHEMA = vol.Schema({vol.Required("entry_id"): cv.string})


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

    hass.services.async_register(DOMAIN, SERVICE_START, _start, schema=_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SNOOZE, _snooze, schema=_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DISMISS, _dismiss, schema=_SERVICE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_STOP, _stop, schema=_SERVICE_SCHEMA)


def _async_remove_services(hass: HomeAssistant) -> None:
    for service in (SERVICE_START, SERVICE_SNOOZE, SERVICE_DISMISS, SERVICE_STOP):
        hass.services.async_remove(DOMAIN, service)
