"""Koordinátor, elérhetőség, config flow, régi regiszter migrációja."""
import json
from pathlib import Path

import pytest
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import count_calls
from .common import eid, ents, make_entry, setup, tick as _tick

DOMAIN = "sinum"
FIXTURES = Path(__file__).parent / "fixtures"
RELAY = "switch.sinum_all_in_one_relay_a_switch"
CLIMATE = "climate.nappali_climate"


# ------------------------------------------------------------ setup / availability
@pytest.mark.parametrize("mode", ["conn", "timeout", "500"])
async def test_P1_setup_retries_when_controller_down(hass, mock_api, mode):
    mock_api.state["fail"] = mode
    entry = make_entry(hass)
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert ents(hass, entry) == []


async def test_P1_setup_bad_token_starts_reauth(hass, mock_api):
    mock_api.state["fail"] = "401"
    entry = make_entry(hass)
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_P1_outage_marks_unavailable_and_recovers(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    relay = eid(hass, RELAY)
    assert hass.states.get(relay).state == "on"
    mock_api.state["fail"] = "conn"
    await _tick(hass, 3)
    assert hass.states.get(relay).state == STATE_UNAVAILABLE
    assert hass.states.get(eid(hass, CLIMATE)).state == STATE_UNAVAILABLE
    mock_api.state["fail"] = None
    await _tick(hass, 6)
    assert hass.states.get(relay).state == "on"


async def test_P1_offline_device_unavailable(hass, mock_api, api_data):
    api_data["sbus"][0]["status"] = "offline"
    entry = make_entry(hass)
    await setup(hass, entry)
    assert hass.states.get(eid(hass, RELAY)).state == STATE_UNAVAILABLE
    assert hass.states.get(eid(hass, "light.sinum_all_in_one_led_light")).state == "on"


async def test_P1_removed_device_unavailable(hass, mock_api, api_data):
    entry = make_entry(hass)
    await setup(hass, entry)
    del api_data["sbus"][0]
    await _tick(hass, 3)
    assert hass.states.get(eid(hass, RELAY)).state == STATE_UNAVAILABLE


async def test_P1_polling_load(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    # egy kör (sbus + wtp + virtual) + szobák, modulok (sbus + wtp) és régió a beállításkor
    assert count_calls(mock_api) == 7
    start = count_calls(mock_api)
    for _ in range(30):
        await _tick(hass, 2)
    per_minute = count_calls(mock_api) - start
    assert per_minute <= 100, per_minute  # korábban ~950


# ------------------------------------------------------------ multiple controllers
async def test_P1_two_controllers_no_unique_id_clash(hass, mock_api, caplog):
    e1 = make_entry(hass, ip="192.168.1.50")
    e2 = make_entry(hass, ip="192.168.1.51")
    await setup(hass, e1)  # az integráció betöltése mindkét bejegyzést felállítja
    assert e1.state is e2.state is ConfigEntryState.LOADED
    assert len(ents(hass, e1)) == len(ents(hass, e2)) > 20
    assert not [r for r in caplog.records if "does not generate unique IDs" in r.getMessage()]
    dev_reg = dr.async_get(hass)
    per_entry = [dr.async_entries_for_config_entry(dev_reg, e.entry_id) for e in (e1, e2)]
    assert len(per_entry[0]) == len(per_entry[1]) > 2  # vezérlő + eszközönként egy
    assert not {d.id for d in per_entry[0]} & {d.id for d in per_entry[1]}
    hubs = [d for devs in per_entry for d in devs if d.via_device_id is None]
    assert {next(iter(d.identifiers))[1] for d in hubs} == {e1.entry_id, e2.entry_id}


async def test_P1_legacy_entry_gets_unique_id(hass, mock_api):
    entry = make_entry(hass, ip="192.168.1.50")
    assert entry.unique_id is None
    await setup(hass, entry)
    assert entry.unique_id == "192.168.1.50"


# ------------------------------------------------------------ commands
async def test_P1_command_connection_error_raises(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    mock_api.state["fail"] = "conn"

    def boom(url, json=None):
        import aiohttp
        raise aiohttp.ClientConnectionError("refused")

    mock_api.add(r"/command/turn_off", method="POST", callback=boom)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("switch", "turn_off", {"entity_id": eid(hass, RELAY)}, blocking=True)


async def test_P1_command_wire_format_unchanged(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    for method in ("POST", "PATCH"):
        mock_api.add(r"/devices/", method=method, status=200, payload={"data": {}})
    mock_api.calls.clear()
    await hass.services.async_call("switch", "turn_off", {"entity_id": eid(hass, RELAY)}, blocking=True)
    await hass.services.async_call("climate", "set_temperature", {"entity_id": eid(hass, CLIMATE), "temperature": 22.5}, blocking=True)
    await hass.services.async_call("cover", "set_cover_position",
                                   {"entity_id": eid(hass, "cover.sinum_all_in_one_blind_cover"), "position": 30}, blocking=True)
    await hass.services.async_call("number", "set_value",
                                   {"entity_id": eid(hass, "number.sinum_all_in_one_pwm_pwm"), "value": 40}, blocking=True)
    writes = [(m, u.split("/api/v1")[1], js) for m, u, js in mock_api.calls if m != "GET"]
    assert ("POST", "/devices/sbus/1/command/turn_off", {}) in writes
    assert ("PATCH", "/devices/virtual/1", {"id": 1, "target_temperature": 225}) in writes
    assert ("PATCH", "/devices/sbus/8", {"id": 8, "target_opening": 30}) in writes
    assert ("POST", "/devices/sbus/10/command/set_duty_cycle", {"set_duty_cycle": 40}) in writes


async def test_P1_cp1250_names_decoded(hass, mock_api, api_data):
    body = json.dumps({"data": [dict(api_data["virtual"][0], name="Fürdőszoba")]}, ensure_ascii=False).encode("cp1250")
    mock_api.add(r"/devices/virtual$", method="GET", status=200, payload=body)
    entry = make_entry(hass)
    await setup(hass, entry)
    names = [s.attributes.get("friendly_name") for s in hass.states.async_all("climate")]
    assert any("fürdőszoba" in (n or "").lower() for n in names), names


# ------------------------------------------------------------ config flow
async def _start(hass):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.FORM
    return r["flow_id"]


async def test_P1_flow_success_with_hostname_and_url(hass, mock_api):
    fid = await _start(hass)
    r = await hass.config_entries.flow.async_configure(fid, {"ip": "http://Sinum.local:8080/api/v1", "token": " tok "})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"] == {"ip": "sinum.local:8080", "token": "tok"}
    assert r["result"].unique_id == "sinum.local:8080"
    assert any("sinum.local:8080/api/v1/devices/virtual" in u for _, u, _ in mock_api.calls)


@pytest.mark.parametrize(("mode", "error"), [("401", "invalid_auth"), ("conn", "cannot_connect"), ("500", "invalid_response")])
async def test_P1_flow_errors(hass, mock_api, mode, error):
    mock_api.state["fail"] = mode
    fid = await _start(hass)
    r = await hass.config_entries.flow.async_configure(fid, {"ip": "192.168.1.50", "token": "x"})
    assert r["type"] is FlowResultType.FORM
    assert r["errors"] == {"base": error}


async def test_P1_flow_duplicate_aborts(hass, mock_api):
    MockConfigEntry(domain=DOMAIN, unique_id="192.168.1.50", data={"ip": "192.168.1.50", "token": "t"}).add_to_hass(hass)
    fid = await _start(hass)
    r = await hass.config_entries.flow.async_configure(fid, {"ip": "192.168.1.50", "token": "x"})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "already_configured"


async def test_P1_reauth_updates_token(hass, mock_api):
    mock_api.state["fail"] = "401"
    entry = make_entry(hass)
    await setup(hass, entry)
    flow = hass.config_entries.flow.async_progress_by_handler(DOMAIN)[0]
    mock_api.state["fail"] = None
    r = await hass.config_entries.flow.async_configure(flow["flow_id"], {"token": "newtok"})
    await hass.async_block_till_done()
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "reauth_successful"
    assert entry.data["token"] == "newtok"
    assert entry.state is ConfigEntryState.LOADED


async def test_P1_reconfigure_changes_host(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    r = await entry.start_reconfigure_flow(hass)
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {"ip": "192.168.1.99", "token": "tok"})
    await hass.async_block_till_done()
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "reconfigure_successful"
    assert entry.data["ip"] == "192.168.1.99" and entry.unique_id == "192.168.1.99"


# ------------------------------------------------------------ registry migration
LEGACY = {
    # (platform, legacy unique_id) -> entity_id the user had
    ("switch", "sinum_sbus_1_relay"): "switch.my_relay",
    ("switch", "sinum_wtp_1_relay"): "switch.my_wtp_relay",
    ("climate", "sinum_1_climate"): "climate.my_thermostat",
    ("select", "sinum_1_mode_select"): "select.my_mode",
    ("number", "sinum_all_in_one_1_temp_set"): "number.my_setpoint",
    ("number", "sinum_all_in_one_10_pwm"): "number.my_pwm",
    ("number", "sinum_all_in_one_9_analog_output"): "number.my_ao",
    ("cover", "sinum_sbus_8_cover"): "cover.my_blind",
    ("light", "sinum_sbus_7_light"): "light.my_led",
    ("binary_sensor", "sinum_all_in_one_5_motion_sensor"): "binary_sensor.my_motion",
    ("binary_sensor", "sinum_all_in_one_6_two_state_input_sensor"): "binary_sensor.my_input",
    ("sensor", "sinum_1_temp"): "sensor.my_room_temp",
    ("sensor", "sinum_1_tempsetpoint"): "sensor.my_room_setpoint",
    ("sensor", "sinum_sbus_2_temperature"): "sensor.my_temp",
    ("sensor", "sinum_sbus_3_humidity_sbuswtp"): "sensor.my_hum",
    ("sensor", "sinum_sbus_4_light"): "sensor.my_lux",
    ("sensor", "sinum_battery_202_11"): "sensor.my_battery",
}


async def test_P1_legacy_registry_migrated(hass, mock_api):
    entry = make_entry(hass)
    dev_reg = dr.async_get(hass)
    legacy_dev = dev_reg.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "all_in_one")},
                                             name="SINUM All-in-One")
    ent_reg = er.async_get(hass)
    for (platform, uid), entity_id in LEGACY.items():
        ent_reg.async_get_or_create(platform, DOMAIN, uid, config_entry=entry, device_id=legacy_dev.id,
                                    suggested_object_id=entity_id.split(".", 1)[1])
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED

    for (platform, uid), entity_id in LEGACY.items():
        ent = ent_reg.async_get(entity_id)
        assert ent is not None, entity_id
        assert ent.unique_id.startswith(entry.entry_id), (entity_id, ent.unique_id)
        assert hass.states.get(entity_id) is not None, entity_id
    # binary_sensor id5 volt ütközésben: a régi entitás az sbus eszközé marad
    assert ent_reg.async_get("binary_sensor.my_motion").unique_id == f"{entry.entry_id}_sbus_5_motion_sensor"
    # nincs duplikált entitás a migrált mellett
    assert ent_reg.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_sbus_1_relay") == "switch.my_relay"
    # a régi közös eszköz lett a vezérlő eszköze; az entitások a saját eszközükre kerültek
    hub = dev_reg.async_get(legacy_dev.id)
    assert hub.identifiers == {(DOMAIN, entry.entry_id)}
    devs = dr.async_entries_for_config_entry(dev_reg, entry.entry_id)
    assert all(d.via_device_id == hub.id for d in devs if d.id != hub.id)
    assert not er.async_entries_for_device(ent_reg, hub.id)
    # a migráció idempotens: újratöltés után sem változik semmi
    before = {e.entity_id: e.unique_id for e in ents(hass, entry)}
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert {e.entity_id: e.unique_id for e in ents(hass, entry)} == before


async def test_P1_unload_reload(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    n = len(ents(hass, entry))
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED and len(ents(hass, entry)) == n


async def test_P1_real_v006_registry_migrated(hass, mock_api):
    """A v0.0.6 által ténylegesen létrehozott regiszter (tests/fixtures) teljes migrációja."""
    legacy = json.loads((FIXTURES / "legacy_v006_registry.json").read_text())
    entry = make_entry(hass)
    dev_reg = dr.async_get(hass)
    legacy_dev = dev_reg.async_get_or_create(config_entry_id=entry.entry_id, identifiers={(DOMAIN, "all_in_one")})
    ent_reg = er.async_get(hass)
    for item in legacy:
        ent_reg.async_get_or_create(item["platform"], DOMAIN, item["unique_id"], config_entry=entry,
                                    device_id=legacy_dev.id, suggested_object_id=item["entity_id"].split(".", 1)[1])
    await setup(hass, entry)
    not_migrated = [i["entity_id"] for i in legacy
                    if not ent_reg.async_get(i["entity_id"]).unique_id.startswith(entry.entry_id)]
    assert not not_migrated
    changed = [(i["entity_id"], i["state"], hass.states.get(i["entity_id"]).state) for i in legacy
               if hass.states.get(i["entity_id"]).state != i["state"]]
    # 2. fázis: a hozzárendelt érzékelő nélküli termosztát 0.0 helyett ismeretlen
    assert sorted(changed) == [
        ("sensor.sinum_all_in_one_nappali_humidity", "0.0", "unknown"),
        ("sensor.sinum_all_in_one_nappali_temp", "0.0", "unknown"),
    ]
    # a v0.0.6-ban ütközés miatt kimaradt entitások (pl. wtp motion id5) most újként jönnek létre
    new = [e.unique_id.removeprefix(entry.entry_id + "_") for e in ents(hass, entry) if e.entity_id not in {i["entity_id"] for i in legacy}]
    assert new == ["wtp_5_motion_sensor"]
