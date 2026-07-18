"""Resolve a person's Companion (mobile_app) phone into notify + sensors.

Chain: person.<name> -> device_trackers -> entity registry (platform ==
"mobile_app", device_id) -> device registry -> notify service + the companion
sensors that share that device_id. Everything is best-effort: any field that
can't be resolved is simply left out, and the related feature stays dormant.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import slugify

from .const import (
    CONF_ALARM_SENSOR,
    CONF_ALARM_VOL_SENSOR,
    CONF_DND_SENSOR,
    CONF_LAST_NOTIF_SENSOR,
    CONF_LAST_REMOVED_SENSOR,
    CONF_NOTIFY,
    CONF_PHONE_STATE_SENSOR,
)

# Config key -> the mobile_app sensor entity_id suffix that carries that data.
_SENSOR_SUFFIXES: dict[str, str] = {
    CONF_ALARM_SENSOR: "next_alarm",
    CONF_DND_SENSOR: "do_not_disturb_sensor",
    CONF_ALARM_VOL_SENSOR: "volume_level_alarm",
    CONF_LAST_NOTIF_SENSOR: "last_notification",
    CONF_LAST_REMOVED_SENSOR: "last_removed_notification",
    CONF_PHONE_STATE_SENSOR: "phone_state",
}


@callback
def _mobile_device_ids(hass: HomeAssistant, person_entity: str) -> list[str]:
    """Return the mobile_app device ids behind a person's device_trackers."""
    state = hass.states.get(person_entity)
    if state is None:
        return []
    trackers = state.attributes.get("device_trackers") or []
    ent_reg = er.async_get(hass)
    device_ids: list[str] = []
    for tracker in trackers:
        entry = ent_reg.async_get(tracker)
        if entry and entry.platform == "mobile_app" and entry.device_id:
            if entry.device_id not in device_ids:
                device_ids.append(entry.device_id)
    return device_ids


@callback
def _resolve_notify(hass: HomeAssistant, name: str) -> str | None:
    """Map a device name to its mobile_app notify service, if present."""
    services = set(hass.services.async_services().get("notify", {}))
    slug = slugify(name)
    if not slug:
        return None
    exact = f"mobile_app_{slug}"
    if exact in services:
        return f"notify.{exact}"
    for svc in services:
        if svc.startswith("mobile_app_") and slug in svc:
            return f"notify.{svc}"
    return None


@callback
def resolve_person(hass: HomeAssistant, person_entity: str) -> dict[str, str]:
    """Return a config dict (notify + companion sensors) for a person.

    Prefers the device that exposes a next-alarm sensor (the phone). Returns an
    empty dict if the person has no resolvable mobile_app device.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    best: dict[str, str] = {}
    best_score = -1
    for device_id in _mobile_device_ids(hass, person_entity):
        device = dev_reg.async_get(device_id)
        if device is None:
            continue
        entities = er.async_entries_for_device(
            ent_reg, device_id, include_disabled_entities=True
        )
        found: dict[str, str] = {}
        for conf_key, suffix in _SENSOR_SUFFIXES.items():
            match = next(
                (
                    e.entity_id
                    for e in entities
                    if e.entity_id.startswith("sensor.")
                    and e.entity_id.endswith(f"_{suffix}")
                ),
                None,
            )
            if match:
                found[conf_key] = match
        name = device.name_by_user or device.name or ""
        notify = _resolve_notify(hass, name)
        if notify:
            found[CONF_NOTIFY] = notify
        # Score: the phone is the device that has a next-alarm sensor + notify.
        score = len(found) + (5 if CONF_ALARM_SENSOR in found else 0)
        if score > best_score:
            best_score = score
            best = found
    return best
