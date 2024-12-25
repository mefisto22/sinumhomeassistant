import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from homeassistant.components.switch import SwitchEntity
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

    update_interval = timedelta(seconds=1)
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="SINUM Relay Switches",
        update_method=api.get_all_relays,  # /devices/sbus + wtp + type=relay
        update_interval=update_interval,
    )

    await coordinator.async_config_entry_first_refresh()
    devices = coordinator.data or []

    entities = []
    for dev in devices:
        device_class = dev.get("class")  # "sbus" / "wtp"
        device_id = dev.get("id")
        name_in_api = dev.get("name", "")
        if not name_in_api:
            name_in_api = "relay"
        base_name = name_in_api.lower().replace(" ", "_")

        entities.append(
            SinumRelaySwitch(coordinator, dev, device_class, device_id, base_name, api)
        )

    async_add_entities(entities)

class SinumRelaySwitch(CoordinatorEntity, SwitchEntity):
    def __init__(self, coordinator, device, device_class, device_id, base_name, api: SinumAPI):
        super().__init__(coordinator)
        self._device = device
        self._device_class = device_class
        self._device_id = device_id
        self._api = api

        self._attr_name = f"{base_name}_switch"
        self._attr_unique_id = f"{DOMAIN}_{device_class}_{device_id}_relay"

    @property
    def device_info(self) -> DeviceInfo:
        """
        Ugyanaz a (DOMAIN, "all_in_one") => minden switch ugyanabba az eszközbe kerül.
        """
        return DeviceInfo(
            identifiers={(DOMAIN, "all_in_one")},
            name="SINUM All-in-One",
            manufacturer="SINUM",
            model="Relay device"
        )

    @property
    def is_on(self) -> bool:
        dev = self._find_device_in_coordinator()
        if not dev:
            return False
        return bool(dev.get("state", False))

    async def async_turn_on(self, **kwargs):
        # Ha az API turn_on hívást használ:
        await self._api.relay_turn_on(self._device_class, self._device_id)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        # Ha az API turn_off hívást használ:
        await self._api.relay_turn_off(self._device_class, self._device_id)
        await self.coordinator.async_request_refresh()

    def _find_device_in_coordinator(self):
        if not self.coordinator.data:
            return None
        for d in self.coordinator.data:
            if d.get("id") == self._device_id and d.get("class") == self._device_class:
                return d
        return None