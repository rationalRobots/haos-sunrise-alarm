"""Buttons: snooze, dismiss, stop."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SunriseAlarmEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the control buttons."""
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SunriseButton(controller, entry, "snooze", "mdi:alarm-snooze"),
            SunriseButton(controller, entry, "dismiss", "mdi:alarm-off"),
            SunriseButton(controller, entry, "stop", "mdi:stop-circle"),
        ]
    )


class SunriseButton(SunriseAlarmEntity, ButtonEntity):
    """A single control button mapped to a controller coroutine."""

    def __init__(self, controller, entry, action: str, icon: str) -> None:
        super().__init__(controller, entry)
        self._action = action
        self._attr_translation_key = action
        self._attr_icon = icon
        self._attr_unique_id = f"{entry.entry_id}_{action}"

    async def async_press(self) -> None:
        await getattr(self._controller, f"async_{self._action}")()
