from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry
from .entity import SinumEntity, async_add_device_entities


# Egyszerre egy parancs platformonként, hogy a vezérlőt ne terheljük túl
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: SinumConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data

    def build(devices: list[dict]) -> list[NumberEntity]:
        entities: list[NumberEntity] = []
        for dev in devices:
            dev_type = dev.get("type")
            if dev["class"] == "virtual" and dev_type == "thermostat":
                entities.append(SinumThermostatSetpointNumber(coordinator, dev))
            elif dev["class"] in ("sbus", "wtp") and dev_type == "analog_output":
                entities.append(SinumAnalogOutputNumber(coordinator, dev))
            elif dev["class"] in ("sbus", "wtp") and dev_type == "pulse_width_modulation":
                entities.append(SinumPWMNumber(coordinator, dev))
        return entities

    async_add_device_entities(entry, async_add_entities, build)


class SinumThermostatSetpointNumber(SinumEntity, NumberEntity):
    """Célhőmérséklet csúszkaként; a klíma entitás ugyanezt tudja."""

    _attr_mode = NumberMode.SLIDER
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_step = 0.1
    _attr_translation_key = "target_temperature"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator, device, "temp_set")
        self._attr_native_unit_of_measurement = coordinator.temperature_unit

    def _tenths(self, field: str, default: int | None = None) -> float | None:
        dev = self.device
        raw = dev.get(field, default) if dev else default
        return None if raw is None else raw / 10.0

    @property
    def native_min_value(self) -> float:
        return self._tenths("target_temperature_minimum", 50)

    @property
    def native_max_value(self) -> float:
        return self._tenths("target_temperature_maximum", 350)

    @property
    def native_value(self) -> float | None:
        return self._tenths("target_temperature")

    async def async_set_native_value(self, value: float) -> None:
        await self._async_patch(target_temperature=round(value * 10))


class SinumAnalogOutputNumber(SinumEntity, NumberEntity):
    """Analóg kimenet; az API ezredekben (mV / µA) adja az értéket."""

    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 0.1
    _attr_name = None

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator, device, "analog_output")
        unit = device.get("unit", "V")
        self._attr_native_unit_of_measurement = "mA" if unit.lower() == "ua" else "V"

    def _thousandths(self, field: str, default: int | None = None) -> float | None:
        dev = self.device
        raw = dev.get(field, default) if dev else default
        return None if raw is None else raw / 1000.0

    @property
    def native_min_value(self) -> float:
        return self._thousandths("value_minimum", 0)

    @property
    def native_max_value(self) -> float:
        return self._thousandths("value_maximum", 10000)

    @property
    def native_value(self) -> float | None:
        return self._thousandths("value")

    async def async_set_native_value(self, value: float) -> None:
        await self._async_command("set_value", int(value * 1000))


class SinumPWMNumber(SinumEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = "%"
    _attr_native_min_value = 0.0
    _attr_native_max_value = 100.0
    _attr_native_step = 1.0
    _attr_name = None

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator, device, "pwm")

    @property
    def native_value(self) -> float | None:
        dev = self.device
        return dev.get("duty_cycle") if dev else None

    async def async_set_native_value(self, value: float) -> None:
        await self._async_command("set_duty_cycle", int(value))
