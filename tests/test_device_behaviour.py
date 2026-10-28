"""Phase 2: thermostat no-sensor values and presets, sensor sentinels, cover STOP/tilt, light color/brightness."""
import pytest
from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.const import STATE_UNKNOWN
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .common import eid, make_entry, setup

CLIMATE = "climate.nappali_climate"
COVER = "cover.sinum_all_in_one_blind_cover"
LIGHT = "light.sinum_all_in_one_led_light"


def _dev(api_data, cls, dev_id):
    return next(d for d in api_data[cls] if d["id"] == dev_id)


async def _loaded(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    # Az alapból letiltott (redundáns) entitásokat is teszteljük
    reg = er.async_get(hass)
    for ent in er.async_entries_for_config_entry(reg, entry.entry_id):
        if ent.disabled_by is not None:
            reg.async_update_entity(ent.entity_id, disabled_by=None)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    for method in ("POST", "PATCH"):
        mock_api.add(r"/devices/", method=method, status=200, payload={"data": {}})
    mock_api.calls.clear()
    return entry


def _writes(mock_api):
    return [(m, u.split("/api/v1")[1], js) for m, u, js in mock_api.calls if m != "GET"]


async def _call(hass, domain, service, entity_id, **data):
    await hass.services.async_call(domain, service, {"entity_id": eid(hass, entity_id), **data}, blocking=True)


# ------------------------------------------------------------ measurements
async def test_P2_thermostat_without_sensor_is_unknown(hass, mock_api):
    await _loaded(hass, mock_api)  # a fixture termosztátja: temperature = humidity = 0
    st = hass.states.get(eid(hass, CLIMATE))
    assert st.attributes["current_temperature"] is None
    assert st.attributes.get("current_humidity") is None
    assert hass.states.get(eid(hass, "sensor.nappali_temp")).state == STATE_UNKNOWN
    assert hass.states.get(eid(hass, "sensor.nappali_humidity")).state == STATE_UNKNOWN
    assert hass.states.get(eid(hass, "sensor.nappali_tempsetpoint")).state == "21.5"


async def test_P2_thermostat_with_sensor(hass, mock_api, api_data):
    _dev(api_data, "virtual", 1).update(temperature=-15, humidity=412)
    await _loaded(hass, mock_api)
    st = hass.states.get(eid(hass, CLIMATE))
    assert st.attributes["current_temperature"] == -1.5
    assert st.attributes["current_humidity"] == 41.2
    assert hass.states.get(eid(hass, "sensor.nappali_temp")).state == "-1.5"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(-32768, STATE_UNKNOWN), (1001, STATE_UNKNOWN), (-401, STATE_UNKNOWN), (-400, "-40.0"), (0, "0.0"), (215, "21.5")],
)
async def test_P2_temperature_sensor_sentinel(hass, mock_api, api_data, raw, expected):
    _dev(api_data, "sbus", 2)["temperature"] = raw
    await _loaded(hass, mock_api)
    assert hass.states.get(eid(hass, "sensor.temp_a_temperature")).state == expected


async def test_P2_humidity_sensor_sentinel(hass, mock_api, api_data):
    _dev(api_data, "sbus", 3)["humidity"] = 65535
    await _loaded(hass, mock_api)
    assert hass.states.get(eid(hass, "sensor.hum_a_humidity")).state == STATE_UNKNOWN
    assert hass.states.get(eid(hass, "sensor.hum_w_humidity")).state == "50.0"


# ------------------------------------------------------------ thermostat presets / mode
def _schedule_thermostat(api_data, current="schedule", labels=("has_schedule",)):
    _dev(api_data, "virtual", 1).update(
        labels=list(labels),
        target_temperature_mode={"current": current, "previous": "constant", "remaining_time": 0},
    )


async def test_P2_presets_schedule_and_constant(hass, mock_api, api_data):
    _schedule_thermostat(api_data)
    await _loaded(hass, mock_api)
    st = hass.states.get(eid(hass, CLIMATE))
    assert st.attributes["supported_features"] & ClimateEntityFeature.PRESET_MODE
    assert st.attributes["preset_modes"] == ["schedule", "constant"]
    assert st.attributes["preset_mode"] == "schedule"
    await _call(hass, "climate", "set_preset_mode", CLIMATE, preset_mode="constant")
    await _call(hass, "climate", "set_preset_mode", CLIMATE, preset_mode="schedule")  # már az aktív: nincs hívás
    assert _writes(mock_api) == [
        ("POST", "/devices/virtual/1/command/enable_constant_mode", {"enable_constant_mode": 215})
    ]


async def test_P2_preset_schedule_command(hass, mock_api, api_data):
    _schedule_thermostat(api_data, current="constant")
    await _loaded(hass, mock_api)
    await _call(hass, "climate", "set_preset_mode", CLIMATE, preset_mode="schedule")
    assert _writes(mock_api) == [("POST", "/devices/virtual/1/command/enable_schedule_mode", {})]


async def test_P2_presets_without_schedule_label(hass, mock_api, api_data):
    _schedule_thermostat(api_data, current="constant", labels=())
    await _loaded(hass, mock_api)
    st = hass.states.get(eid(hass, CLIMATE))
    assert st.attributes["preset_modes"] == ["constant"]
    with pytest.raises(Exception):  # nincs a listában: a HA validációja elutasítja
        await _call(hass, "climate", "set_preset_mode", CLIMATE, preset_mode="schedule")
    assert _writes(mock_api) == []


async def test_P2_time_limited_preset_shown(hass, mock_api, api_data):
    _schedule_thermostat(api_data, current="time_limited")
    await _loaded(hass, mock_api)
    st = hass.states.get(eid(hass, CLIMATE))
    assert st.attributes["preset_modes"] == ["schedule", "constant", "time_limited"]
    assert st.attributes["preset_mode"] == "time_limited"


async def test_P2_no_presets_on_old_firmware(hass, mock_api):
    await _loaded(hass, mock_api)  # nincs target_temperature_mode mező
    st = hass.states.get(eid(hass, CLIMATE))
    assert not st.attributes["supported_features"] & ClimateEntityFeature.PRESET_MODE


async def test_P2_locked_mode(hass, mock_api, api_data):
    _dev(api_data, "virtual", 1)["mode_mutable"] = False
    await _loaded(hass, mock_api)
    with pytest.raises(HomeAssistantError):
        await _call(hass, "climate", "set_hvac_mode", CLIMATE, hvac_mode="cool")
    with pytest.raises(HomeAssistantError):
        await _call(hass, "select", "select_option", "select.nappali_mode_select", option="cooling")
    assert _writes(mock_api) == []


async def test_P2_setpoint_rounding(hass, mock_api):
    await _loaded(hass, mock_api)
    await _call(hass, "climate", "set_temperature", CLIMATE, temperature=20.3)
    await _call(hass, "number", "set_value", "number.nappali_tempset", value=19.7)
    assert _writes(mock_api) == [
        ("PATCH", "/devices/virtual/1", {"id": 1, "target_temperature": 203}),
        ("PATCH", "/devices/virtual/1", {"id": 1, "target_temperature": 197}),
    ]


@pytest.mark.parametrize(
    ("limits", "expected"),
    [
        ({}, (5.0, 35.0, 5.0, 35.0, 0.0, 10.0)),
        ({"target_temperature_minimum": 70, "value_minimum": 1000}, (7.0, 35.0, 7.0, 35.0, 1.0, 10.0)),
        # A vezérlő null-t is küldhet; ilyenkor is az alapértelmezett határ érvényes
        ({"target_temperature_minimum": None, "target_temperature_maximum": None,
          "value_minimum": None, "value_maximum": None}, (5.0, 35.0, 5.0, 35.0, 0.0, 10.0)),
    ],
)
async def test_P2_min_max_limits(hass, mock_api, api_data, limits, expected):
    thermostat, analog = _dev(api_data, "virtual", 1), _dev(api_data, "sbus", 9)
    for dev in (thermostat, analog):
        for key in ("target_temperature_minimum", "target_temperature_maximum", "value_minimum", "value_maximum"):
            dev.pop(key, None)
    for key, value in limits.items():
        (thermostat if key.startswith("target") else analog)[key] = value
    entry = await _loaded(hass, mock_api)
    reg = er.async_get(hass)

    def attrs(platform, key):
        entity_id = reg.async_get_entity_id(platform, "sinum", f"{entry.entry_id}_{key}")
        return hass.states.get(entity_id).attributes

    climate = attrs("climate", "virtual_1_climate")
    setpoint = attrs("number", "virtual_1_temp_set")
    ao = attrs("number", "sbus_9_analog_output")
    assert (climate["min_temp"], climate["max_temp"], setpoint["min"], setpoint["max"], ao["min"], ao["max"]) == expected


# ------------------------------------------------------------ cover
async def test_P2_cover_stop_and_position(hass, mock_api, api_data):
    _dev(api_data, "sbus", 8)["window_covering_type"] = "roller_shade"
    await _loaded(hass, mock_api)
    st = hass.states.get(eid(hass, COVER))
    assert st.attributes["device_class"] == "shade"
    assert st.attributes["supported_features"] & CoverEntityFeature.STOP
    assert st.attributes["supported_features"] & CoverEntityFeature.SET_POSITION
    assert not st.attributes["supported_features"] & CoverEntityFeature.SET_TILT_POSITION
    await _call(hass, "cover", "stop_cover", COVER)
    await _call(hass, "cover", "open_cover", COVER)
    assert _writes(mock_api) == [
        ("POST", "/devices/sbus/8/command/stop", {}),
        ("PATCH", "/devices/sbus/8", {"id": 8, "target_opening": 100}),
    ]


async def test_P2_cover_without_percent_label(hass, mock_api, api_data):
    _dev(api_data, "sbus", 8)["labels"] = []
    await _loaded(hass, mock_api)
    st = hass.states.get(eid(hass, COVER))
    assert not st.attributes["supported_features"] & CoverEntityFeature.SET_POSITION
    assert st.attributes["current_position"] == 40


async def test_P2_cover_tilt(hass, mock_api, api_data):
    _dev(api_data, "sbus", 8).update(
        labels=["percent_opening_control", "percent_tilt_control"], current_tilt=20, target_tilt=20
    )
    await _loaded(hass, mock_api)
    st = hass.states.get(eid(hass, COVER))
    assert st.attributes["current_tilt_position"] == 20
    await _call(hass, "cover", "set_cover_tilt_position", COVER, tilt_position=65)
    await _call(hass, "cover", "close_cover_tilt", COVER)
    assert _writes(mock_api) == [
        ("POST", "/devices/sbus/8/command/tilt", {"tilt": 65}),
        ("POST", "/devices/sbus/8/command/tilt", {"tilt": 0}),
    ]


# ------------------------------------------------------------ light
async def test_P2_light_off_sets_params_before_turn_on(hass, mock_api, api_data):
    _dev(api_data, "sbus", 7)["state"] = False
    await _loaded(hass, mock_api)
    await _call(hass, "light", "turn_on", LIGHT, hs_color=[240, 100], brightness=128)
    assert _writes(mock_api) == [
        ("POST", "/devices/sbus/7/command/set_color", {"set_color": ["#0000ff"]}),
        ("POST", "/devices/sbus/7/command/set_brightness", {"set_brightness": [50]}),
        ("POST", "/devices/sbus/7/command/turn_on", {}),
    ]


async def test_P2_light_on_color_keeps_full_value(hass, mock_api):
    await _loaded(hass, mock_api)  # bekapcsolt, 50% fényerő
    await _call(hass, "light", "turn_on", LIGHT, hs_color=[120, 50])
    assert _writes(mock_api) == [("POST", "/devices/sbus/7/command/set_color", {"set_color": ["#80ff80"]})]


async def test_P2_light_transition_and_color_temp(hass, mock_api, api_data):
    _dev(api_data, "sbus", 7)["state"] = False
    await _loaded(hass, mock_api)
    await _call(hass, "light", "turn_on", LIGHT, color_temp_kelvin=4000, brightness=1, transition=2)
    await _call(hass, "light", "turn_off", LIGHT, transition=1.5)
    assert _writes(mock_api) == [
        ("POST", "/devices/sbus/7/command/set_temperature", {"set_temperature": [4000, 20]}),
        ("POST", "/devices/sbus/7/command/set_brightness", {"set_brightness": [1, 20]}),
        ("POST", "/devices/sbus/7/command/turn_on", {"turn_on": 20}),
        ("POST", "/devices/sbus/7/command/turn_off", {"turn_off": 15}),
    ]


async def test_P2_light_state(hass, mock_api, api_data):
    _dev(api_data, "sbus", 7).update(color_mode="temperature", white_temperature=3500, brightness=100)
    await _loaded(hass, mock_api)
    st = hass.states.get(eid(hass, LIGHT))
    assert st.attributes["color_mode"] == "color_temp"
    assert st.attributes["color_temp_kelvin"] == 3500
    assert st.attributes["brightness"] == 255
