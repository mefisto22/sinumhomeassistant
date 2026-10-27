"""Alapok: betöltés, entitás-szemantika, hibakezelés."""
from homeassistant.config_entries import ConfigEntryState

from .common import eid, ents, make_entry, setup

CLIMATE = "climate.nappali_climate"


async def test_P0_setup_loads_all_entities(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert len(ents(hass, entry)) > 20


async def test_P0_options_flow_removed(hass, mock_api):
    """Az üres opciók párbeszéd 2026.10.01-től nincs; nem szabad összeomlania."""
    entry = make_entry(hass)
    await setup(hass, entry)
    assert entry.supports_options is False


async def test_P0_hvac_action_idle_when_not_working(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    c = hass.states.get(eid(hass, CLIMATE))
    assert c.state == "heat"
    assert c.attributes["hvac_action"] == "idle"


async def test_P0_hvac_action_heating_when_working(hass, mock_api, api_data):
    api_data["virtual"][0]["state"] = True
    entry = make_entry(hass)
    await setup(hass, entry)
    assert hass.states.get(eid(hass, CLIMATE)).attributes["hvac_action"] == "heating"


async def test_P0_hvac_action_cooling_and_off(hass, mock_api, api_data):
    api_data["virtual"][0].update(mode="cooling", state=True)
    entry = make_entry(hass)
    await setup(hass, entry)
    assert hass.states.get(eid(hass, CLIMATE)).attributes["hvac_action"] == "cooling"


async def test_P0_state_class_measurement(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    numeric = [s for s in hass.states.async_all("sensor")
               if s.attributes.get("device_class") in ("temperature", "humidity", "illuminance", "battery")]
    assert numeric
    missing = [s.entity_id for s in numeric if s.attributes.get("state_class") != "measurement"]
    assert not missing, missing


async def test_P0_two_state_input_not_motion(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    b = hass.states.get(eid(hass, "binary_sensor.sinum_all_in_one_door_input_binary_sensor"))
    assert b is not None and b.attributes.get("device_class") is None
    m = hass.states.get(eid(hass, "binary_sensor.sinum_all_in_one_motion_a_binary_sensor"))
    assert m is None or m.attributes.get("device_class") == "motion"


async def test_P0_light_min_brightness_is_1(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    sent = []

    def cb(url, **kw):
        sent.append((str(url), kw.get("json")))
        return 200, {"data": {}}

    mock_api.add(r".*/command/.*", method="POST", callback=cb)
    await hass.services.async_call("light", "turn_on",
                                   {"entity_id": eid(hass, "light.sinum_all_in_one_led_light"), "brightness": 1}, blocking=True)
    bri = [js for url, js in sent if url.endswith("/set_brightness")]
    assert bri, sent
    assert all(js["set_brightness"][0] >= 1 for js in bri), bri


async def test_P0_http_error_surfaces_to_user(hass, mock_api, caplog):
    import pytest
    from homeassistant.exceptions import HomeAssistantError
    entry = make_entry(hass)
    await setup(hass, entry)
    mock_api.add(r"/devices/sbus/1/command/turn_on", method="POST",
                 status=422, payload={"error": {"message": "bad"}})
    with pytest.raises(HomeAssistantError, match="422 bad"):
        await hass.services.async_call("switch", "turn_on",
                                       {"entity_id": eid(hass, "switch.sinum_all_in_one_relay_a_switch")}, blocking=True)
    assert not [r for r in caplog.records if "AttributeError" in r.getMessage()]
