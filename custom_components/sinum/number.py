from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry
from .entity import SinumEntity, slug


async def async_setup_entry(
    hass: HomeAssistant, entry: SinumConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = [
        SinumThermostatSetpointNumber(coordinator, dev)
        for dev in coordinator.devices("virtual")
        if dev.get("type") == "thermostat"
    ]
    for dev in coordinator.devices():
        if dev["class"] not in ("sbus", "wtp"):
            continue
        if dev.get("type") == "analog_output":
            entities.append(SinumAnalogOutputNumber(coordinator, dev))
        elif dev.get("type") == "pulse_width_modulation":
            entities.append(SinumPWMNumber(coordinator, dev))
    async_add_entities(entities)


class SinumThermostatSetpointNumber(SinumEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_native_step = 0.1

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator, device, "temp_set")
        self._attr_name = f"{slug(device.get('name', 'Thermostat'))}_tempset"

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
        await self._async_patch(target_temperature=int(value * 10))


class SinumAnalogOutputNumber(SinumEntity, NumberEntity):
    """Analóg kimenet; az API ezredekben (mV / µA) adja az értéket."""

    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 0.1

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator, device, "analog_output")
        self._attr_name = f"{slug(device.get('name', 'unknown_device'))}_analog_output"
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

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator, device, "pwm")
        self._attr_name = f"{slug(device.get('name', 'unknown_device'))}_pwm"

    @property
    def native_value(self) -> float | None:
        dev = self.device
        return dev.get("duty_cycle") if dev else None

    async def async_set_native_value(self, value: float) -> None:
        await self._async_command("set_duty_cycle", int(value))
