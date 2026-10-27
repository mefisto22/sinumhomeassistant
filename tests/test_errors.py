"""Felhasználónak szóló hibák: fordítható üzenetek, hibatípusok."""
import aiohttp
import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from .common import DOMAIN, make_entry, setup

CLIMATE = "climate.nappali"


def _entity_id(hass, entry, platform, key):
    return er.async_get(hass).async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")


def _entity(hass, entity_id):
    for platform in hass.data["entity_platform"][DOMAIN]:
        if entity_id in platform.entities:
            return platform.entities[entity_id]
    raise LookupError(entity_id)


async def _relay_on(hass, entry):
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": _entity_id(hass, entry, "switch", "sbus_1_relay")}, blocking=True
    )


async def test_command_rejected(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    mock_api.add(r"/devices/sbus/1/command/turn_on", status=422, payload={"error": {"message": "bad"}})
    with pytest.raises(HomeAssistantError) as exc:
        await _relay_on(hass, entry)
    assert exc.value.translation_domain == DOMAIN
    assert exc.value.translation_key == "command_failed"
    assert str(exc.value).startswith("The SINUM controller rejected the command: ")
    assert "HTTP 422 bad" in str(exc.value)


async def test_command_connection_error(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)

    def refuse(url, **kw):
        raise aiohttp.ClientConnectionError("Connection refused")

    mock_api.add(r"/devices/sbus/1/command/turn_on", callback=refuse)
    with pytest.raises(HomeAssistantError) as exc:
        await _relay_on(hass, entry)
    assert exc.value.translation_key == "cannot_connect"
    assert str(exc.value).startswith("Cannot reach the SINUM controller: ")


async def test_command_auth_error(hass, mock_api):
    entry = make_entry(hass)
    await setup(hass, entry)
    mock_api.add(r"/devices/sbus/1/command/turn_on", status=401, payload={})
    with pytest.raises(HomeAssistantError) as exc:
        await _relay_on(hass, entry)
    assert exc.value.translation_key == "invalid_auth"


async def test_locked_mode_is_validation_error(hass, mock_api, api_data):
    api_data["virtual"][0]["mode_mutable"] = False
    entry = make_entry(hass)
    await setup(hass, entry)
    with pytest.raises(ServiceValidationError) as exc:
        await hass.services.async_call(
            "climate", "set_hvac_mode", {"entity_id": CLIMATE, "hvac_mode": "cool"}, blocking=True
        )
    assert exc.value.translation_key == "mode_locked"
    assert str(exc.value) == "The thermostat mode is locked on the SINUM controller"
    assert not [c for c in mock_api.calls if c[0] != "GET"]


async def test_constant_preset_without_target(hass, mock_api, api_data):
    api_data["virtual"][0].update(
        target_temperature=None,
        labels=["has_schedule"],
        target_temperature_mode={"current": "schedule", "previous": "constant", "remaining_time": 0},
    )
    entry = make_entry(hass)
    await setup(hass, entry)
    with pytest.raises(HomeAssistantError) as exc:
        await hass.services.async_call(
            "climate", "set_preset_mode", {"entity_id": CLIMATE, "preset_mode": "constant"}, blocking=True
        )
    assert exc.value.translation_key == "no_target_temperature"
    assert str(exc.value) == "The thermostat has no target temperature"


async def test_time_limited_preset_cannot_be_activated(hass, mock_api, api_data):
    api_data["virtual"][0]["target_temperature_mode"] = {"current": "constant"}
    entry = make_entry(hass)
    await setup(hass, entry)
    # A HA a listán kívüli presetet már a szolgáltatáshívásnál elutasítja, ezért közvetlenül
    with pytest.raises(ServiceValidationError) as exc:
        await _entity(hass, CLIMATE).async_set_preset_mode("time_limited")
    assert exc.value.translation_key == "preset_not_supported"
    assert exc.value.translation_placeholders == {"preset": "time_limited"}
    assert str(exc.value) == "The time_limited preset cannot be activated from Home Assistant"


@pytest.mark.parametrize(
    ("platform", "expected"),
    [("sensor", 0), ("binary_sensor", 0), ("climate", 1), ("cover", 1), ("light", 1),
     ("number", 1), ("select", 1), ("switch", 1)],
)
def test_parallel_updates(platform, expected):
    module = __import__(f"custom_components.sinum.{platform}", fromlist=["PARALLEL_UPDATES"])
    assert module.PARALLEL_UPDATES == expected
