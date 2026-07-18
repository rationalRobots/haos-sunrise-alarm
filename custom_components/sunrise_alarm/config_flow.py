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
    CONF_DASHBOARD,
    CONF_ESCALATE,
    CONF_FAILSAFE_EXTRA_MIN,
    CONF_KELVIN_END,
    CONF_KELVIN_START,
    CONF_LEAD_MIN,
    CONF_LIGHT,
    CONF_NOTIFY,
    CONF_PERSON,
    CONF_PREALARM_LEAD_SEC,
    CONF_PREMUTE_SEC,
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
    DEFAULT_DASHBOARD,
    DEFAULT_ESCALATE,
    DEFAULT_FAILSAFE_EXTRA_MIN,
    DEFAULT_KELVIN_END,
    DEFAULT_KELVIN_START,
    DEFAULT_LEAD_MIN,
    DEFAULT_PREALARM_LEAD_SEC,
    DEFAULT_PREMUTE_SEC,
    DEFAULT_RAMP_MIN,
    DEFAULT_SNOOZE_MAX,
    DEFAULT_SNOOZE_MIN,
    DEFAULT_VOLUME_MAX,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    DOMAIN,
)
from .person import resolve_person

_PERSON = selector.EntitySelector(selector.EntitySelectorConfig(domain="person"))
_LIGHT = selector.EntitySelector(selector.EntitySelectorConfig(domain="light"))
_SPEAKER = selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player"))
_ALARM = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
_TEXT = selector.TextSelector()


def _num(minimum: float, maximum: float, step: float, unit: str | None = None):
    config: dict[str, Any] = {
        "min": minimum,
        "max": maximum,
        "step": step,
        "mode": selector.NumberSelectorMode.BOX,
    }
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(selector.NumberSelectorConfig(**config))


def _user_schema() -> vol.Schema:
    """Person-centric first step: pick the person and their lamp/speaker."""
    return vol.Schema(
        {
            vol.Optional(CONF_PERSON): _PERSON,
            vol.Optional("name"): _TEXT,
            vol.Required(CONF_LIGHT): _LIGHT,
            vol.Optional(CONF_SPEAKER): _SPEAKER,
        }
    )


def _manual_schema() -> vol.Schema:
    """Fallback step when the phone can't be inferred from a person."""
    return vol.Schema(
        {
            vol.Optional(CONF_NOTIFY): _TEXT,
            vol.Optional(CONF_ALARM_SENSOR): _ALARM,
        }
    )


# Sensible defaults used to pre-fill the form (as suggested values, not schema
# defaults — see async_step_init). Window times are HH:MM:SS for the TimeSelector.
_OPTION_DEFAULTS: dict[str, Any] = {
    CONF_LEAD_MIN: DEFAULT_LEAD_MIN,
    CONF_RAMP_MIN: DEFAULT_RAMP_MIN,
    CONF_BRIGHTNESS_MAX: DEFAULT_BRIGHTNESS_MAX,
    CONF_KELVIN_START: DEFAULT_KELVIN_START,
    CONF_KELVIN_END: DEFAULT_KELVIN_END,
    CONF_AUDIO: "",
    CONF_AUDIO_TYPE: DEFAULT_AUDIO_TYPE,
    CONF_AUDIO_DELAY_MIN: DEFAULT_AUDIO_DELAY_MIN,
    CONF_VOLUME_MAX: DEFAULT_VOLUME_MAX,
    CONF_SNOOZE_MIN: DEFAULT_SNOOZE_MIN,
    CONF_SNOOZE_MAX: DEFAULT_SNOOZE_MAX,
    CONF_PREALARM_LEAD_SEC: DEFAULT_PREALARM_LEAD_SEC,
    CONF_DASHBOARD: DEFAULT_DASHBOARD,
    CONF_PREMUTE_SEC: DEFAULT_PREMUTE_SEC,
    CONF_ESCALATE: DEFAULT_ESCALATE,
    CONF_FAILSAFE_EXTRA_MIN: DEFAULT_FAILSAFE_EXTRA_MIN,
    CONF_WINDOW_START: f"{DEFAULT_WINDOW_START}:00",
    CONF_WINDOW_END: f"{DEFAULT_WINDOW_END}:00",
}


def _options_schema() -> vol.Schema:
    """Static options schema. Current values are applied as suggested values."""
    return vol.Schema(
        {
            # Devices + notify are editable here too (not just at first setup).
            vol.Required(CONF_LIGHT): _LIGHT,
            vol.Optional(CONF_SPEAKER): _SPEAKER,
            vol.Optional(CONF_NOTIFY): _TEXT,
            vol.Optional(CONF_ALARM_SENSOR): _ALARM,
            vol.Required(CONF_LEAD_MIN): _num(1, 120, 1, "min"),
            vol.Required(CONF_RAMP_MIN): _num(1, 120, 1, "min"),
            vol.Required(CONF_BRIGHTNESS_MAX): _num(1, 100, 1, "%"),
            vol.Required(CONF_KELVIN_START): _num(1500, 6500, 100, "K"),
            vol.Required(CONF_KELVIN_END): _num(1500, 6500, 100, "K"),
            vol.Optional(CONF_AUDIO): _TEXT,
            vol.Required(CONF_AUDIO_TYPE): selector.SelectSelector(
                selector.SelectSelectorConfig(options=["music", "playlist", "tts"])
            ),
            vol.Required(CONF_AUDIO_DELAY_MIN): _num(0, 120, 1, "min"),
            vol.Required(CONF_VOLUME_MAX): _num(0, 1, 0.05),
            vol.Required(CONF_SNOOZE_MIN): _num(1, 60, 1, "min"),
            vol.Required(CONF_SNOOZE_MAX): _num(0, 10, 1),
            vol.Required(CONF_PREALARM_LEAD_SEC): _num(0, 600, 5, "s"),
            vol.Optional(CONF_DASHBOARD): _TEXT,
            # Phone-side tunables (companion sensors are wired by the person flow).
            vol.Required(CONF_PREMUTE_SEC): _num(0, 600, 5, "s"),
            vol.Required(CONF_ESCALATE): selector.BooleanSelector(),
            vol.Required(CONF_FAILSAFE_EXTRA_MIN): _num(0, 60, 1, "min"),
            vol.Required(CONF_WINDOW_START): selector.TimeSelector(),
            vol.Required(CONF_WINDOW_END): selector.TimeSelector(),
        }
    )


class SunriseAlarmConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup of a wake profile (person-centric)."""

    VERSION = 1

    def __init__(self) -> None:
        """Init the flow's carry-over state."""
        self._pending: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick a person; infer their phone (notify + companion sensors)."""
        if user_input is not None:
            data: dict[str, Any] = {CONF_LIGHT: user_input[CONF_LIGHT]}
            if user_input.get(CONF_SPEAKER):
                data[CONF_SPEAKER] = user_input[CONF_SPEAKER]
            name = user_input.get("name")
            person = user_input.get(CONF_PERSON)
            if person:
                data[CONF_PERSON] = person
                if not name:
                    pstate = self.hass.states.get(person)
                    name = (
                        (pstate.attributes.get("friendly_name") if pstate else None)
                        or person.split(".")[-1]
                    )
                data.update(resolve_person(self.hass, person))
                if data.get(CONF_NOTIFY):
                    return await self._finish(name, data)
                # Person had no resolvable Companion phone -> ask manually.
                self._pending = {"name": name, "data": data}
                return await self.async_step_manual()
            self._pending = {"name": name or "Wake", "data": data}
            return await self.async_step_manual()
        return self.async_show_form(step_id="user", data_schema=_user_schema())

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual notify + alarm-sensor when no person/phone was inferred."""
        if user_input is not None:
            data = dict(self._pending["data"])
            if user_input.get(CONF_NOTIFY):
                data[CONF_NOTIFY] = user_input[CONF_NOTIFY]
            if user_input.get(CONF_ALARM_SENSOR):
                data[CONF_ALARM_SENSOR] = user_input[CONF_ALARM_SENSOR]
            return await self._finish(self._pending["name"], data)
        return self.async_show_form(step_id="manual", data_schema=_manual_schema())

    async def _finish(self, name: str, data: dict[str, Any]) -> ConfigFlowResult:
        """Create the entry with a unique id derived from the name."""
        await self.async_set_unique_id(name.lower())
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=name, data=data)

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
            return self.async_create_entry(data=user_input)
        suggested = {
            **_OPTION_DEFAULTS,
            **self.config_entry.data,
            **self.config_entry.options,
        }
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _options_schema(), suggested
            ),
        )
