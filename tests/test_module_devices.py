"""Fizikai modulonként egy HA eszköz; a termosztát a szobai panelje eszközére kerül."""
import pytest
from homeassistant.helpers import area_registry as ar, device_registry as dr, entity_registry as er

from custom_components.sinum import async_remove_config_entry_device
from custom_components.sinum.diagnostics import async_get_config_entry_diagnostics

from .common import ents, make_entry, setup
from .conftest import _devices

ROOM = {"room_id": 3}
SBUS = [
    # R-S3 szobai panel (parent 50)
    {"id": 20, "class": "sbus", "type": "temperature_sensor", "name": "Földszint szoba hőmérséklet",
     "temperature": 215, "address": 300, "parent_id": 50, "software_version": "R-S3 v1.2.7", **ROOM},
    {"id": 21, "class": "sbus", "type": "humidity_sensor", "name": "Földszint szoba páratartalom",
     "humidity": 455, "address": 300, "parent_id": 50, "software_version": "R-S3 v1.2.7", **ROOM},
    {"id": 22, "class": "sbus", "type": "temperature_regulator", "name": "Földszint szoba szabályzó",
     "address": 300, "parent_id": 50, "software_version": "R-S3 v1.2.7",
     "user_menu_lock": {"pin_code": "1234"}, **ROOM},
    # PS-08m relémodul (parent 60)
    {"id": 30, "class": "sbus", "type": "relay", "name": "Nappali fűtés", "state": False,
     "address": 400, "parent_id": 60, "software_version": "PS-08m v2.0.1", "room_id": 4},
    {"id": 31, "class": "sbus", "type": "relay", "name": "Fürdő fűtés", "state": True,
     "address": 400, "parent_id": 60, "software_version": "PS-08m v2.0.1", "room_id": 4},
    # modul nélküli eszköz: marad a saját eszközén
    {"id": 40, "class": "sbus", "type": "relay", "name": "Kapu", "state": False, "address": 500},
]
VIRTUAL = [
    {"id": 2, "class": "virtual", "type": "thermostat", "name": "Földszint szoba termosztát", "mode": "heating",
     "state": False, "temperature": 0, "humidity": 0, "target_temperature": 215,
     "target_temperature_minimum": 50, "target_temperature_maximum": 350, "parent_id": None,
     "associations": {"temperature_regulator": {"class": "sbus", "id": 22},
                      "room_temperature_sensor": {"class": "sbus", "id": 20}},
     **ROOM},
    # hozzárendelés nélküli termosztát: saját eszköz
    {"id": 3, "class": "virtual", "type": "thermostat", "name": "Pince", "mode": "off", "state": False,
     "temperature": 0, "humidity": 0, "target_temperature": 180, "associations": {}},
]
ROOMS = {"data": [{"id": 3, "name": "Földszint szoba"}, {"id": 4, "name": "Kazánház"}]}
PARENTS = {"data": [
    {"id": 50, "name": "R-S3", "model": "R-S3", "version": "R-S3 v1.2.7", "class": "sbus", "devices": [20, 21, 22]},
    {"id": 60, "name": "Kazánház relék", "model": "PS-08m", "version": "2.0.1", "class": "sbus", "devices": [30, 31]},
]}


@pytest.fixture
def api_data():
    return {"sbus": _devices(SBUS), "wtp": [], "virtual": _devices(VIRTUAL)}


def _routes(mock_api, parents=True):
    mock_api.add(r"/rooms$", method="GET", payload=ROOMS)
    if parents:
        mock_api.add(r"/parent-devices/sbus$", method="GET", payload=PARENTS)


def _entity(hass, entry, suffix):
    uid = f"{entry.entry_id}_{suffix}"
    return next(e for e in ents(hass, entry) if e.unique_id == uid)


def _module(hass, entry, parent_id):
    ident = ("sinum", f"{entry.entry_id}_sbus_module_{parent_id}")
    return next(
        (d for d in dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id) if ident in d.identifiers),
        None,
    )


def _name(hass, entity):
    return hass.states.get(entity.entity_id).attributes["friendly_name"]


async def test_module_groups_endpoints_and_thermostat(hass, mock_api):
    _routes(mock_api)
    entry = make_entry(hass)
    await setup(hass, entry)

    panel = _module(hass, entry, 50)
    assert panel.name == "Földszint szoba"
    assert panel.model == "SBUS R-S3"
    assert panel.sw_version == "1.2.7"
    assert panel.area_id == ar.async_get(hass).async_get_area_by_name("Földszint szoba").id
    on_panel = {
        e.unique_id.removeprefix(f"{entry.entry_id}_")
        for e in er.async_entries_for_device(er.async_get(hass), panel.id, include_disabled_entities=True)
    }
    assert {"sbus_20_temperature", "sbus_21_humidity", "virtual_2_climate", "virtual_2_temp",
            "virtual_2_humidity", "virtual_2_mode_select"} <= on_panel

    assert _name(hass, _entity(hass, entry, "sbus_20_temperature")) == "Földszint szoba Hőmérséklet"
    assert _name(hass, _entity(hass, entry, "sbus_21_humidity")) == "Földszint szoba Páratartalom"
    assert _name(hass, _entity(hass, entry, "virtual_2_climate")) == "Földszint szoba"
    assert _name(hass, _entity(hass, entry, "virtual_2_temp")) == "Földszint szoba Thermostat temperature"
    assert _name(hass, _entity(hass, entry, "virtual_2_humidity")) == "Földszint szoba Thermostat humidity"

    relays = _module(hass, entry, 60)
    assert relays.name == "Kazánház relék"
    assert relays.model == "SBUS PS-08m"
    assert _name(hass, _entity(hass, entry, "sbus_30_relay")) == "Kazánház relék Nappali fűtés"
    assert _entity(hass, entry, "sbus_31_relay").device_id == relays.id

    # modul nélküli eszközök: a régi, eszközönkénti HA eszköz
    gate = _entity(hass, entry, "sbus_40_relay")
    assert dr.async_get(hass).async_get(gate.device_id).name == "Kapu"
    assert _name(hass, gate) == "Kapu"
    cellar = _entity(hass, entry, "virtual_3_temp")
    assert _name(hass, cellar) == "Pince Temperature"

    # vezérlő + 2 modul + 2 modul nélküli eszköz
    assert len(dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)) == 5


async def test_module_without_parent_endpoint_falls_back(hass, mock_api):
    """Régebbi vezérlő /parent-devices nélkül: modell és verzió a végpont szoftververziójából."""
    _routes(mock_api, parents=False)
    entry = make_entry(hass)
    await setup(hass, entry)
    relays = _module(hass, entry, 60)
    assert relays.name == "PS-08m"
    assert relays.model == "SBUS PS-08m"
    assert relays.sw_version == "2.0.1"
    assert relays.area_id == ar.async_get(hass).async_get_area_by_name("Kazánház").id
    assert _module(hass, entry, 50).name == "Földszint szoba"


async def test_old_per_endpoint_devices_are_merged(hass, mock_api, caplog):
    """A korábbi eszközök entitásai (a letiltottak is) átkerülnek; az entity_id-k maradnak."""
    _routes(mock_api)
    entry = make_entry(hass)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    area = ar.async_get(hass).async_create("Emelet")
    old = {}
    for cls, dev_id in (("sbus", 20), ("sbus", 21), ("virtual", 2)):
        old[(cls, dev_id)] = dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={("sinum", f"{entry.entry_id}_{cls}_{dev_id}")}, name=f"old {dev_id}"
        )
    dev_reg.async_update_device(old[("virtual", 2)].id, area_id=area.id)
    ent_reg.async_get_or_create(
        "sensor", "sinum", f"{entry.entry_id}_sbus_20_temperature", config_entry=entry,
        device_id=old[("sbus", 20)].id, suggested_object_id="regi_homerseklet",
    )
    ent_reg.async_get_or_create(
        "sensor", "sinum", f"{entry.entry_id}_virtual_2_mode", config_entry=entry,
        device_id=old[("virtual", 2)].id, suggested_object_id="regi_mod",
        disabled_by=er.RegistryEntryDisabler.INTEGRATION,
    )

    await setup(hass, entry)

    panel = _module(hass, entry, 50)
    # a felhasználó által választott terület öröklődik, nem a SINUM szobáé
    assert panel.area_id == area.id
    for device in old.values():
        assert dev_reg.async_get(device.id) is None
    temp = ent_reg.async_get("sensor.regi_homerseklet")
    assert temp.device_id == panel.id
    assert hass.states.get("sensor.regi_homerseklet").state == "21.5"
    assert ent_reg.async_get("sensor.regi_mod").device_id == panel.id
    # a HA 2026.10-ben elavult eszközregiszter-hívások nélkül
    assert "Detected that custom integration 'sinum'" not in caplog.text


async def test_module_device_cannot_be_removed(hass, mock_api, api_data):
    _routes(mock_api)
    entry = make_entry(hass)
    await setup(hass, entry)
    panel = _module(hass, entry, 50)
    assert not await async_remove_config_entry_device(hass, entry, panel)


async def test_diagnostics_lists_modules_and_hides_pin(hass, mock_api):
    _routes(mock_api)
    entry = make_entry(hass)
    await setup(hass, entry)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["parents"]["sbus_60"]["model"] == "PS-08m"
    assert "devices" not in diag["parents"]["sbus_60"]
    assert diag["devices"]["sbus"][22]["user_menu_lock"]["pin_code"] == "**REDACTED**"
    assert "1234" not in str(diag)
