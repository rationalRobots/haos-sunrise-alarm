"""Scenario checks for SunriseAlarmController against a mocked hass.

Run inside a Home Assistant container (needs the `homeassistant` package):

    docker exec homeassistant python3 /config/.sa_test/tests/controller_scenarios.py

with the repo's custom_components/ copied next to it under /config/.sa_test.
"""
import asyncio
import logging
import os
import sys
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.environ.get("SA_TEST_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

from homeassistant.util import dt as dt_util  # noqa: E402
from custom_components.sunrise_alarm import coordinator as co  # noqa: E402

CLOCK = "com.google.android.deskclock"
BASE = {
    "lead_min": 30, "ramp_min": 30, "snooze_min": 9, "snooze_max": 3,
    "window_start": "00:00:00", "window_end": "23:59:59",
    "clock_packages": [CLOCK], "light": "light.lamp", "speaker": "media_player.spk",
    "notify": "notify.mobile_app_phone",
}


def make(opts, alarm_state, pkg=CLOCK):
    hass = MagicMock()
    hass.async_create_task = lambda coro: asyncio.ensure_future(coro)
    hass.services.async_call = AsyncMock()
    st = MagicMock(); st.state = alarm_state; st.attributes = {"Package": pkg}
    hass.states.get.return_value = st
    entry = MagicMock(); entry.entry_id = "e1"; entry.title = "Test"
    entry.data = {"alarm_sensor": "sensor.x"}; entry.options = {**BASE, **opts}
    with patch.object(co, "Store"):
        c = co.SunriseAlarmController(hass, entry)
    c._store.async_save = AsyncMock()
    c._signal = lambda: None
    return c


def calls(c, domain=None, service=None):
    out = []
    for call in c.hass.services.async_call.await_args_list:
        d, s, data = call.args[:3]
        if (domain is None or d == domain) and (service is None or s == service):
            out.append(data)
    return out


def action(c, name):
    ev = MagicMock(); ev.data = {"action": name}
    return c._handle_action(ev)


async def scheduling():
    now = dt_util.now().replace(microsecond=0)
    r = {}
    with patch.object(co, "async_track_point_in_time", return_value=lambda: None):
        c = make({}, (now + timedelta(minutes=29, seconds=58)).isoformat())
        c.async_start_run = AsyncMock()
        c._reschedule(); await asyncio.sleep(0)
        r["late_start"] = (c.async_start_run.await_args.kwargs, c.late_start)
        c = make({}, (now + timedelta(minutes=40)).isoformat())
        c.async_start_run = AsyncMock()
        c._reschedule(); await asyncio.sleep(0)
        r["normal"] = (c.async_start_run.await_count, sorted(k for k in c._unsubs if c._unsubs[k]))
        c = make({}, (now + timedelta(minutes=20)).isoformat())
        c.async_start_run = AsyncMock()
        c._reschedule(); c._reschedule(); await asyncio.sleep(0)
        r["double"] = c.async_start_run.await_count
        c = make({"ramp_min": 10}, (now + timedelta(minutes=20)).isoformat())
        c.async_start_run = AsyncMock()
        c._reschedule(); await asyncio.sleep(0)
        r["cap"] = c.async_start_run.await_args.kwargs
        c = make({}, (now + timedelta(minutes=20)).isoformat())
        c.async_start_run = AsyncMock()
        c._stopped_date = now.strftime("%Y-%m-%d")
        c._reschedule(); await asyncio.sleep(0)
        r["stopped_blocks_late_start"] = (c.async_start_run.await_count, c.last_skip_reason)
    assert r["late_start"] == ({"ramp_min": 29}, True), r
    assert r["normal"] == (0, ["failsafe", "firing", "point", "prealarm", "premute"]), r
    assert r["double"] == 1, r
    assert r["cap"] == {"ramp_min": 10}, r
    assert r["stopped_blocks_late_start"] == (0, "stopped for today"), r
    print("scheduling: ok")


class Gate:
    """Replace asyncio.sleep: long sleeps wait on an event the test opens."""

    def __init__(self):
        self.event = asyncio.Event()
        self.real = asyncio.sleep

    async def __call__(self, seconds):
        if seconds >= 60:
            await self.event.wait()
        else:
            await self.real(0)

    async def release(self):
        self.event.set()
        for _ in range(5):
            await self.real(0)
        self.event = asyncio.Event()


async def notifications():
    now = dt_util.now().replace(microsecond=0)
    gate = Gate()
    with patch.object(co, "async_track_point_in_time", return_value=lambda: None), \
         patch.object(co.asyncio, "sleep", gate):
        c = make({}, (now + timedelta(minutes=40)).isoformat())
        c._reschedule()
        # Start a run: main notification has Snooze 10 / Snooze 20 / More
        await c.async_start_run()
        n = calls(c, "notify")[-1]
        titles = [a["title"] for a in n["data"]["actions"]]
        assert titles == ["Snooze 10", "Snooze 20", "More…"], titles
        assert c.active
        # More -> menu with Snooze 30 / Dismiss / Stop
        await action(c, c._actions["more"])
        titles = [a["title"] for a in calls(c, "notify")[-1]["data"]["actions"]]
        assert titles == ["Snooze 30", "Dismiss, I'm up", "Stop for today…"], titles
        # Stop ask -> confirmation with Keep first and a timeout
        await action(c, c._actions["stop_ask"])
        n = calls(c, "notify")[-1]
        titles = [a["title"] for a in n["data"]["actions"]]
        assert titles == ["Keep going", "Yes, stop today"], titles
        assert n["data"]["timeout"] == 60 and n["data"]["alert_once"] is True, n
        assert n["data"]["tag"].endswith("_menu"), n
        # Keep -> only the menu is cleared; main notification untouched, still active
        c.hass.services.async_call.reset_mock()
        await action(c, c._actions["keep"])
        clears = [d for d in calls(c, "notify") if d["message"] == "clear_notification"]
        assert len(clears) == 1 and clears[0]["data"]["tag"].endswith("_menu"), clears
        assert len(calls(c, "notify")) == 1 and c.active
        # Snooze 20 -> run cancelled, music paused, lamp fades over 45 s, count 1
        c.hass.services.async_call.reset_mock()
        await action(c, f"{co.ACTION_SNOOZE_FOR}_20_e1")
        assert calls(c, "media_player", "media_pause"), "music not paused"
        off = calls(c, "light", "turn_off")
        assert off and off[0].get("transition") == 45, off
        assert c.snooze_count == 1 and c.active and c._snooze_task is not None
        assert "Snoozing 20 min" in calls(c, "notify")[-1]["message"]
        # Snooze 30 while snoozing -> replaces, count unchanged
        await action(c, f"{co.ACTION_SNOOZE_FOR}_30_e1")
        assert c.snooze_count == 1, c.snooze_count
        # Let the snooze timer run out -> short re-ramp
        c.hass.services.async_call.reset_mock()
        await gate.release()
        assert c._snooze_task is None and c.active
        assert "Sunrise wake starting" in calls(c, "notify")[-1]["message"]
        assert c._run_task is not None
        # Stop confirm -> stopped today, everything down, phone layer stood down
        c.hass.services.async_call.reset_mock()
        await action(c, c._actions["stop_confirm"])
        assert c.stopped_today and not c.active and c._snooze_task is None
        assert not c._session_live()
        assert all(c._unsubs[k] is None for k in ("point", "prealarm", "premute", "firing", "failsafe"))
        assert calls(c, "media_player", "turn_off"), "speaker not turned off"
        assert calls(c, "light", "turn_off")[0].get("transition") == 45
        assert "Stopped for today" in calls(c, "notify")[-1]["message"]
        assert c._pstate.get("stopped_date") == c._stopped_date, "stop not persisted"
        # A reschedule later that day must not start anything
        c.async_start_run = AsyncMock()
        c.hass.states.get.return_value.state = (now + timedelta(minutes=20)).isoformat()
        c._reschedule(); await asyncio.sleep(0)
        assert c.async_start_run.await_count == 0
        # A stray snooze after stop must not arm a pre-alarm snooze for tomorrow
        await c.async_snooze(10)
        assert c._snooze_task is None and not c._suppress_next
        # Legacy pre-alarm Cancel routes to the confirmation, not a stop
        c2 = make({}, (now + timedelta(minutes=40)).isoformat())
        await action(c2, c2._actions["cancel"])
        assert calls(c2, "notify")[-1]["title"] == "Stop today's wake?"
        assert not c2.stopped_today
        # Dismiss during a snooze cancels the pending restart
        c3 = make({}, (now + timedelta(minutes=40)).isoformat())
        await c3.async_start_run()
        await action(c3, f"{co.ACTION_SNOOZE_FOR}_10_e1")
        assert c3._snooze_task is not None
        await action(c3, c3._actions["dismiss"])
        assert c3._snooze_task is None and not c3.active
        assert calls(c3, "light", "turn_on")[-1].get("brightness_pct") == 100
        c3.async_start_run = AsyncMock()
        await gate.release()
        assert c3.async_start_run.await_count == 0, "snooze restarted after dismiss"
        # Dismiss on the pre-alarm notification cancels the pending start
        c4 = make({}, (now + timedelta(minutes=40)).isoformat())
        c4._reschedule()
        assert c4._unsubs["point"] is not None
        await action(c4, c4._actions["dismiss"])
        assert c4._unsubs["point"] is None and c4._last_run_date == now.strftime("%Y-%m-%d")
        c4.async_start_run = AsyncMock()
        c4._handle_start(now); await asyncio.sleep(0)
        assert c4.async_start_run.await_count == 0 and c4.last_skip_reason == "already ran today"
    print("notifications: ok")


async def main():
    await scheduling()
    await notifications()
    print("ALL SCENARIOS PASSED")


asyncio.run(main())
