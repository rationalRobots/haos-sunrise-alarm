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
        # Two fast snooze taps: serialised, one timer, count 1
        c5 = make({}, (now + timedelta(minutes=40)).isoformat())
        await c5.async_start_run()
        real_cancel = c5._cancel_run
        async def slow_cancel():
            await gate.real(0); await gate.real(0); await real_cancel()
        c5._cancel_run = slow_cancel
        await asyncio.gather(action(c5, f"{co.ACTION_SNOOZE_FOR}_10_e1"),
                             action(c5, f"{co.ACTION_SNOOZE_FOR}_20_e1"))
        live = [t for t in asyncio.all_tasks() if t.get_coro().__qualname__.endswith("_snooze_wait") and not t.done()]
        assert c5.snooze_count == 1 and len(live) == 1, (c5.snooze_count, len(live))
        # Pre-mute worker in flight when stop arrives must not leave the phone muted
        c6 = make({}, (now + timedelta(minutes=40)).isoformat())
        c6._pstate["overridden"] = False
        muted = {"n": 0}
        async def mute():
            await gate.real(0); await gate.real(0)
            muted["n"] += 1; c6._pstate["overridden"] = True
        async def restore():
            c6._pstate["overridden"] = False
        c6.async_mute_phone = mute
        c6.async_restore_phone = restore
        c6._start_hold = AsyncMock()
        c6._last_run_date = now.strftime("%Y-%m-%d")
        c6._handle_premute(now)
        assert len(c6._phone_tasks) == 1
        await c6.async_stop_today()
        for _ in range(5):
            await gate.real(0)
        assert not c6._pstate["overridden"], "phone left muted after stop"
        assert not c6._start_hold.await_count, "hold started after stop"
        assert not c6._phone_tasks
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


async def presence():
    now = dt_util.now().replace(microsecond=0)
    alarm = (now + timedelta(minutes=40)).isoformat()

    def mk(person_state, opts=None):
        c = make(opts or {}, alarm)
        c.entry.data = {"alarm_sensor": "sensor.x", "person": "person.chris"}
        alarm_st = c.hass.states.get.return_value
        person_st = MagicMock(); person_st.state = person_state; person_st.attributes = {}
        c.hass.states.get.side_effect = lambda eid: {"sensor.x": alarm_st, "person.chris": person_st}.get(eid)
        c.async_start_run = AsyncMock()
        return c

    with patch.object(co, "async_track_point_in_time", return_value=lambda: None):
        # Away: scheduled start skipped, no pre-alarm, phone layer never live
        c = mk("not_home"); c._reschedule()
        c._handle_prealarm(now); await asyncio.sleep(0)
        assert not calls(c, "notify"), "pre-alarm sent while away"
        c._handle_start(now); await asyncio.sleep(0)
        assert c.async_start_run.await_count == 0 and c.last_skip_reason == "person is not home"
        assert not c._session_live() and c.person_home() is False
        # ...and the phone-layer handlers stay inert even with yesterday's run date
        c._last_run_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        c.async_mute_phone = AsyncMock(); c.async_escalate = AsyncMock()
        c._handle_premute(now); c._handle_firing_time(now)
        for _ in range(3):
            await asyncio.sleep(0)
        assert c.async_mute_phone.await_count == 0 and c.async_escalate.await_count == 0
        assert not c._phone_tasks
        # Coming home inside the lead window -> person listener triggers a late start
        c = mk("not_home"); c.hass.states.get("sensor.x").state = (now + timedelta(minutes=20)).isoformat()
        c._reschedule(); await asyncio.sleep(0)
        assert c.async_start_run.await_count == 0
        c.hass.states.get("person.chris").state = "home"
        ev = MagicMock(); old = MagicMock(); old.state = "not_home"; new = MagicMock(); new.state = "home"
        ev.data = {"old_state": old, "new_state": new}
        c._handle_person_change(ev); await asyncio.sleep(0)
        assert c.async_start_run.await_count == 1, "no late start on arriving home"
        # Pre-alarm snooze, then leaving home before it expires -> no start
        gate = Gate()
        with patch.object(co.asyncio, "sleep", gate):
            c = mk("home")
            await c.async_snooze(10)
            assert c._snooze_task is not None and c._suppress_next
            c.hass.states.get("person.chris").state = "not_home"
            await gate.release()
            assert c.async_start_run.await_count == 0 and c.last_skip_reason == "person is not home"
        # Attribute-only churn (same state) does not reschedule
        c._reschedule = MagicMock()
        same = MagicMock(); same.state = "home"
        ev.data = {"old_state": same, "new_state": new}
        c._handle_person_change(ev)
        assert c._reschedule.call_count == 0
        # Away: late start skipped too
        c = mk("not_home"); c.hass.states.get("sensor.x").state = (now + timedelta(minutes=20)).isoformat()
        c._reschedule(); await asyncio.sleep(0)
        assert c.async_start_run.await_count == 0 and c.last_skip_reason == "person is not home"
        # Home: runs
        c = mk("home"); c._reschedule(); c._handle_start(now); await asyncio.sleep(0)
        assert c.async_start_run.await_count == 1 and c.person_home() is True
        # Unknown tracker: fails open
        c = mk("unavailable"); c._reschedule(); c._handle_start(now); await asyncio.sleep(0)
        assert c.async_start_run.await_count == 1 and c.person_home() is None
        # Option off: away still runs
        c = mk("not_home", {"require_home": False}); c._reschedule(); c._handle_start(now); await asyncio.sleep(0)
        assert c.async_start_run.await_count == 1
    print("presence: ok")


AWAKE_OPTS = {
    "awake_stop": True, "awake_debounce_sec": 30,
    "awake_locked_sensor": "binary_sensor.lock",
    "awake_interactive_sensor": "binary_sensor.inter",
    "awake_charging_sensor": "binary_sensor.charge",
    "awake_steps_sensor": "sensor.steps",
    "awake_activity_sensor": "sensor.activity",
}


def _st(val):
    m = MagicMock(); m.state = val; m.attributes = {}
    return m


def mk_awake(states, opts=None):
    c = make({**AWAKE_OPTS, **(opts or {})}, "2026-10-28T09:00:00+00:00")
    c.hass.states.get.side_effect = lambda eid: (
        _st(states[eid]) if eid in states else None
    )
    return c


AWAKE_UP = {
    "binary_sensor.lock": "off", "binary_sensor.inter": "on",
    "binary_sensor.charge": "off", "sensor.steps": "1200", "sensor.activity": "walking",
}


async def issue2():
    now = dt_util.now().replace(microsecond=0)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    # Ramp finishes on its own -> active STAYS set (wake session still on),
    # _run_task cleared. Start-blocking no longer depends on this flag.
    with patch.object(co.asyncio, "sleep", AsyncMock()):
        c = make({"ramp_min": 1}, (now + timedelta(minutes=40)).isoformat())
        await c.async_start_run()
        assert c.active
        t = c._run_task
        await t
        assert c.active and c._run_task is None
    # A flag left from a PRIOR day is cleared; a flag from today is kept.
    c = make({}, (now + timedelta(minutes=40)).isoformat())
    c.active = True; c._run_task = None; c._snooze_task = None
    c._last_run_date = yesterday
    c._clear_stale_active()
    assert not c.active
    c = make({}, (now + timedelta(minutes=40)).isoformat())
    c.active = True; c._run_task = None; c._snooze_task = None
    c._last_run_date = today
    c._clear_stale_active()
    assert c.active, "same-day flag wrongly cleared (would break awake/snooze)"
    # _run_task is assigned before the start notification (race guard)
    with patch.object(co.asyncio, "sleep", AsyncMock()):
        c = make({"ramp_min": 1}, (now + timedelta(minutes=40)).isoformat())
        seen = {}
        orig = c._notify_main
        async def spy(*a, **k):
            seen["run_task_set"] = c._run_task is not None
            return await orig(*a, **k)
        c._notify_main = spy
        await c.async_start_run()
        assert seen.get("run_task_set") is True
        if c._run_task:
            await c._run_task
    # A live run blocks a second start; a stale prior-day flag does not.
    with patch.object(co, "async_track_point_in_time", return_value=lambda: None):
        c = make({}, (now + timedelta(minutes=40)).isoformat())
        c.async_start_run = AsyncMock()
        c.active = True; c._last_run_date = yesterday
        c._run_task = None; c._snooze_task = None
        c._reschedule(); c._handle_start(now); await asyncio.sleep(0)
        assert c.async_start_run.await_count == 1 and not c.last_skip_reason
        # live routine -> blocked
        c = make({}, (now + timedelta(minutes=40)).isoformat())
        c.async_start_run = AsyncMock()
        c._run_task = asyncio.ensure_future(asyncio.sleep(3600))
        c._reschedule(); c._handle_start(now); await asyncio.sleep(0)
        assert c.async_start_run.await_count == 0 and c.last_skip_reason == "a run is already active"
        c._run_task.cancel()
    # Dismiss stands the phone layer down for the day (#8 interaction)
    c = make({}, (now + timedelta(minutes=40)).isoformat())
    c.active = True; c._last_run_date = today
    for k in ("premute", "firing", "failsafe"):
        c._unsubs[k] = lambda: None
    await c.async_dismiss()
    assert c._dismissed_date == today
    assert all(c._unsubs[k] is None for k in ("premute", "firing", "failsafe"))
    assert not c._phone_layer_live()
    c.async_mute_phone = AsyncMock(); c.async_escalate = AsyncMock()
    c._handle_firing_time(now)
    for _ in range(3):
        await asyncio.sleep(0)
    assert c.async_mute_phone.await_count == 0 and c.async_escalate.await_count == 0
    print("issue2: ok")


async def awake():
    # Composite: unlocked + interactive + off charger + walking -> awake
    c = mk_awake(AWAKE_UP); c._steps_baseline = 1000
    assert c._is_awake()
    # On the charger -> not awake
    c = mk_awake({**AWAKE_UP, "binary_sensor.charge": "on"}); c._steps_baseline = 1000
    assert not c._is_awake()
    # Still, and steps not risen enough -> not awake
    c = mk_awake({**AWAKE_UP, "sensor.activity": "still", "sensor.steps": "1002"})
    c._steps_baseline = 1000
    assert not c._is_awake()
    # Steps risen >=5 (still activity) -> awake via steps
    c = mk_awake({**AWAKE_UP, "sensor.activity": "still", "sensor.steps": "1006"})
    c._steps_baseline = 1000
    assert c._is_awake()
    # Missing interactive sensor -> fails closed
    c = mk_awake({k: v for k, v in AWAKE_UP.items() if k != "binary_sensor.inter"})
    c._steps_baseline = 1000
    assert not c._is_awake()
    # Debounce + auto-dismiss while a run is active
    gate = Gate()
    with patch.object(co.asyncio, "sleep", gate):
        c = mk_awake(AWAKE_UP); c._steps_baseline = 1000; c.active = True
        c.async_dismiss = AsyncMock()
        c._handle_awake_change(MagicMock())
        assert c._awake_task is not None
        await gate.release()
        assert c.async_dismiss.await_count == 1 and c._awake_task is None
        # Awake drops during debounce -> cancelled, no dismiss
        c = mk_awake(AWAKE_UP); c._steps_baseline = 1000; c.active = True
        c.async_dismiss = AsyncMock()
        c._handle_awake_change(MagicMock())
        c.hass.states.get.side_effect = lambda eid: (
            _st("on") if eid == "binary_sensor.charge" else _st(AWAKE_UP.get(eid, ""))
        )
        c._handle_awake_change(MagicMock())
        await gate.release()
        assert c.async_dismiss.await_count == 0 and c._awake_task is None
        # Not awake while inactive: no debounce starts
        c = mk_awake(AWAKE_UP); c._steps_baseline = 1000; c.active = False
        c._handle_awake_change(MagicMock())
        assert c._awake_task is None
    print("awake: ok")


async def migration():
    import custom_components.sunrise_alarm as sa
    # Slug recovery from a wired companion sensor
    assert sa._phone_slug({"alarm_sensor": "sensor.s24u_next_alarm"}) == "s24u"
    assert sa._phone_slug({"phone_state_sensor": "sensor.pixel7_phone_state"}) == "pixel7"
    assert sa._phone_slug({}) is None
    # v1 -> v2 wires the derived sensors (those that exist) and enables the feature
    entry = MagicMock(); entry.version = 1
    entry.data = {"alarm_sensor": "sensor.s24u_next_alarm"}; entry.options = {}
    hass = MagicMock()
    captured = {}
    hass.config_entries.async_update_entry = lambda e, **kw: captured.update(kw)
    reg = MagicMock(); reg.async_get = lambda eid: object()  # everything exists
    with patch.object(sa.er, "async_get", return_value=reg):
        ok = await sa.async_migrate_entry(hass, entry)
    assert ok and captured.get("version") == 2
    o = captured["options"]
    assert o["awake_stop"] is True
    assert o["awake_locked_sensor"] == "binary_sensor.s24u_device_locked"
    assert o["awake_steps_sensor"] == "sensor.s24u_daily_steps"
    assert o["awake_activity_sensor"] == "sensor.s24u_detected_activity"
    # A sensor that doesn't exist is left unset (fail closed)
    entry2 = MagicMock(); entry2.version = 1
    entry2.data = {"alarm_sensor": "sensor.s24u_next_alarm"}; entry2.options = {}
    cap2 = {}
    hass.config_entries.async_update_entry = lambda e, **kw: cap2.update(kw)
    reg2 = MagicMock()
    reg2.async_get = lambda eid: None if "interactive" in eid else object()
    with patch.object(sa.er, "async_get", return_value=reg2):
        await sa.async_migrate_entry(hass, entry2)
    assert "awake_interactive_sensor" not in cap2["options"]
    assert cap2["options"]["awake_stop"] is True
    # Already v2 -> no-op
    entry3 = MagicMock(); entry3.version = 2
    assert await sa.async_migrate_entry(MagicMock(), entry3) is True
    print("migration: ok")


async def main():
    await migration()
    await scheduling()
    await notifications()
    await presence()
    await issue2()
    await awake()
    print("ALL SCENARIOS PASSED")


asyncio.run(main())
