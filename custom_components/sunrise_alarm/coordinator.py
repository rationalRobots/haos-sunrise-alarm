"""Sunrise Alarm controller: schedules and runs the wake routine.

Includes the phone-side layer (Phase 3): proactive pre-mute + hold-retry, a
DND override that snapshots and restores the phone's prior state, mirrors that
react to the phone's own firing/snooze/dismiss, a failsafe un-mute backstop,
call-through, and escalation. Runtime mute state is persisted so a restart can
never leave the phone silenced.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ACTION_CANCEL,
    ACTION_DISMISS,
    ACTION_SNOOZE,
    ALARM_STREAM,
    CMD_DND,
    CMD_VOLUME,
    CONF_ALARM_SENSOR,
    CONF_ALARM_VOL_SENSOR,
    CONF_AUDIO,
    CONF_AUDIO_DELAY_MIN,
    CONF_AUDIO_TYPE,
    CONF_BRIGHTNESS_MAX,
    CONF_CLOCK_PACKAGES,
    CONF_DASHBOARD,
    CONF_DND_SENSOR,
    CONF_ESCALATE,
    CONF_FAILSAFE_EXTRA_MIN,
    CONF_FIRING_CHANNEL,
    CONF_FIRING_PACKAGE,
    CONF_KELVIN_END,
    CONF_KELVIN_START,
    CONF_LAST_NOTIF_SENSOR,
    CONF_LAST_REMOVED_SENSOR,
    CONF_LEAD_MIN,
    CONF_LIGHT,
    CONF_MUTE_HOLD_INTERVAL_SEC,
    CONF_MUTE_HOLD_RETRIES,
    CONF_NOTIFY,
    CONF_PHONE_STATE_SENSOR,
    CONF_PREALARM_LEAD_SEC,
    CONF_PREMUTE_SEC,
    CONF_RAMP_MIN,
    CONF_SNOOZED_CHANNEL,
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
    DEFAULT_DASHBOARD,
    DEFAULT_ESCALATE,
    DEFAULT_FAILSAFE_EXTRA_MIN,
    DEFAULT_FIRING_CHANNEL,
    DEFAULT_FIRING_PACKAGE,
    DEFAULT_KELVIN_END,
    DEFAULT_KELVIN_START,
    DEFAULT_LEAD_MIN,
    DEFAULT_MUTE_HOLD_INTERVAL_SEC,
    DEFAULT_MUTE_HOLD_RETRIES,
    DEFAULT_PREALARM_LEAD_SEC,
    DEFAULT_PREMUTE_SEC,
    DEFAULT_RAMP_MIN,
    DEFAULT_SNOOZED_CHANNEL,
    DEFAULT_SNOOZE_MAX,
    DEFAULT_SNOOZE_MIN,
    DEFAULT_VOLUME_MAX,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    DND_TOTAL_SILENCE,
    DND_VALID,
    EVENT_NOTIFICATION_ACTION,
    NOTIFY_TAG,
    SIGNAL_UPDATE,
    STEP_SECONDS,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE = {"unknown", "unavailable", "none", ""}


def _parse_hhmm(value: str, fallback: str) -> time:
    """Parse an 'HH:MM[:SS]' string into a time, falling back on error."""
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
        self.prealarm_time: datetime | None = None
        self._run_task: asyncio.Task | None = None
        self._hold_task: asyncio.Task | None = None
        self._unsubs: dict[str, CALLBACK_TYPE | None] = {
            "state": None,
            "action": None,
            "point": None,
            "prealarm": None,
            "premute": None,
            "firing": None,
            "failsafe": None,
            "notif": None,
            "removed": None,
            "phone": None,
        }
        self._last_run_date: str | None = None
        self._suppress_next: bool = False
        self._store: Store = Store(
            hass, STORAGE_VERSION, STORAGE_KEY.format(entry_id=entry.entry_id)
        )
        self._pstate: dict = {"overridden": False, "saved_dnd": "off", "saved_vol": None}
        eid = entry.entry_id
        self._actions = {
            "snooze": f"{ACTION_SNOOZE}_{eid}",
            "dismiss": f"{ACTION_DISMISS}_{eid}",
            "cancel": f"{ACTION_CANCEL}_{eid}",
        }
        self._tag = NOTIFY_TAG.format(entry_id=eid)

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

    @property
    def dnd_overridden(self) -> bool:
        """True while HA is holding the phone muted."""
        return bool(self._pstate.get("overridden"))

    # -- lifecycle -----------------------------------------------------------
    async def async_setup(self) -> None:
        """Load persisted state, wire listeners, and schedule the first run."""
        stored = await self._store.async_load()
        if isinstance(stored, dict):
            self._pstate.update(stored)

        sensor = self.opt(CONF_ALARM_SENSOR)
        if sensor:
            self._unsubs["state"] = async_track_state_change_event(
                self.hass, [sensor], self._handle_alarm_change
            )
        self._unsubs["action"] = self.hass.bus.async_listen(
            EVENT_NOTIFICATION_ACTION, self._handle_action
        )
        notif = self.opt(CONF_LAST_NOTIF_SENSOR)
        if notif:
            self._unsubs["notif"] = async_track_state_change_event(
                self.hass, [notif], self._handle_notification
            )
        removed = self.opt(CONF_LAST_REMOVED_SENSOR)
        if removed:
            self._unsubs["removed"] = async_track_state_change_event(
                self.hass, [removed], self._handle_removed
            )
        phone = self.opt(CONF_PHONE_STATE_SENSOR)
        if phone:
            self._unsubs["phone"] = async_track_state_change_event(
                self.hass, [phone], self._handle_phone_state
            )

        # Watchdog: never come back from a restart still muted.
        if self.dnd_overridden:
            self.hass.async_create_task(self.async_restore_phone())

        self._reschedule()

    async def async_unload(self) -> None:
        """Cancel all timers, listeners and any running tasks."""
        for key, unsub in list(self._unsubs.items()):
            if unsub:
                unsub()
                self._unsubs[key] = None
        await self._cancel_run()
        await self._cancel_hold()

    # -- alarm resolution (the source gate) ----------------------------------
    def _resolve_alarm(self) -> datetime | None:
        """Return the effective wake time, or None if the source isn't a real alarm."""
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
        self._reschedule()

    @callback
    def _cancel_timer(self, key: str) -> None:
        if self._unsubs.get(key):
            self._unsubs[key]()
            self._unsubs[key] = None

    @callback
    def _reschedule(self) -> None:
        """Recompute the alarm-derived times and (re)arm every timer."""
        for key in ("point", "prealarm", "premute", "firing", "failsafe"):
            self._cancel_timer(key)
        self.effective_alarm = self._resolve_alarm()
        if self.effective_alarm is None:
            self.start_time = None
            self.prealarm_time = None
            self._signal()
            return
        now = dt_util.now()
        lead = int(self.opt(CONF_LEAD_MIN, DEFAULT_LEAD_MIN))
        self.start_time = self.effective_alarm - timedelta(minutes=lead)
        prelead = int(self.opt(CONF_PREALARM_LEAD_SEC, DEFAULT_PREALARM_LEAD_SEC))
        self.prealarm_time = self.start_time - timedelta(seconds=prelead)

        def arm(key: str, when: datetime, handler) -> None:
            if when > now:
                self._unsubs[key] = async_track_point_in_time(self.hass, handler, when)

        arm("point", self.start_time, self._handle_start)
        arm("prealarm", self.prealarm_time, self._handle_prealarm)
        # Phone-side timers (only meaningful if a notify target exists).
        if self.opt(CONF_NOTIFY):
            premute = int(self.opt(CONF_PREMUTE_SEC, DEFAULT_PREMUTE_SEC))
            arm(
                "premute",
                self.effective_alarm - timedelta(seconds=premute),
                self._handle_premute,
            )
            arm("firing", self.effective_alarm, self._handle_firing_time)
            snooze_min = int(self.opt(CONF_SNOOZE_MIN, DEFAULT_SNOOZE_MIN))
            extra = int(self.opt(CONF_FAILSAFE_EXTRA_MIN, DEFAULT_FAILSAFE_EXTRA_MIN))
            arm(
                "failsafe",
                self.effective_alarm + timedelta(minutes=snooze_min + extra),
                self._handle_failsafe,
            )
        self._signal()

    def _session_live(self) -> bool:
        """True if a run is active or already ran today (our morning window)."""
        today = dt_util.now().strftime("%Y-%m-%d")
        return self.active or self._last_run_date == today

    @callback
    def _handle_prealarm(self, _now: datetime) -> None:
        self._unsubs["prealarm"] = None
        if not self.enabled or self.active or self._suppress_next:
            return
        self.hass.async_create_task(
            self._notify(
                title=f"Alarm soon, {self.name}",
                message="Your wake routine is about to start.",
                actions=[
                    {"action": self._actions["snooze"], "title": "Snooze"},
                    {"action": self._actions["cancel"], "title": "Cancel"},
                ],
            )
        )

    @callback
    def _handle_start(self, _now: datetime) -> None:
        self._unsubs["point"] = None
        if self._suppress_next:
            self._suppress_next = False
            return
        today = dt_util.now().strftime("%Y-%m-%d")
        if not self.enabled or self.active or self._last_run_date == today:
            return
        self._last_run_date = today
        self.hass.async_create_task(self.async_start_run())

    # -- the sunrise routine -------------------------------------------------
    async def async_start_run(self, ramp_min: int | None = None) -> None:
        await self._cancel_run()
        self._suppress_next = False
        self.active = True
        self._signal()
        ramp = ramp_min if ramp_min is not None else int(
            self.opt(CONF_RAMP_MIN, DEFAULT_RAMP_MIN)
        )
        await self._notify(
            title=f"Good morning, {self.name}",
            message="Sunrise wake starting.",
            actions=[
                {"action": self._actions["snooze"], "title": "Snooze"},
                {"action": self._actions["dismiss"], "title": "Dismiss"},
            ],
        )
        self._run_task = self.hass.async_create_task(self._async_sunrise(ramp))

    async def _async_sunrise(self, ramp_min: int) -> None:
        try:
            await asyncio.gather(
                self._light_branch(ramp_min), self._audio_branch(ramp_min)
            )
        except asyncio.CancelledError:
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
        if not self.active:
            await self._prealarm_snooze()
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

    async def _prealarm_snooze(self) -> None:
        self._suppress_next = True
        snooze_min = int(self.opt(CONF_SNOOZE_MIN, DEFAULT_SNOOZE_MIN))
        await self._notify(message=f"Wake snoozed. Back in {snooze_min} min.")
        await asyncio.sleep(snooze_min * 60)
        await self.async_start_run(ramp_min=2)

    async def _prealarm_cancel(self) -> None:
        self._suppress_next = True
        self._cancel_timer("point")
        await self.async_stop()
        await self._notify(message="Wake cancelled.")

    async def async_dismiss(self) -> None:
        await self._cancel_run()
        await self._cancel_hold()
        self.active = False
        self.snooze_count = 0
        light = self.opt(CONF_LIGHT)
        speaker = self.opt(CONF_SPEAKER)
        if light:
            await self._call("light", "turn_on", light, brightness_pct=100)
        if speaker:
            await self._call("media_player", "media_stop", speaker)
        await self.async_restore_phone()
        await self._notify(message=f"Alarm dismissed. Have a good day, {self.name}.")
        self._signal()

    async def async_stop(self) -> None:
        await self._cancel_run()
        await self._cancel_hold()
        self.active = False
        self.snooze_count = 0
        light = self.opt(CONF_LIGHT)
        speaker = self.opt(CONF_SPEAKER)
        if speaker:
            await self._call("media_player", "turn_off", speaker)
        if light:
            await self._call("light", "turn_off", light)
        await self.async_restore_phone()
        self._signal()

    async def _cancel_run(self) -> None:
        task = self._run_task
        self._run_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _cancel_hold(self) -> None:
        task = self._hold_task
        self._hold_task = None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    # ================= Phone-side layer =====================================
    def _sensor_state(self, conf_key: str) -> str | None:
        entity = self.opt(conf_key)
        if not entity:
            return None
        st = self.hass.states.get(entity)
        if st is None or st.state.lower() in _UNAVAILABLE:
            return None
        return st.state

    def _sensor_attr(self, conf_key: str, attr: str) -> str | None:
        entity = self.opt(conf_key)
        if not entity:
            return None
        st = self.hass.states.get(entity)
        return None if st is None else st.attributes.get(attr)

    async def _persist(self) -> None:
        await self._store.async_save(self._pstate)

    async def _command(self, message: str, data: dict) -> None:
        """Send a Companion command_* message via the notify target."""
        target = self.opt(CONF_NOTIFY)
        if not target or "." not in target:
            return
        _, service = target.split(".", 1)
        try:
            await self.hass.services.async_call(
                "notify", service, {"message": message, "data": data}, blocking=False
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("%s: command %s failed: %s", self.name, message, err)

    async def async_mute_phone(self) -> None:
        """Snapshot DND + alarm volume (once), then mute phone and watch."""
        if not self._pstate.get("overridden"):
            self._pstate["saved_dnd"] = self._sensor_state(CONF_DND_SENSOR) or "off"
            vol = self._sensor_state(CONF_ALARM_VOL_SENSOR)
            self._pstate["saved_vol"] = int(vol) if vol and vol.isdigit() else None
            self._pstate["overridden"] = True
            await self._persist()
        await self._command(CMD_VOLUME, {"media_stream": ALARM_STREAM, "command": 0})
        await self._command(CMD_DND, {"command": DND_TOTAL_SILENCE})
        self._signal()

    async def async_restore_phone(self) -> None:
        """Restore DND + alarm volume to the exact pre-override snapshot."""
        if not self._pstate.get("overridden"):
            return
        prior = self._pstate.get("saved_dnd") or "off"
        if prior not in DND_VALID:
            prior = "off"
        await self._command(CMD_DND, {"command": prior})
        vol = self._pstate.get("saved_vol")
        if vol is not None:
            await self._command(
                CMD_VOLUME, {"media_stream": ALARM_STREAM, "command": int(vol)}
            )
        self._pstate["overridden"] = False
        await self._persist()
        self._signal()

    async def _mute_hold(self) -> None:
        """Re-send the mute across the pre-mute window (the channel is flaky)."""
        retries = int(self.opt(CONF_MUTE_HOLD_RETRIES, DEFAULT_MUTE_HOLD_RETRIES))
        interval = int(
            self.opt(CONF_MUTE_HOLD_INTERVAL_SEC, DEFAULT_MUTE_HOLD_INTERVAL_SEC)
        )
        try:
            for _ in range(retries):
                if not self._pstate.get("overridden"):
                    return
                await self._command(CMD_DND, {"command": DND_TOTAL_SILENCE})
                await self._command(
                    CMD_VOLUME, {"media_stream": ALARM_STREAM, "command": 0}
                )
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            raise

    async def _start_hold(self) -> None:
        await self._cancel_hold()
        self._hold_task = self.hass.async_create_task(self._mute_hold())

    async def async_escalate(self) -> None:
        """Lamp to 100% and audio to full — the phone fired and we're still asleep."""
        light = self.opt(CONF_LIGHT)
        speaker = self.opt(CONF_SPEAKER)
        audio = (self.opt(CONF_AUDIO) or "").strip()
        if light:
            await self._call("light", "turn_on", light, brightness_pct=100)
        if speaker and audio:
            await self._call("media_player", "volume_set", speaker, volume_level=1.0)
            st = self.hass.states.get(speaker)
            if st is None or st.state != "playing":
                await self._call(
                    "media_player",
                    "play_media",
                    speaker,
                    media_content_id=audio,
                    media_content_type=self.opt(CONF_AUDIO_TYPE, DEFAULT_AUDIO_TYPE),
                )

    @callback
    def _handle_premute(self, _now: datetime) -> None:
        self._unsubs["premute"] = None
        if not self.enabled or self._suppress_next or not self._session_live():
            return
        self.hass.async_create_task(self._premute())

    async def _premute(self) -> None:
        await self.async_mute_phone()
        await self._start_hold()

    @callback
    def _handle_firing_time(self, _now: datetime) -> None:
        self._unsubs["firing"] = None
        if not self.enabled or not self._session_live():
            return
        self.hass.async_create_task(self._on_firing())

    async def _on_firing(self) -> None:
        await self.async_mute_phone()
        await self._start_hold()
        self.active = True
        if self.opt(CONF_ESCALATE, DEFAULT_ESCALATE):
            await self.async_escalate()
        self._signal()

    @callback
    def _handle_notification(self, event) -> None:
        """React to the phone's own alarm firing/snooze notification channels."""
        if not self.enabled or not self._session_live():
            return
        new = event.data.get("new_state")
        if new is None:
            return
        channel = new.attributes.get("channel_id")
        package = new.attributes.get("package")
        firing_ch = self.opt(CONF_FIRING_CHANNEL, DEFAULT_FIRING_CHANNEL)
        firing_pkg = self.opt(CONF_FIRING_PACKAGE, DEFAULT_FIRING_PACKAGE)
        snoozed_ch = self.opt(CONF_SNOOZED_CHANNEL, DEFAULT_SNOOZED_CHANNEL)
        if channel == firing_ch and package == firing_pkg:
            self.hass.async_create_task(self._on_firing())
        elif channel == snoozed_ch:
            self.hass.async_create_task(self._on_phone_snooze())

    async def _on_phone_snooze(self) -> None:
        await self.async_restore_phone()
        await self.async_snooze()

    @callback
    def _handle_removed(self, event) -> None:
        """Phone dismissed (Firing notification removed, not a snooze) -> stop HA."""
        if not self.active:
            return
        new = event.data.get("new_state")
        if new is None:
            return
        firing_ch = self.opt(CONF_FIRING_CHANNEL, DEFAULT_FIRING_CHANNEL)
        if new.attributes.get("channel_id") != firing_ch:
            return
        # Skip if a fresh 'Snoozed' notification just posted (that's a snooze).
        snoozed_ch = self.opt(CONF_SNOOZED_CHANNEL, DEFAULT_SNOOZED_CHANNEL)
        if self._sensor_attr(CONF_LAST_NOTIF_SENSOR, "channel_id") == snoozed_ch:
            return
        self.hass.async_create_task(self.async_dismiss())

    @callback
    def _handle_phone_state(self, event) -> None:
        """Call-through: a call during our DND override releases it if DND was off."""
        new = event.data.get("new_state")
        if new is None or new.state != "ringing":
            return
        if self.dnd_overridden and (self._pstate.get("saved_dnd") == "off"):
            self.hass.async_create_task(self.async_restore_phone())

    @callback
    def _handle_failsafe(self, _now: datetime) -> None:
        """Backstop: if still muted this long after the alarm, un-mute the phone."""
        self._unsubs["failsafe"] = None
        if self.dnd_overridden:
            self.hass.async_create_task(self._failsafe())

    async def _failsafe(self) -> None:
        await self.async_restore_phone()
        await self._notify(message="Wake failsafe: phone un-muted.")

    # -- notification action routing -----------------------------------------
    async def _handle_action(self, event: Event) -> None:
        action = event.data.get("action")
        if action == self._actions["snooze"]:
            await self.async_snooze()
        elif action == self._actions["dismiss"]:
            await self.async_dismiss()
        elif action == self._actions["cancel"]:
            await self._prealarm_cancel()

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
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("%s: %s.%s failed: %s", self.name, domain, service, err)

    async def _notify(
        self,
        message: str,
        title: str | None = None,
        actions: list[dict] | None = None,
    ) -> None:
        target = self.opt(CONF_NOTIFY)
        if not target or "." not in target:
            return
        _, service = target.split(".", 1)
        payload: dict = {"message": message}
        if title:
            payload["title"] = title
        ndata: dict = {"tag": self._tag}
        dashboard = self.opt(CONF_DASHBOARD, DEFAULT_DASHBOARD)
        if dashboard:
            ndata["clickAction"] = dashboard
        if actions:
            ndata["actions"] = actions
        payload["data"] = ndata
        try:
            await self.hass.services.async_call(
                "notify", service, payload, blocking=False
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("%s: notify failed: %s", self.name, err)

    @callback
    def _signal(self) -> None:
        async_dispatcher_send(
            self.hass, SIGNAL_UPDATE.format(entry_id=self.entry.entry_id)
        )

    @callback
    def set_enabled(self, value: bool) -> None:
        self.enabled = value
        self._reschedule()
