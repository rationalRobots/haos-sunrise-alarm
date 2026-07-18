"""Shared base entity for Sunrise Alarm."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, SIGNAL_UPDATE
from .coordinator import SunriseAlarmController


class SunriseAlarmEntity(Entity):
    """Base entity wired to a controller and its update signal."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, controller: SunriseAlarmController, entry: ConfigEntry) -> None:
        """Initialise the base entity."""
        self._controller = controller
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Sunrise Alarm",
            model="Wake profile",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to controller updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE.format(entry_id=self._entry.entry_id),
                self.async_write_ha_state,
            )
        )
