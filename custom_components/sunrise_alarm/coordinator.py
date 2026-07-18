"""Sunrise Alarm controller: schedules and runs the wake routine."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
)
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ALARM_SENSOR,
    CONF_AUDIO,
    CONF_AUDIO_DELAY_MIN,
    CONF_AUDIO_TYPE,
    CONF_BRIGHTNESS_MAX,
    CONF_CLOCK_PACKAGES,
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
    DEFAULT_CLOCK_PACKAGES,
    DEFAULT_KELVIN_END,
    DEFAULT_KELVIN_START,
    DEFAULT_LEAD_MIN,
    DEFAULT_RAMP_MIN,
    DEFAULT_SNOOZE_MAX,
    DEFAULT_SNOOZE_MIN,
    DEFAULT_VOLUME_MAX,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    SIGNAL_UPDATE,
    STEP_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE = {"unknown", "unavailable", "none", ""}


def _parse_hhmm(value: str, fallback: str) -> time:
    """Parse an 'HH:MM' string into a time, falling back on error."""
    result = dt_util.parse_time(value) or dt_util.parse_time(fallback)
    return result


class SunriseAlarmController:
    """Owns one wake profile: resolves the alarm, schedules and runs it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the controller for a config entry."""
        self.hass = hass
        self.entry = entry
        self.enabled: bool = True
        self.active: bool = False
        self.snooze_count: int = 0
        self.effective_alarm: datetime | None = None
        self.start_time: datetime | None = None
        self._run_task: asyncio.Task | None = None
        self._unsub_point: CALLBACK_TYPE | None = None
        self._unsub_state: CALLBACK_TYPE | None = None
        self._last_run_date: str | None = None

    # -- option access -------------------------------------------------------
    def opt(self, key: str, default=None):
        """Read an option, preferring the (editable) options over data."""
        if key in self.entry.options:
            return self.entry.options[key]
        return self.entry.data.get(key, default)

    @property
    def name(self) -> str:
        """Return the profile's display name."""
        return self.entry.title

    # -- lifecycle -----------------------------------------------------------
    async def async_setup(self) -> None:
        """Start listening for alarm changes and schedule the first run."""
        sensor = self.opt(CONF_ALARM_SENSOR)
        if sensor:
            self._unsub_state = async_track_state_change_event(
                self.hass, [sensor], self._handle_alarm_change
            )
        self._reschedule()

    async def async_unload(self) -> None:
        """Cancel all timers and any running ramp."""
        if self._unsub_state:
            self._unsub_state()
            self._unsub_state = None
        self._cancel_point()
        await self._cancel_run()

    # -- alarm resolution (the source gate) ----------------------------------
    def _resolve_alarm(self) -> datetime | None:
        """Return the effective wake time, or None if the source isn't a real alarm.

        This is the guard that stops calendar reminders, Samsung Routines and
        timers (which the Companion 'next alarm' sensor also surfaces) from
        arming the routine: the alarm only counts if it comes from an allowed
        clock app AND its time-of-day is inside the morning window.
        """
        sensor = self.opt(CONF_ALARM_SENSOR)
        if not sensor:
            return None
        state = self.hass.states.get(sensor)
        if state is None or state.state.lower() in _UNAVAILABLE:
            return None
        when = dt_util.parse_datetime(state.state)
        if when is None:
            return None
        when = dt_util.as_local(when)

        packages = self.opt(CONF_CLOCK_PACKAGES, DEFAULT_CLOCK_PACKAGES)
        if packages:
            package = state.attributes.get("Package")
            if package not in packages:
                _LOGGER.debug(
                    "%s: ignoring alarm from non-clock source %s", self.name, package
                )
                return None

        win_start = _parse_hhmm(
            self.opt(CONF_WINDOW_START, DEFAULT_WINDOW_START), DEFAULT_WINDOW_START
        )
        win_end = _parse_hhmm(
            self.opt(CONF_WINDOW_END, DEFAULT_WINDOW_END), DEFAULT_WINDOW_END
        )
        tod = when.timetz().replace(tzinfo=None)
        if not (win_start <= tod <= win_end):
            _LOGGER.debug("%s: alarm %s outside morning window", self.name, tod)
            return None
        return when

    # -- scheduling ----------------------------------------------------------
    @callback
    def _handle_alarm_change(self, event) -> None:
        """React to the alarm sensor changing."""
        self._reschedule()

    @callback
    def _reschedule(self) -> None:
        """Recompute the effective alarm/start and (re)arm the start timer."""
        self._cancel_point()
        self.effective_alarm = self._resolve_alarm()
        if self.effective_alarm is None:
            self.start_time = None
            self._signal()
            return
        lead = int(self.opt(CONF_LEAD_MIN, DEFAULT_LEAD_MIN))
        self.start_time = self.effective_alarm - timedelta(minutes=lead)
        now = dt_util.now()
        if self.start_time > now:
            self._unsub_point = async_track_point_in_time(
                self.hass, self._handle_start, self.start_time
            )
        self._signal()

    @callback
    def _cancel_point(self) -> None:
        if self._unsub_point:
            self._unsub_point()
            self._unsub_point = None

    @callback
    def _handle_start(self, _now: datetime) -> None:
        """Fire when the scheduled start time is reached."""
        self._unsub_point = None
        today = dt_util.now().strftime("%Y-%m-%d")
        if not self.enabled:
            return
        if self.active:
            return
        if self._last_run_date == today:
            return
        self._last_run_date = today
        self.hass.async_create_task(self.async_start_run())

    # -- the routine ---------------------------------------------------------
    async def async_start_run(self, ramp_min: int | None = None) -> None:
        """Begin (or restart) the sunrise ramp."""
        await self._cancel_run()
        self.active = True
        self._signal()
        ramp = ramp_min if ramp_min is not None else int(
            self.opt(CONF_RAMP_MIN, DEFAULT_RAMP_MIN)
        )
        await self._notify(
            title=f"Good morning, {self.name}", message="Sunrise wake starting."
        )
        self._run_task = self.hass.async_create_task(self._async_sunrise(ramp))

    async def _async_sunrise(self, ramp_min: int) -> None:
        """Run the light and audio ramps in parallel until done or cancelled."""
        try:
            await asyncio.gather(
                self._light_branch(ramp_min), self._audio_branch(ramp_min)
            )
        except asyncio.CancelledError:  # noqa: TRY302 - cooperative stop
            raise
        finally:
            self._run_task = None

    async def _light_branch(self, ramp_min: int) -> None:
        light = self.opt(CONF_LIGHT)
        if not light:
            return
        bri_max = int(self.opt(CONF_BRIGHTNESS_MAX, DEFAULT_BRIGHTNESS_MAX))
        k_start = int(self.opt(CONF_KELVIN_START, DEFAULT_KELVIN_START))
        k_end = int(self.opt(CONF_KELVIN_END, DEFAULT_KELVIN_END))
        steps = max(1, round(ramp_min * 60 / STEP_SECONDS))
        await self._light(light, 1, k_start, 0)
        for i in range(1, steps + 1):
            progress = i / steps
            bri = max(1, round(progress * bri_max))
            kelvin = round(k_start + progress * (k_end - k_start))
            await self._light(light, bri, kelvin, STEP_SECONDS)
            await asyncio.sleep(STEP_SECONDS)

    async def _audio_branch(self, ramp_min: int) -> None:
        speaker = self.opt(CONF_SPEAKER)
        audio = (self.opt(CONF_AUDIO) or "").strip()
        if not speaker or not audio:
            return
        delay = int(self.opt(CONF_AUDIO_DELAY_MIN, DEFAULT_AUDIO_DELAY_MIN))
        if delay:
            await asyncio.sleep(delay * 60)
        vol_max = float(self.opt(CONF_VOLUME_MAX, DEFAULT_VOLUME_MAX))
        await self._call("media_player", "volume_set", speaker, volume_level=0)
        await self._call(
            "media_player",
            "play_media",
            speaker,
            media_content_id=audio,
            media_content_type=self.opt(CONF_AUDIO_TYPE, DEFAULT_AUDIO_TYPE),
        )
        vol_minutes = max(1, ramp_min - delay)
        steps = max(1, round(vol_minutes * 60 / STEP_SECONDS))
        for i in range(1, steps + 1):
            vol = round(i / steps * vol_max, 2)
            await self._call("media_player", "volume_set", speaker, volume_level=vol)
            await asyncio.sleep(STEP_SECONDS)

    async def async_snooze(self) -> None:
        """Snooze: pause, wait, then re-run a short sunrise, or dismiss at the cap."""
        if not self.active:
            return
        await self._cancel_run()
        self.snooze_count += 1
        snooze_min = int(self.opt(CONF_SNOOZE_MIN, DEFAULT_SNOOZE_MIN))
        snooze_max = int(self.opt(CONF_SNOOZE_MAX, DEFAULT_SNOOZE_MAX))
        light = self.opt(CONF_LIGHT)
        speaker = self.opt(CONF_SPEAKER)
        if light:
            await self._call("light", "turn_off", light)
        if speaker:
            await self._call("media_player", "media_pause", speaker)
        if self.snooze_count > snooze_max:
            await self.async_dismiss()
            return
        self._signal()
        await self._notify(
            message=f"Snoozing {snooze_min} min ({self.snooze_count}/{snooze_max})."
        )
        await asyncio.sleep(snooze_min * 60)
        if self.active:
            await self.async_start_run(ramp_min=2)

    async def async_dismiss(self) -> None:
        """Dismiss: stop the routine, leave the lamp on, stop audio."""
        await self._cancel_run()
        self.active = False
        self.snooze_count = 0
        light = self.opt(CONF_LIGHT)
        speaker = self.opt(CONF_SPEAKER)
        if light:
            await self._call("light", "turn_on", light, brightness_pct=100)
        if speaker:
            await self._call("media_player", "media_stop", speaker)
        await self._notify(message=f"Alarm dismissed. Have a good day, {self.name}.")
        self._signal()

    async def async_stop(self) -> None:
        """Hard stop: cancel everything, lamp off, audio off."""
        await self._cancel_run()
        self.active = False
        self.snooze_count = 0
        light = self.opt(CONF_LIGHT)
        speaker = self.opt(CONF_SPEAKER)
        if speaker:
            await self._call("media_player", "turn_off", speaker)
        if light:
            await self._call("light", "turn_off", light)
        self._signal()

    async def _cancel_run(self) -> None:
        """Cancel any in-flight ramp task."""
        task = self._run_task
        self._run_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # -- service helpers -----------------------------------------------------
    async def _light(self, entity: str, bri_pct: int, kelvin: int, transition: int):
        data = {"brightness_pct": bri_pct, "color_temp_kelvin": kelvin}
        if transition:
            data["transition"] = transition
        await self._call("light", "turn_on", entity, **data)

    async def _call(self, domain: str, service: str, entity: str, **data) -> None:
        try:
            await self.hass.services.async_call(
                domain, service, {"entity_id": entity, **data}, blocking=False
            )
        except Exception as err:  # noqa: BLE001 - never let a bad entity kill the ramp
            _LOGGER.warning("%s: %s.%s failed: %s", self.name, domain, service, err)

    async def _notify(self, message: str, title: str | None = None) -> None:
        target = self.opt(CONF_NOTIFY)
        if not target or "." not in target:
            return
        _, service = target.split(".", 1)
        data = {"message": message}
        if title:
            data["title"] = title
        try:
            await self.hass.services.async_call("notify", service, data, blocking=False)
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("%s: notify failed: %s", self.name, err)

    @callback
    def _signal(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_UPDATE.format(entry_id=self.entry.entry_id))

    @callback
    def set_enabled(self, value: bool) -> None:
        """Enable/disable the profile and re-evaluate scheduling."""
        self.enabled = value
        self._reschedule()
