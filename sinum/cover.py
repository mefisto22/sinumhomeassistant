import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from homeassistant.components.cover import (
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.helpers.device_registry import DeviceInfo

from .api import SinumAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
):
    """Set up cover platform: blind_controller from sbus/wtp."""
    ip = config_entry.data["ip"]
    token = config_entry.data["token"]
    api = SinumAPI(ip, token)

    update_interval = timedelta(seconds=2)
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="SINUM Blind Controllers",
        update_method=api.get_all_blind_controllers,  # Leszedi a type="blind_controller" eszközöket
        update_interval=update_interval,
    )

    await coordinator.async_config_entry_first_refresh()
    devices = coordinator.data or []

    entities = []
    for dev in devices:
        # dev["type"] = "blind_controller", dev["class"] = "sbus"/"wtp"
        device_class = dev.get("class") 
        device_id = dev.get("id")
        name_in_api = dev.get("name", "")
        if not name_in_api:
            name_in_api = "cover"

        base_name = name_in_api.lower().replace(" ", "_")
        entities.append(
            SinumCoverEntity(coordinator, dev, device_class, device_id, base_name, api)
        )

    async_add_entities(entities)

class SinumCoverEntity(CoordinatorEntity, CoverEntity):
    """
    Home Assistant cover entitás, ami a "current_opening" (0..100) alapján
    mutatja a redőny helyzetét, és "target_opening" PATCH-el állítja.
    """

    def __init__(self, coordinator, device, device_class, device_id, base_name, api: SinumAPI):
        super().__init__(coordinator)
        self._device = device
        self._device_class = device_class
        self._device_id = device_id
        self._api = api

        self._attr_name = f"{base_name}_cover"  # Pl. "blind_controller_1_cover"
        self._attr_unique_id = f"{DOMAIN}_{self._device_class}_{self._device_id}_cover"

        # Ezzel jelzed, hogy a user a Lovelace-ben open/close/set position akciókat is végezhet
        self._attr_supported_features = (
            CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.SET_POSITION
        )

    @property
    def device_info(self) -> DeviceInfo:
        """
        Ugyanaz a "all_in_one" azonosító, mint a többi entitásnál:
        => 1 eszközbe kerül minden.
        """
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
            if dev.get("id") == self._device_id and dev.get("class") == self._device_class:
                return dev
        return None

    @property
    def current_cover_position(self) -> int | None:
        """
        A 'current_opening' mező (0..100) mutatja a redőny jelenlegi állapotát.
        A HA-nak integer kerek szám kell: 0=totál zárt, 100=totál nyitott.
        """
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        return dev.get("current_opening", 0)

    @property
    def is_closed(self) -> bool | None:
        """
        A HA logika szerint is_closed=True, ha current_cover_position=0.
        """
        position = self.current_cover_position
        if position is None:
            return None
        return position <= 0

    async def async_set_cover_position(self, **kwargs):
        """
        A user beírja: "go to 20%", HA -> cover.set_cover_position -> ez a metódus.
        """
        position = kwargs.get("position")  # int 0..100
        if position is None:
            return
        await self._api.set_cover_position(self._device_class, self._device_id, position)
        await self.coordinator.async_request_refresh()

    async def async_open_cover(self, **kwargs):
        """
        A user a Lovelace-ben 'open cover' -> 100%-ra nyit.
        """
        await self._api.set_cover_position(self._device_class, self._device_id, 100)
        await self.coordinator.async_request_refresh()

    async def async_close_cover(self, **kwargs):
        """
        A user a Lovelace-ben 'close cover' -> 0%-ra zár.
        """
        await self._api.set_cover_position(self._device_class, self._device_id, 0)
        await self.coordinator.async_request_refresh()