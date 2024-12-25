import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from homeassistant.components.number import NumberEntity, NumberMode, NumberDeviceClass
from homeassistant.helpers.device_registry import DeviceInfo

from .api import SinumAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    ip = config_entry.data["ip"]
    token = config_entry.data["token"]
    api = SinumAPI(ip, token)

    update_interval = timedelta(seconds=1) 

    # Coordinators létrehozása
    thermostat_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="SINUM Thermostat Number",
        update_method=api.get_virtual_devices,
        update_interval=update_interval,
    )

    sbus_wtp_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="SINUM SBUS/WTP Coordinator",
        update_method=_fetch_sbus_wtp_devices(api),
        update_interval=update_interval,
    )

    # Első frissítések
    await thermostat_coordinator.async_config_entry_first_refresh()
    await sbus_wtp_coordinator.async_config_entry_first_refresh()

    devices_thermostat = thermostat_coordinator.data or []
    devices_sbus_wtp = sbus_wtp_coordinator.data or []

    entities = []

    # Thermostat entitások hozzáadása
    for dev in devices_thermostat:
        if dev.get("type") == "thermostat":
            name_in_api = dev.get("name", "Thermostat")
            base_name = name_in_api.lower().replace(" ", "_")

            entities.append(
                SinumThermostatSetpointNumber(thermostat_coordinator, dev, base_name, api)
            )

    # Analóg kimenet és PWM entitások hozzáadása
    for dev in devices_sbus_wtp:
        device_type = dev.get("type")
        name_in_api = dev.get("name", "unknown_device")
        base_name = name_in_api.lower().replace(" ", "_")

        if device_type == "analog_output":
            entities.append(
                SinumAnalogOutputNumber(sbus_wtp_coordinator, dev, base_name, api)
            )
        elif device_type == "pulse_width_modulation":
            entities.append(
                SinumPWMNumber(sbus_wtp_coordinator, dev, base_name, api)
            )

    async_add_entities(entities)

def _fetch_sbus_wtp_devices(api: SinumAPI):
    async def _async_fetch_sbus_wtp():
        sbus_list = await api.get_sbus_devices()
        wtp_list = await api.get_wtp_devices()
        return sbus_list + wtp_list

    return _async_fetch_sbus_wtp

# Definiáljuk a közös DeviceInfo-t
DEVICE_INFO = DeviceInfo(
    identifiers={(DOMAIN, "all_in_one")},
    name="SINUM All-in-One",
    manufacturer="SINUM",
    model="All-in-One Integration",
)

class SinumThermostatSetpointNumber(CoordinatorEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"

    def __init__(self, coordinator, device, base_name, api: SinumAPI):
        super().__init__(coordinator)
        self._device_id = device.get("id")
        self._api = api
        self._attr_name = f"{base_name}_tempset"
        self._attr_unique_id = f"{DOMAIN}_all_in_one_{self._device_id}_temp_set"

    @property
    def device_info(self) -> DeviceInfo:
        return DEVICE_INFO

    @property
    def native_min_value(self) -> float:
        dev = self._find_device_in_coordinator()
        if not dev:
            return 5.0
        raw_lower = dev.get("target_temperature_minimum", 50)
        return raw_lower / 10.0

    @property
    def native_max_value(self) -> float:
        dev = self._find_device_in_coordinator()
        if not dev:
            return 35.0
        raw_upper = dev.get("target_temperature_maximum", 350)
        return raw_upper / 10.0

    @property
    def native_step(self) -> float:
        return 0.1

    @property
    def native_value(self) -> float | None:
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        raw_target = dev.get("target_temperature")
        if raw_target is None:
            return None
        return raw_target / 10.0

    async def async_set_native_value(self, value: float) -> None:
        new_target = int(value * 10)
        result = await self._api.set_thermostat_target_temperature(self._device_id, new_target)
        if result:
            await self.coordinator.async_request_refresh()

    def _find_device_in_coordinator(self):
        data = self.coordinator.data
        if not data:
            return None
        for dev in data:
            if dev.get("id") == self._device_id:
                return dev
        return None

class SinumAnalogOutputNumber(CoordinatorEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = "mA"  # Alapértelmezett egység

    def __init__(self, coordinator, device, base_name, api: SinumAPI):
        super().__init__(coordinator)
        self._device_id = device.get("id")
        self._api = api
        self._attr_name = f"{base_name}_analog_output"
        self._attr_unique_id = f"{DOMAIN}_all_in_one_{self._device_id}_analog_output"
        self._unit = device.get("unit", "V")
        self._attr_native_unit_of_measurement = "mA" if self._unit.lower() == "ua" else "V"

    @property
    def device_info(self) -> DeviceInfo:
        return DEVICE_INFO

    @property
    def native_min_value(self) -> float:
        dev = self._find_device_in_coordinator()
        if not dev:
            return 0.0
        raw_min = dev.get("value_minimum", 0)
        return raw_min / 1000.0

    @property
    def native_max_value(self) -> float:
        dev = self._find_device_in_coordinator()
        if not dev:
            return 10.0
        raw_max = dev.get("value_maximum", 10000)
        return raw_max / 1000.0

    @property
    def native_step(self) -> float:
        return 0.1

    @property
    def native_value(self) -> float | None:
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        raw_value = dev.get("value")
        if raw_value is None:
            return None
        return raw_value / 1000.0

    async def async_set_native_value(self, value: float) -> None:
        set_value = int(value * 1000)
        result = await self._api.set_analog_output_value(self._device_id, set_value)
        if result:
            await self.coordinator.async_request_refresh()

    def _find_device_in_coordinator(self):
        data = self.coordinator.data
        if not data:
            return None
        for dev in data:
            if dev.get("id") == self._device_id:
                return dev
        return None

class SinumPWMNumber(CoordinatorEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = "%"  # Módosítva "%"-re

    def __init__(self, coordinator, device, base_name, api: SinumAPI):
        super().__init__(coordinator)
        self._device_id = device.get("id")
        self._device_class = device.get("class")  # 'sbus' vagy 'wtp'
        self._api = api
        self._attr_name = f"{base_name}_pwm"
        self._attr_unique_id = f"{DOMAIN}_all_in_one_{self._device_id}_pwm"

    @property
    def device_info(self) -> DeviceInfo:
        return DEVICE_INFO

    @property
    def native_min_value(self) -> float:
        return 0.0

    @property
    def native_max_value(self) -> float:
        return 100.0

    @property
    def native_step(self) -> float:
        return 1.0  # Lépésköz 1%-onként

    @property
    def native_value(self) -> float | None:
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        duty_cycle = dev.get("duty_cycle")
        if duty_cycle is None:
            return None
        return duty_cycle  # Direct 0-100%

    async def async_set_native_value(self, value: float) -> None:
        set_duty_cycle = int(value)  # Például 75%
        result = await self._api.set_pwm_duty_cycle(self._device_class, self._device_id, set_duty_cycle)
        if result:
            await self.coordinator.async_request_refresh()

    def _find_device_in_coordinator(self):
        data = self.coordinator.data
        if not data:
            return None
        for dev in data:
            if dev.get("id") == self._device_id:
                return dev
        return None