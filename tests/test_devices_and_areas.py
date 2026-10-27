"""Phase 3: per-device HA devices, areas, region units, dynamic/stale devices, diagnostics, defaults."""
import pytest
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM

from custom_components.sinum import async_remove_config_entry_device
from custom_components.sinum.diagnostics import async_get_config_entry_diagnostics

from .common import ents, make_entry, setup, tick as _tick

DOMAIN = "sinum"


def _by_ident(hass, entry, ident):
    # Verziófüggetlen: az async_get_device(identifiers=) a HA 2026.10-ben elavult
    devs = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    return next((d for d in devs if (DOMAIN, ident) in d.identifiers), None)


def _device(hass, entry, cls, dev_id):
    return _by_ident(hass, entry, f"{entry.entry_id}_{cls}_{dev_id}")


def _uid(entry, key):
    return f"{entry.entry_id}_{key}"


async def test_P3_device_per_sinum_device(hass, mock_api, api_data):
    entry = make_entry(hass)
    await setup(hass, entry)
    dev_reg, ent_reg = dr.async_get(hass), er.async_get(hass)
    hub = _by_ident(hass, entry, entry.entry_id)
    assert hub is not None and hub.via_device_id is None
    n = sum(len(api_data[c]) for c in ("sbus", "wtp", "virtual"))
    devs = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    assert len(devs) == n + 1
    assert all(d.via_device_id == hub.id for d in devs if d.id != hub.id)

    relay = _device(hass, entry, "sbus", 1)
    assert (relay.name, relay.manufacturer, relay.model, relay.sw_version) == (
        "Relay A", "SINUM", "SBUS relay", "SBUS-R v1")
    # minden entitás a saját eszközén, a vezérlőn nincs entitás
    assert not er.async_entries_for_device(ent_reg, hub.id)
    for ent in ents(hass, entry):
        dev = dev_reg.async_get(ent.device_id)
        cls, dev_id = ent.unique_id.removeprefix(entry.entry_id + "_").split("_")[:2]
        assert dev.identifiers == {(DOMAIN, f"{entry.entry_id}_{cls}_{dev_id}")}, ent.entity_id


async def test_P3_same_id_in_two_classes_are_separate_devices(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    assert _device(hass, entry, "sbus", 1).id != _device(hass, entry, "wtp", 1).id
    assert _device(hass, entry, "sbus", 5).name == "Motion A"
    assert _device(hass, entry, "wtp", 5).name == "Motion W"


async def test_P3_readable_names(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    ent_reg = er.async_get(hass)

    def name(key):
        entity_id = ent_reg.async_get_entity_id(key.split(":")[0], DOMAIN, _uid(entry, key.split(":")[1]))
        return hass.states.get(entity_id).attributes["friendly_name"]

    assert name("switch:sbus_1_relay") == "Relay A"
    assert name("climate:virtual_1_climate") == "Nappali"
    assert name("sensor:virtual_1_temp") == "Nappali Temperature"
    assert name("sensor:sbus_2_temperature") == "Temp A"
    assert name("sensor:wtp_11_battery") == "Temp W Battery"


async def test_P3_unnamed_device_gets_type_name(hass, mock_api, api_data):
    api_data["sbus"][0]["name"] = ""
    entry = make_entry(hass)
    await setup(hass, entry)
    assert _device(hass, entry, "sbus", 1).name == "Relay 1"


async def test_P3_areas_from_rooms(hass, mock_api, api_data):
    api_data["virtual"][0]["room_id"] = 3
    api_data["sbus"][0]["room_id"] = 4
    api_data["sbus"][1]["room_id"] = 99  # ismeretlen szoba
    mock_api.add(r"/rooms$", method="GET", payload={"data": [
        {"id": 3, "name": "Nappali"}, {"id": 4, "name": "Kazánház"}, {"id": 5, "name": ""}]})
    entry = make_entry(hass)
    await setup(hass, entry)
    area_reg = ar.async_get(hass)
    assert area_reg.async_get_area(_device(hass, entry, "virtual", 1).area_id).name == "Nappali"
    assert area_reg.async_get_area(_device(hass, entry, "sbus", 1).area_id).name == "Kazánház"
    assert _device(hass, entry, "sbus", 2).area_id is None
    assert _device(hass, entry, "wtp", 1).area_id is None


async def test_P3_user_area_not_overwritten(hass, mock_api, api_data):
    api_data["sbus"][0]["room_id"] = 4
    mock_api.add(r"/rooms$", method="GET", payload={"data": [{"id": 4, "name": "Kazánház"}]})
    entry = make_entry(hass)
    await setup(hass, entry)
    garage = ar.async_get(hass).async_create("Garázs")
    dev_reg = dr.async_get(hass)
    dev_reg.async_update_device(_device(hass, entry, "sbus", 1).id, area_id=garage.id)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _device(hass, entry, "sbus", 1).area_id == garage.id


async def test_P3_rooms_auth_error_starts_reauth(hass, mock_api):
    mock_api.add(r"/rooms$", method="GET", status=401, payload={})
    entry = make_entry(hass)
    await setup(hass, entry)
    flows = hass.config_entries.flow.async_progress()
    assert any(f["context"].get("source") == "reauth" for f in flows)


async def test_P3_region_eu_defaults(hass, mock_api):
    mock_api.add(r"/settings/locale$", method="GET", payload={"data": {"region": "eu"}})
    entry = make_entry(hass)
    await setup(hass, entry)
    assert entry.runtime_data.region == "eu"
    st = hass.states.get("sensor.lux_a")
    assert st.state == "300" and st.attributes["unit_of_measurement"] == "lx"
    assert hass.states.get("sensor.temp_a").attributes["unit_of_measurement"] == UnitOfTemperature.CELSIUS


async def test_P3_region_us_units(hass, mock_api, api_data):
    hass.config.units = US_CUSTOMARY_SYSTEM
    api_data["sbus"][1]["temperature"] = 720  # 72,0 °F
    api_data["virtual"][0]["temperature"] = 700
    mock_api.add(r"/settings/locale$", method="GET", payload={"data": {"region": "us"}})
    entry = make_entry(hass)
    await setup(hass, entry)
    st = hass.states.get("sensor.temp_a")
    assert st.attributes["unit_of_measurement"] == UnitOfTemperature.FAHRENHEIT
    assert float(st.state) == 72.0  # a 100-as (°C) felső határ nem vágja le
    climate = hass.states.get("climate.nappali")
    assert climate.attributes["current_temperature"] == 70.0
    lux = hass.states.get("sensor.lux_a")  # 300 fc
    assert lux.attributes["unit_of_measurement"] == "lx"
    assert float(lux.state) == pytest.approx(3229.17, abs=0.5)


async def test_P3_unknown_region_falls_back_to_eu(hass, mock_api):
    mock_api.add(r"/settings/locale$", method="GET", payload={"data": {"region": "mars"}})
    entry = make_entry(hass)
    await setup(hass, entry)
    assert entry.runtime_data.region == "eu"


async def test_P3_redundant_entities_disabled_by_default(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    disabled = {e.unique_id.removeprefix(entry.entry_id + "_") for e in ents(hass, entry) if e.disabled_by}
    assert disabled == {"virtual_1_mode", "virtual_1_mode_select", "virtual_1_temp_set", "virtual_1_tempsetpoint"}
    assert all(e.disabled_by is er.RegistryEntryDisabler.INTEGRATION
               for e in ents(hass, entry) if e.disabled_by)


async def test_P3_existing_enabled_entity_stays_enabled(hass, mock_api):
    entry = make_entry(hass)
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create("select", DOMAIN, _uid(entry, "virtual_1_mode_select"),
                                config_entry=entry, suggested_object_id="nappali_mode_select")
    await setup(hass, entry)
    assert ent_reg.async_get("select.nappali_mode_select").disabled_by is None
    assert hass.states.get("select.nappali_mode_select").state == "heating"


async def test_P3_new_device_added_without_reload(hass, mock_api, api_data):
    entry = make_entry(hass)
    await setup(hass, entry)
    before = len(ents(hass, entry))
    api_data["sbus"].append({"id": 20, "class": "sbus", "type": "relay", "name": "Új relé", "state": True,
                             "address": 300, "status": "online", "messages": [], "labels": []})
    await _tick(hass, 3)
    assert len(ents(hass, entry)) == before + 1
    assert _device(hass, entry, "sbus", 20).name == "Új relé"
    entity_id = er.async_get(hass).async_get_entity_id("switch", DOMAIN, _uid(entry, "sbus_20_relay"))
    assert hass.states.get(entity_id).state == "on"
    # a következő körben nem jön létre duplikátum
    await _tick(hass, 3)
    assert len(ents(hass, entry)) == before + 1


async def test_P3_stale_device_can_be_removed(hass, mock_api, api_data):
    entry = make_entry(hass)
    await setup(hass, entry)
    hub = _by_ident(hass, entry, entry.entry_id)
    relay = _device(hass, entry, "sbus", 1)
    assert not await async_remove_config_entry_device(hass, entry, hub)
    assert not await async_remove_config_entry_device(hass, entry, relay)
    del api_data["sbus"][0]
    await _tick(hass, 3)
    assert await async_remove_config_entry_device(hass, entry, relay)
    # a többi eszköz továbbra sem törölhető
    assert not await async_remove_config_entry_device(hass, entry, _device(hass, entry, "wtp", 1))


async def test_P3_diagnostics_redacted(hass, mock_api, api_data):
    entry = make_entry(hass, ip="192.168.1.50", token="secret-token")
    await setup(hass, entry)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    text = repr(diag)
    assert "secret-token" not in text and "192.168.1.50" not in text
    assert diag["entry"]["data"] == {"ip": "**REDACTED**", "token": "**REDACTED**"}
    assert diag["region"] == "eu" and diag["last_update_success"] is True
    assert diag["devices"]["sbus"][1]["name"] == "Relay A"


async def test_P3_entity_ids_kept_after_split(hass, mock_api):
    """Meglévő telepítés: az eszközszétválasztás nem változtatja meg az entity_id-ket."""
    entry = make_entry(hass)
    ent_reg = er.async_get(hass)
    old = {
        ("switch", "sbus_1_relay"): "switch.sinum_all_in_one_relay_a_switch",
        ("climate", "virtual_1_climate"): "climate.nappali_climate",
        ("sensor", "virtual_1_temp"): "sensor.nappali_temp",
        ("sensor", "wtp_11_battery"): "sensor.sinum_all_in_one_temp_w_battery",
    }
    hub = dr.async_get(hass).async_get_or_create(config_entry_id=entry.entry_id,
                                                 identifiers={(DOMAIN, entry.entry_id)}, name="SINUM All-in-One")
    for (platform, key), entity_id in old.items():
        ent_reg.async_get_or_create(platform, DOMAIN, _uid(entry, key), config_entry=entry, device_id=hub.id,
                                    suggested_object_id=entity_id.split(".", 1)[1])
    await setup(hass, entry)
    for (platform, key), entity_id in old.items():
        assert ent_reg.async_get_entity_id(platform, DOMAIN, _uid(entry, key)) == entity_id
        assert hass.states.get(entity_id) is not None
        assert ent_reg.async_get(entity_id).device_id != hub.id


async def test_foreign_class_devices_ignored(hass, mock_api, api_data):
    """A vezérlő a /devices/wtp-re néha az SBUS listát adja: ebből nem lehet WTP eszköz."""
    entry = make_entry(hass)
    await setup(hass, entry)
    devices_before = len(dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id))
    entities_before = len(ents(hass, entry))
    mock_api.add(r"/devices/wtp$", method="GET", payload={"data": api_data["sbus"]})
    await _tick(hass, 3)
    assert len(dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)) == devices_before
    assert len(ents(hass, entry)) == entities_before
    assert _device(hass, entry, "wtp", 10) is None  # az SBUS PWM (id 10) nem lett WTP eszköz
    assert entry.runtime_data.devices("wtp") == []


async def test_foreign_class_devices_ignored_at_setup(hass, mock_api, api_data):
    mock_api.add(r"/devices/wtp$", method="GET", payload={"data": api_data["sbus"]})
    entry = make_entry(hass)
    await setup(hass, entry)
    assert not [e for e in ents(hass, entry) if "_wtp_" in e.unique_id]
    assert _device(hass, entry, "wtp", 1) is None
