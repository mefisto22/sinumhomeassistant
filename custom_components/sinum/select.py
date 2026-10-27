from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry
from .entity import SinumEntity, ensure_mode_mutable, slug


async def async_setup_entry(
    hass: HomeAssistant, entry: SinumConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SinumThermostatModeSelect(coordinator, dev)
        for dev in coordinator.devices("virtual")
        if dev.get("type") == "thermostat"
    )


class SinumThermostatModeSelect(SinumEntity, SelectEntity):
    """A termosztát 'mode' mezője (off/heating/cooling)."""

    _attr_options = ["off", "heating", "cooling"]

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator, device, "mode_select")
        self._attr_name = f"{slug(device.get('name') or 'thermostat')}_mode_select"

    @property
    def current_option(self) -> str | None:
        dev = self.device
        return dev.get("mode") if dev else None

    async def async_select_option(self, option: str) -> None:
        ensure_mode_mutable(self.device)
        await self._async_patch(mode=option)
