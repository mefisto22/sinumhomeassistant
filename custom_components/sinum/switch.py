from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry, SinumCoordinator
from .entity import SinumEntity, async_add_device_entities


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
            SinumRelaySwitch(coordinator, dev)
            for dev in devices
            if dev["class"] in ("sbus", "wtp") and dev.get("type") == "relay"
        ],
    )


class SinumRelaySwitch(SinumEntity, SwitchEntity):

    def __init__(self, coordinator: SinumCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device, "relay", primary=True)

    @property
    def is_on(self) -> bool | None:
        dev = self.device
        return bool(dev.get("state")) if dev else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_command("turn_on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_command("turn_off")
