import logging
from datetime import timedelta
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.components.climate import (
    ClimateEntity,
    HVACMode,
    ClimateEntityFeature,
)
from homeassistant.components.climate.const import (
    HVACAction,
)
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.util.unit_system import UnitOfTemperature
from homeassistant.helpers.device_registry import DeviceInfo

from .api import SinumAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
):
    ip = config_entry.data["ip"]
    token = config_entry.data["token"]

    api = SinumAPI(ip, token)

    update_interval = timedelta(seconds=2)
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="SINUM Thermostat Climate",
        update_method=api.get_virtual_devices,
        update_interval=update_interval,
    )

    await coordinator.async_config_entry_first_refresh()
    devices = coordinator.data or []

    entities = []
    for device in devices:
        if device.get("type") == "thermostat":
            name_in_api = device.get("name", "")
            if not name_in_api:
                name_in_api = "thermostat"
            base_name = name_in_api.lower().replace(" ", "_")
            entities.append(
                SinumThermostatClimate(coordinator, device, base_name, api)
            )

    async_add_entities(entities)

class SinumThermostatClimate(CoordinatorEntity, ClimateEntity):
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, device, base_name, api: SinumAPI):
        super().__init__(coordinator)
        self._device_id = device.get("id")
        self._api = api
        self._attr_name = f"{base_name}_climate"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_climate"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "all_in_one")},
            name="SINUM All-in-One",
            manufacturer="SINUM",
            model="All-in-One Integration",
        )

    def _find_device_in_coordinator(self):
        data = self.coordinator.data
        if not data:
            return None
        for dev in data:
            if dev.get("id") == self._device_id:
                return dev
        return None

    @property
    def hvac_mode(self) -> str:
        dev = self._find_device_in_coordinator()
        if not dev:
            return HVACMode.OFF
        sinum_mode = dev.get("mode", "off")
        if sinum_mode == "heating":
            return HVACMode.HEAT
        elif sinum_mode == "cooling":
            return HVACMode.COOL
        return HVACMode.OFF

    @property
    def hvac_action(self) -> Optional[str]:
        mode = self.hvac_mode
        if mode == HVACMode.HEAT:
            return HVACAction.HEATING
        elif mode == HVACMode.COOL:
            return HVACAction.COOLING
        return HVACAction.OFF

    @property
    def current_temperature(self) -> Optional[float]:
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        raw_temp = dev.get("temperature")
        if raw_temp is None:
            return None
        return raw_temp / 10.0

    @property
    def target_temperature(self) -> Optional[float]:
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        raw_target = dev.get("target_temperature")
        if raw_target is None:
            return None
        return raw_target / 10.0

    @property
    def min_temp(self) -> float:
        dev = self._find_device_in_coordinator()
        if not dev:
            return 5.0
        raw_lower = dev.get("target_temperature_minimum", 50)
        return raw_lower / 10.0

    @property
    def max_temp(self) -> float:
        dev = self._find_device_in_coordinator()
        if not dev:
            return 35.0
        raw_upper = dev.get("target_temperature_maximum", 350)
        return raw_upper / 10.0

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        sinum_mode = "off"
        if hvac_mode == HVACMode.HEAT:
            sinum_mode = "heating"
        elif hvac_mode == HVACMode.COOL:
            sinum_mode = "cooling"

        await self._api.set_thermostat_mode(self._device_id, sinum_mode)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs) -> None:
        new_temp = kwargs.get(ATTR_TEMPERATURE)
        if new_temp is None:
            return
        new_target = int(new_temp * 10)
        await self._api.set_thermostat_target_temperature(self._device_id, new_target)
        await self.coordinator.async_request_refresh()