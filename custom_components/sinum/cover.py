from __future__ import annotations

from typing import Any

from homeassistant.components.cover import ATTR_POSITION, CoverEntity, CoverEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry
from .entity import SinumEntity, slug


async def async_setup_entry(
    hass: HomeAssistant, entry: SinumConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SinumCoverEntity(coordinator, dev)
        for dev in coordinator.devices()
        if dev["class"] in ("sbus", "wtp") and dev.get("type") == "blind_controller"
    )


class SinumCoverEntity(SinumEntity, CoverEntity):
    """Redőny: 'current_opening' (0..100) olvasás, 'target_opening' PATCH írás."""

    _attr_supported_features = (
        CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.SET_POSITION
    )

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator, device, "cover")
        self._attr_name = f"{slug(device.get('name') or 'cover')}_cover"

    @property
    def current_cover_position(self) -> int | None:
        dev = self.device
        return dev.get("current_opening", 0) if dev else None

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
