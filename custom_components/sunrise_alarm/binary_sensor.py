"""Binary sensor: whether the wake routine is currently active."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SunriseAlarmEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the active + DND-override binary sensors."""
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SunriseActiveSensor(controller, entry),
            SunriseDndOverrideSensor(controller, entry),
        ]
    )


class SunriseActiveSensor(SunriseAlarmEntity, BinarySensorEntity):
    """True while a sunrise ramp (or snooze) is running."""

    _attr_translation_key = "active"
    _attr_icon = "mdi:play-circle"

    def __init__(self, controller, entry) -> None:
        super().__init__(controller, entry)
        self._attr_unique_id = f"{entry.entry_id}_active"

    @property
    def is_on(self) -> bool:
        return self._controller.active

    @property
    def extra_state_attributes(self) -> dict:
        return {"snooze_count": self._controller.snooze_count}


class SunriseDndOverrideSensor(SunriseAlarmEntity, BinarySensorEntity):
    """True while HA is holding the phone muted (DND override active)."""

    _attr_translation_key = "dnd_override"
    _attr_icon = "mdi:bell-off"

    def __init__(self, controller, entry) -> None:
        super().__init__(controller, entry)
        self._attr_unique_id = f"{entry.entry_id}_dnd_override"

    @property
    def is_on(self) -> bool:
        return self._controller.dnd_overridden
