"""Közös segédfüggvények a SINUM tesztekhez."""
from datetime import timedelta

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

DOMAIN = "sinum"


def make_entry(hass, ip="192.168.1.50", token="tok"):
    e = MockConfigEntry(domain=DOMAIN, data={"ip": ip, "token": token}, title="SINUM")
    e.add_to_hass(hass)
    return e


async def setup(hass, entry):
    ok = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return ok


def ents(hass, entry):
    return er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)


async def tick(hass, seconds):
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done(wait_background_tasks=True)


# A 3. fázis előtti (eszköznév nélküli) entity_id-k -> unique_id utótag; a friss
# telepítés has_entity_name óta olvasható id-ket kap (pl. switch.relay_a).
LEGACY_IDS = {
    "relay_a_switch": "sbus_1_relay",
    "temp_a_temperature": "sbus_2_temperature",
    "hum_a_humidity": "sbus_3_humidity",
    "lux_a_light": "sbus_4_illuminance",
    "motion_a_binary_sensor": "sbus_5_motion_sensor",
    "door_input_binary_sensor": "sbus_6_two_state_input_sensor",
    "led_light": "sbus_7_light",
    "blind_cover": "sbus_8_cover",
    "ao_analog_output": "sbus_9_analog_output",
    "pwm_pwm": "sbus_10_pwm",
    "hum_w_humidity": "wtp_12_humidity",
    "nappali_climate": "virtual_1_climate",
    "nappali_temp": "virtual_1_temp",
    "nappali_humidity": "virtual_1_humidity",
    "nappali_tempsetpoint": "virtual_1_tempsetpoint",
    "nappali_mode": "virtual_1_mode",
    "nappali_mode_select": "virtual_1_mode_select",
    "nappali_tempset": "virtual_1_temp_set",
}


def eid(hass, entity_id):
    """Régi stílusú id feloldása a registry-n át."""
    domain, obj = entity_id.split(".", 1)
    obj = obj.removeprefix("sinum_all_in_one_")
    if hass.states.get(f"{domain}.{obj}") is not None or obj not in LEGACY_IDS:
        return f"{domain}.{obj}" if hass.states.get(f"{domain}.{obj}") else entity_id
    reg = er.async_get(hass)
    suffix = "_" + LEGACY_IDS[obj]
    for ent in reg.entities.values():
        if ent.platform == "sinum" and ent.domain == domain and ent.unique_id.endswith(suffix):
            return ent.entity_id
    return entity_id
