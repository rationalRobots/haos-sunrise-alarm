"""Config and options flow for Sunrise Alarm."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ALARM_SENSOR,
    CONF_AUDIO,
    CONF_AUDIO_DELAY_MIN,
    CONF_AUDIO_TYPE,
    CONF_BRIGHTNESS_MAX,
    CONF_KELVIN_END,
    CONF_KELVIN_START,
    CONF_LEAD_MIN,
    CONF_LIGHT,
    CONF_NOTIFY,
    CONF_RAMP_MIN,
    CONF_SNOOZE_MAX,
    CONF_SNOOZE_MIN,
    CONF_SPEAKER,
    CONF_VOLUME_MAX,
    CONF_WINDOW_END,
    CONF_WINDOW_START,
    DEFAULT_AUDIO_DELAY_MIN,
    DEFAULT_AUDIO_TYPE,
    DEFAULT_BRIGHTNESS_MAX,
    DEFAULT_KELVIN_END,
    DEFAULT_KELVIN_START,
    DEFAULT_LEAD_MIN,
    DEFAULT_RAMP_MIN,
    DEFAULT_SNOOZE_MAX,
    DEFAULT_SNOOZE_MIN,
    DEFAULT_VOLUME_MAX,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    DOMAIN,
)

_LIGHT = selector.EntitySelector(selector.EntitySelectorConfig(domain="light"))
_SPEAKER = selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player"))
_ALARM = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
_TEXT = selector.TextSelector()


def _num(minimum: float, maximum: float, step: float, unit: str | None = None):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _user_schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("name"): _TEXT,
            vol.Required(CONF_LIGHT): _LIGHT,
            vol.Optional(CONF_SPEAKER): _SPEAKER,
            vol.Optional(CONF_NOTIFY): _TEXT,
            vol.Optional(CONF_ALARM_SENSOR): _ALARM,
        }
    )


def _options_schema(data: dict[str, Any]) -> vol.Schema:
    def cur(key, default):
        return data.get(key, default)

    return vol.Schema(
        {
            vol.Required(CONF_LEAD_MIN, default=cur(CONF_LEAD_MIN, DEFAULT_LEAD_MIN)): _num(1, 120, 1, "min"),
            vol.Required(CONF_RAMP_MIN, default=cur(CONF_RAMP_MIN, DEFAULT_RAMP_MIN)): _num(1, 120, 1, "min"),
            vol.Required(CONF_BRIGHTNESS_MAX, default=cur(CONF_BRIGHTNESS_MAX, DEFAULT_BRIGHTNESS_MAX)): _num(1, 100, 1, "%"),
            vol.Required(CONF_KELVIN_START, default=cur(CONF_KELVIN_START, DEFAULT_KELVIN_START)): _num(1500, 6500, 100, "K"),
            vol.Required(CONF_KELVIN_END, default=cur(CONF_KELVIN_END, DEFAULT_KELVIN_END)): _num(1500, 6500, 100, "K"),
            vol.Optional(CONF_AUDIO, default=cur(CONF_AUDIO, "")): _TEXT,
            vol.Required(CONF_AUDIO_TYPE, default=cur(CONF_AUDIO_TYPE, DEFAULT_AUDIO_TYPE)): selector.SelectSelector(
                selector.SelectSelectorConfig(options=["music", "playlist", "tts"])
            ),
            vol.Required(CONF_AUDIO_DELAY_MIN, default=cur(CONF_AUDIO_DELAY_MIN, DEFAULT_AUDIO_DELAY_MIN)): _num(0, 120, 1, "min"),
            vol.Required(CONF_VOLUME_MAX, default=cur(CONF_VOLUME_MAX, DEFAULT_VOLUME_MAX)): _num(0, 1, 0.05),
            vol.Required(CONF_SNOOZE_MIN, default=cur(CONF_SNOOZE_MIN, DEFAULT_SNOOZE_MIN)): _num(1, 60, 1, "min"),
            vol.Required(CONF_SNOOZE_MAX, default=cur(CONF_SNOOZE_MAX, DEFAULT_SNOOZE_MAX)): _num(0, 10, 1),
            vol.Required(CONF_WINDOW_START, default=cur(CONF_WINDOW_START, DEFAULT_WINDOW_START)): selector.TimeSelector(),
            vol.Required(CONF_WINDOW_END, default=cur(CONF_WINDOW_END, DEFAULT_WINDOW_END)): selector.TimeSelector(),
        }
    )


class SunriseAlarmConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup of a wake profile."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a profile from the user's entity choices."""
        if user_input is not None:
            name = user_input.pop("name")
            await self.async_set_unique_id(name.lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=name, data=user_input)
        return self.async_show_form(step_id="user", data_schema=_user_schema())

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return SunriseAlarmOptionsFlow()


class SunriseAlarmOptionsFlow(OptionsFlow):
    """Edit timings, audio and the source-gating window."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        merged = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init", data_schema=_options_schema(merged)
        )
