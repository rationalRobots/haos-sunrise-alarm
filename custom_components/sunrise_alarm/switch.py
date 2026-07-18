"""Switch: enable/disable the profile."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SunriseAlarmEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the enable switch."""
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([SunriseEnableSwitch(controller, entry)])


class SunriseEnableSwitch(SunriseAlarmEntity, SwitchEntity):
    """Master enable for this wake profile."""

    _attr_translation_key = "enabled"
    _attr_icon = "mdi:weather-sunset-up"

    def __init__(self, controller, entry) -> None:
        super().__init__(controller, entry)
        self._attr_unique_id = f"{entry.entry_id}_enabled"

    @property
    def is_on(self) -> bool:
        return self._controller.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._controller.set_enabled(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._controller.set_enabled(False)
        self.async_write_ha_state()
