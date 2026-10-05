"""Sensors: effective alarm time and computed start time."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import SunriseAlarmEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the timestamp sensors."""
    controller = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SunriseAlarmTimeSensor(controller, entry),
            SunriseStartTimeSensor(controller, entry),
        ]
    )


class SunriseAlarmTimeSensor(SunriseAlarmEntity, SensorEntity):
    """The effective (source-gated) wake time."""

    _attr_translation_key = "effective_alarm"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:alarm"

    def __init__(self, controller, entry) -> None:
        super().__init__(controller, entry)
        self._attr_unique_id = f"{entry.entry_id}_effective_alarm"

    @property
    def native_value(self) -> datetime | None:
        return self._controller.effective_alarm


class SunriseStartTimeSensor(SunriseAlarmEntity, SensorEntity):
    """When the routine will start (alarm minus lead)."""

    _attr_translation_key = "start_time"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:weather-sunset-up"

    def __init__(self, controller, entry) -> None:
        super().__init__(controller, entry)
        self._attr_unique_id = f"{entry.entry_id}_start_time"

    @property
    def native_value(self) -> datetime | None:
        return self._controller.start_time

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Explain the schedule: why a start was skipped, or that it began late."""
        return {
            "late_start": self._controller.late_start,
            "last_skip_reason": self._controller.last_skip_reason,
        }
