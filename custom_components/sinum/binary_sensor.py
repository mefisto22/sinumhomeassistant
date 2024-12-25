import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .api import SinumAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEVICE_INFO = DeviceInfo(
    identifiers={(DOMAIN, "all_in_one")},
    name="SINUM All-in-One",
    manufacturer="SINUM",
    model="All-in-One Integration",
)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    ip = config_entry.data["ip"]
    token = config_entry.data["token"]
    api = SinumAPI(ip, token)

    update_interval = timedelta(seconds=1)  # Bináris szenzorok frissítése 1 másodpercenként

    binary_sensor_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="SINUM Binary Sensor Coordinator",
        update_method=_fetch_binary_sensors(api),
        update_interval=update_interval,
    )

    await binary_sensor_coordinator.async_config_entry_first_refresh()

    devices_binary = binary_sensor_coordinator.data or []

    entities = []

    for dev in devices_binary:
        device_type = dev.get("type")
        if device_type not in ["motion_sensor", "two_state_input_sensor"]:
            continue  # Csak a két típusú bináris szenzorra fókuszálunk

        name_in_api = dev.get("name", "Unnamed Sensor")
        base_name = name_in_api.lower().replace(" ", "_")

        entities.append(
            SinumBinarySensor(binary_sensor_coordinator, dev, base_name, api)
        )

    async_add_entities(entities)

def _fetch_binary_sensors(api: SinumAPI):
    async def _async_fetch_binary_sensors():
        sbus_list = await api.get_sbus_devices()
        wtp_list = await api.get_wtp_devices()
        combined = sbus_list + wtp_list
        # Szűrjük ki a bináris szenzorokat
        binary_sensors = [
            dev for dev in combined
            if dev.get("type") in ["motion_sensor", "two_state_input_sensor"]
        ]
        return binary_sensors

    return _async_fetch_binary_sensors

class SinumBinarySensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, coordinator, device, base_name, api: SinumAPI):
        super().__init__(coordinator)
        self._device_id = device.get("id")
        self._device_class_type = device.get("class")  # 'sbus' vagy 'wtp'
        self._api = api
        self._type = device.get("type")
        self._attr_name = f"{base_name}_binary_sensor"
        self._attr_unique_id = f"{DOMAIN}_all_in_one_{self._device_id}_{self._type}"
        self._attr_device_info = DEVICE_INFO

    @property
    def is_on(self) -> bool:
        """Return the state of the binary sensor."""
        dev = self._find_device_in_coordinator()
        if not dev:
            return False

        if self._type == "motion_sensor":
            return dev.get("motion_detected", False)
        elif self._type == "two_state_input_sensor":
            return dev.get("state", False)
        return False

    async def async_update(self):
        """Fetch new state data for the binary sensor."""
        await self.coordinator.async_request_refresh()

    @property
    def device_class(self) -> str | None:
        """Return the class of the binary sensor."""
        if self._type == "motion_sensor":
            return "motion"
        elif self._type == "two_state_input_sensor":
            return "motion"  # Ha szükséges, módosítsd a megfelelő device_class-ra
        return None

    def _find_device_in_coordinator(self):
        """Find the device data in the coordinator's data list."""
        data = self.coordinator.data
        if not data:
            return None
        for dev in data:
            if dev.get("id") == self._device_id and dev.get("class") == self._device_class_type:
                return dev
        return None