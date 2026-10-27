from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    ATTR_TILT_POSITION,
    CoverDeviceClass,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry
from .entity import SinumEntity, async_add_device_entities, has_label

COVERING_TYPE_TO_DEVICE_CLASS = {
    "roller_shade": CoverDeviceClass.SHADE,
    "tilt_blind": CoverDeviceClass.BLIND,
    "pergola": CoverDeviceClass.AWNING,
}


# Egyszerre egy parancs platformonként, hogy a vezérlőt ne terheljük túl
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: SinumConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_device_entities(
        entry,
        async_add_entities,
        lambda devices: [
            SinumCoverEntity(coordinator, dev)
            for dev in devices
            if dev["class"] in ("sbus", "wtp") and dev.get("type") == "blind_controller"
        ],
    )


class SinumCoverEntity(SinumEntity, CoverEntity):
    """Redőny: 'current_opening' (0..100) olvasás, 'target_opening' PATCH írás.

    Tetszőleges pozíció csak 'percent_opening_control' címkével állítható (enélkül
    a vezérlő csak 0/50/100%-ot fogad el), billentés csak 'percent_tilt_control'-lal.
    """

    _attr_name = None

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator, device, "cover")
        self._attr_device_class = COVERING_TYPE_TO_DEVICE_CLASS.get(device.get("window_covering_type"))
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP
        if has_label(device, "percent_opening_control"):
            features |= CoverEntityFeature.SET_POSITION
        if has_label(device, "percent_tilt_control"):
            features |= (
                CoverEntityFeature.OPEN_TILT
                | CoverEntityFeature.CLOSE_TILT
                | CoverEntityFeature.STOP_TILT
                | CoverEntityFeature.SET_TILT_POSITION
            )
        self._attr_supported_features = features

    @property
    def current_cover_position(self) -> int | None:
        dev = self.device
        return dev.get("current_opening") if dev else None

    @property
    def current_cover_tilt_position(self) -> int | None:
        dev = self.device
        return dev.get("current_tilt") if dev else None

    @property
    def is_closed(self) -> bool | None:
        position = self.current_cover_position
        return None if position is None else position <= 0

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._async_patch(target_opening=kwargs[ATTR_POSITION])

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._async_patch(target_opening=100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._async_patch(target_opening=0)

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._async_command("stop")

    async def async_set_cover_tilt_position(self, **kwargs: Any) -> None:
        await self._async_command("tilt", kwargs[ATTR_TILT_POSITION])

    async def async_open_cover_tilt(self, **kwargs: Any) -> None:
        await self._async_command("tilt", 100)

    async def async_close_cover_tilt(self, **kwargs: Any) -> None:
        await self._async_command("tilt", 0)

    async def async_stop_cover_tilt(self, **kwargs: Any) -> None:
        await self._async_command("stop")
