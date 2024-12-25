import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from homeassistant.components.select import SelectEntity
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
        name="SINUM Thermostat Mode",
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
                SinumThermostatModeSelect(coordinator, device, base_name, api)
            )

    async_add_entities(entities)

class SinumThermostatModeSelect(CoordinatorEntity, SelectEntity):
    """SelectEntity a 'mode' mező állítására (off/heating/cooling)."""
    _attr_options = ["off", "heating", "cooling"]

    def __init__(self, coordinator, device, base_name, api: SinumAPI):
        super().__init__(coordinator)
        self._device_id = device.get("id")
        self._api = api
        self._attr_name = f"{base_name}_mode_select"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_mode_select"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, "all_in_one")},
            name="SINUM All-in-One",
            manufacturer="SINUM",
            model="Thermostat Integration",
        )

    @property
    def current_option(self) -> str | None:
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        return dev.get("mode")

    async def async_select_option(self, option: str) -> None:
        await self._api.set_thermostat_mode(self._device_id, option)
        await self.coordinator.async_request_refresh()

    def _find_device_in_coordinator(self):
        data = self.coordinator.data
        if not data:
            return None
        for dev in data:
            if dev.get("id") == self._device_id:
                return dev
        return None