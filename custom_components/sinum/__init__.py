"""SINUM integráció: egy vezérlő = egy config entry = egy koordinátor."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SinumClient, normalize_host
from .const import CONF_IP, CONF_TOKEN, DOMAIN, PLATFORMS
from .coordinator import SinumConfigEntry, SinumCoordinator, SinumData
from .entity import (
    current_device_identifier,
    device_identifier,
    entity_unique_id,
    hub_device_info,
    module_device_info,
    module_of,
    thermostat_sensor_endpoints,
)

_LOGGER = logging.getLogger(__name__)

# A 2026.10 előtti verziók egyetlen, minden vezérlő által közösen használt eszköze
_LEGACY_DEVICE_IDENTIFIER = (DOMAIN, "all_in_one")


async def async_setup_entry(hass: HomeAssistant, entry: SinumConfigEntry) -> bool:
    client = SinumClient(
        async_get_clientsession(hass), entry.data[CONF_IP], entry.data[CONF_TOKEN]
    )
    coordinator = SinumCoordinator(hass, entry, client)
    # Hiba esetén ConfigEntryNotReady (újrapróbálás) vagy ConfigEntryAuthFailed (reauth)
    await coordinator.async_config_entry_first_refresh()

    await coordinator.async_load_metadata()

    _async_set_entry_unique_id(hass, entry, client.host)
    _async_migrate_legacy_registry(hass, entry, coordinator.data)

    entry.runtime_data = coordinator
    # A vezérlő eszköze előbb létezzen, mert a SINUM eszközök ehhez kapcsolódnak (via_device)
    hub = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id, **hub_device_info(entry))
    coordinator.hub_device_id = hub.id
    _async_migrate_to_module_devices(hass, entry, coordinator)
    if entry.minor_version < 2:
        _async_disable_thermostat_duplicates(hass, entry, coordinator)
        hass.config_entries.async_update_entry(entry, minor_version=2)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SinumConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: SinumConfigEntry, device_entry: DeviceEntry
) -> bool:
    """A vezérlőről már törölt eszköz kézzel eltávolítható; a még létező nem."""
    coordinator = entry.runtime_data
    current = {(DOMAIN, entry.entry_id)} | {
        current_device_identifier(coordinator, dev) for dev in coordinator.devices()
    }
    return not device_entry.identifiers & current


@callback
def _async_set_entry_unique_id(hass: HomeAssistant, entry: SinumConfigEntry, host: str) -> None:
    """A régi (unique_id nélküli) bejegyzések megkapják a host-ot azonosítónak."""
    if entry.unique_id is not None:
        return
    host = normalize_host(host)
    if any(e.unique_id == host for e in hass.config_entries.async_entries(DOMAIN)):
        return
    hass.config_entries.async_update_entry(entry, unique_id=host)


def _legacy_unique_ids(dev: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(platform, régi unique_id, új kulcs) hármasok egy eszközhöz.

    A régi azonosítók nem tartalmazták a vezérlőt (és helyenként az eszközosztályt sem),
    ezért két vezérlő entitásai ütköztek.
    """
    cls, dev_id, dev_type = dev["class"], dev["id"], dev.get("type")
    ids: list[tuple[str, str, str]] = []
    if cls == "virtual":
        if dev_type == "thermostat":
            ids += [
                ("climate", f"{DOMAIN}_{dev_id}_climate", "climate"),
                ("select", f"{DOMAIN}_{dev_id}_mode_select", "mode_select"),
                ("number", f"{DOMAIN}_all_in_one_{dev_id}_temp_set", "temp_set"),
            ]
            ids += [
                ("sensor", f"{DOMAIN}_{dev_id}_{key}", key)
                for key in ("temp", "humidity", "mode", "tempsetpoint")
            ]
        return ids

    by_type = {
        "relay": ("switch", f"{DOMAIN}_{cls}_{dev_id}_relay", "relay"),
        "blind_controller": ("cover", f"{DOMAIN}_{cls}_{dev_id}_cover", "cover"),
        "rgb_controller": ("light", f"{DOMAIN}_{cls}_{dev_id}_light", "light"),
        "motion_sensor": ("binary_sensor", f"{DOMAIN}_all_in_one_{dev_id}_motion_sensor", "motion_sensor"),
        "two_state_input_sensor": (
            "binary_sensor",
            f"{DOMAIN}_all_in_one_{dev_id}_two_state_input_sensor",
            "two_state_input_sensor",
        ),
        "analog_output": ("number", f"{DOMAIN}_all_in_one_{dev_id}_analog_output", "analog_output"),
        "pulse_width_modulation": ("number", f"{DOMAIN}_all_in_one_{dev_id}_pwm", "pwm"),
        "temperature_sensor": ("sensor", f"{DOMAIN}_{cls}_{dev_id}_temperature", "temperature"),
        "humidity_sensor": ("sensor", f"{DOMAIN}_{cls}_{dev_id}_humidity_sbuswtp", "humidity"),
        "light_sensor": ("sensor", f"{DOMAIN}_{cls}_{dev_id}_light", "illuminance"),
    }
    if dev_type in by_type:
        ids.append(by_type[dev_type])
    if "battery" in dev:
        ids.append(
            ("sensor", f"{DOMAIN}_battery_{dev.get('address', 'unknown_address')}_{dev_id}", "battery")
        )
    return ids


@callback
def _async_migrate_legacy_registry(
    hass: HomeAssistant, entry: SinumConfigEntry, data: SinumData
) -> None:
    """Régi unique_id-k és a közös eszköz átírása; az entity_id-k és az előzmények megmaradnak."""
    dev_reg = dr.async_get(hass)
    new_identifier = (DOMAIN, entry.entry_id)
    # Csak a bejegyzés saját eszközeit nézzük: az azonosító szerinti keresés
    # (async_get_device) a HA 2026.10-től elavult.
    devices = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    if not any(new_identifier in device.identifiers for device in devices):
        legacy_device = next(
            (d for d in devices if _LEGACY_DEVICE_IDENTIFIER in d.identifiers), None
        )
        if legacy_device is not None:
            dev_reg.async_update_device(legacy_device.id, new_identifiers={new_identifier})
            _LOGGER.info("Migrated legacy SINUM device to config entry %s", entry.entry_id)

    # Az osztály nélküli régi azonosítóknál (binary_sensor, number) az sbus eszköz
    # nyert, mert a régi kód sbus+wtp sorrendben hozta létre az entitásokat.
    mapping: dict[tuple[str, str], str] = {}
    for cls in ("sbus", "wtp", "virtual"):
        for dev in data.get(cls, {}).values():
            for platform, old_uid, key in _legacy_unique_ids(dev):
                mapping.setdefault(
                    (platform, old_uid), entity_unique_id(entry.entry_id, cls, dev["id"], key)
                )

    ent_reg = er.async_get(hass)
    migrated = 0
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        new_uid = mapping.get((ent.domain, ent.unique_id))
        if new_uid is None or ent_reg.async_get_entity_id(ent.domain, DOMAIN, new_uid):
            continue
        ent_reg.async_update_entity(ent.entity_id, new_unique_id=new_uid)
        migrated += 1
    if migrated:
        _LOGGER.info("Migrated %d SINUM entity unique IDs", migrated)


@callback
def _async_migrate_to_module_devices(
    hass: HomeAssistant, entry: SinumConfigEntry, coordinator: SinumCoordinator
) -> None:
    """A korábbi, végpontonkénti HA eszközök a fizikai modul eszközébe olvadnak.

    Az entitások (a letiltottak is) átkerülnek a modul eszközére, így az entity_id-k
    és az előzmények megmaradnak; az új eszköz a régiek területét kapja (elsősorban
    a termosztátét), az üres régi eszközök törlődnek.
    """
    dev_reg = dr.async_get(hass)
    ent_reg = er.async_get(hass)
    by_identifier = {
        identifier: device
        for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
        for identifier in device.identifiers
    }
    old_by_module: dict[tuple[str, int], list[DeviceEntry]] = {}
    # A termosztát előre kerül, hogy az ő területe legyen az elsődleges
    for dev in sorted(coordinator.devices(), key=lambda d: d["class"] != "virtual"):
        module = module_of(coordinator, dev)
        old = by_identifier.get(device_identifier(entry.entry_id, dev["class"], dev["id"]))
        if module is not None and old is not None:
            old_by_module.setdefault(module, []).append(old)

    for module, old_devices in old_by_module.items():
        info = module_device_info(coordinator, module)
        is_new = not info["identifiers"] & by_identifier.keys()
        new = dev_reg.async_get_or_create(config_entry_id=entry.entry_id, **info)
        area_id = next((d.area_id for d in old_devices if d.area_id), None)
        if is_new and area_id is not None and new.area_id != area_id:
            dev_reg.async_update_device(new.id, area_id=area_id)
        for old in old_devices:
            for ent in er.async_entries_for_device(ent_reg, old.id, include_disabled_entities=True):
                ent_reg.async_update_entity(ent.entity_id, device_id=new.id)
            dev_reg.async_remove_device(old.id)
    if old_by_module:
        _LOGGER.info(
            "Merged %d SINUM devices into %d physical modules",
            sum(map(len, old_by_module.values())),
            len(old_by_module),
        )


def _async_disable_thermostat_duplicates(
    hass: HomeAssistant, entry: SinumConfigEntry, coordinator: SinumCoordinator
) -> None:
    """Egyszeri: a termosztát által is mutatott panelérzékelők letiltása.

    Az újonnan létrejövők eleve letiltva jönnek létre; a korábbiakat egyszer tiltjuk
    le, utána a felhasználó által újra engedélyezettek engedélyezve maradnak.
    """
    ent_reg = er.async_get(hass)
    keys = {"temperature_sensor": "temperature", "humidity_sensor": "humidity"}
    disabled = 0
    for cls, dev_id in thermostat_sensor_endpoints(coordinator):
        if (key := keys.get(str(coordinator.data[cls][dev_id].get("type")))) is None:
            continue
        unique_id = entity_unique_id(entry.entry_id, cls, dev_id, key)
        entity_id = ent_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
        if entity_id is None or (ent := ent_reg.async_get(entity_id)) is None or ent.disabled_by:
            continue
        ent_reg.async_update_entity(entity_id, disabled_by=er.RegistryEntryDisabler.INTEGRATION)
        disabled += 1
    if disabled:
        _LOGGER.info("Disabled %d SINUM panel sensors that their thermostat already shows", disabled)
