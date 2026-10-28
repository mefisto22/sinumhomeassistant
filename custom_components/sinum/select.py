from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry, SinumCoordinator
from .entity import SinumEntity, async_add_device_entities, ensure_mode_mutable


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
            SinumThermostatModeSelect(coordinator, dev)
            for dev in devices
            if dev["class"] == "virtual" and dev.get("type") == "thermostat"
        ],
    )


class SinumThermostatModeSelect(SinumEntity, SelectEntity):
    """A termosztát 'mode' mezője (off/heating/cooling); a klíma entitás ugyanezt tudja."""

    _attr_options = ["off", "heating", "cooling"]
    _attr_translation_key = "mode"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: SinumCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device, "mode_select")

    @property
    def current_option(self) -> str | None:
        dev = self.device
        return dev.get("mode") if dev else None

    async def async_select_option(self, option: str) -> None:
        ensure_mode_mutable(self.device)
        await self._async_patch(mode=option)
