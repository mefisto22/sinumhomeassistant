"""Közös alaposztály a SINUM entitásokhoz."""
from __future__ import annotations

from collections.abc import Awaitable
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SinumError
from .const import DOMAIN
from .coordinator import SinumConfigEntry, SinumCoordinator


def hub_device_info(entry: SinumConfigEntry) -> DeviceInfo:
    """Vezérlőnként egy eszköz (a régi, közös 'all_in_one' eszköz helyett)."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="SINUM All-in-One",
        manufacturer="SINUM",
        model="All-in-One Integration",
        configuration_url=f"http://{entry.runtime_data.client.host}",
    )


def entity_unique_id(entry_id: str, device_class: str, device_id: int, key: str) -> str:
    return f"{entry_id}_{device_class}_{device_id}_{key}"


def slug(name: str) -> str:
    return name.lower().replace(" ", "_")


class SinumEntity(CoordinatorEntity[SinumCoordinator]):
    """Egy SINUM eszköz (class + id) egy jellemzője."""

    def __init__(self, coordinator: SinumCoordinator, device: dict[str, Any], key: str) -> None:
        super().__init__(coordinator)
        self._dev_class: str = device["class"]
        self._dev_id: int = device["id"]
        entry = coordinator.config_entry
        self._attr_unique_id = entity_unique_id(entry.entry_id, self._dev_class, self._dev_id, key)
        self._attr_device_info = hub_device_info(entry)

    @property
    def device(self) -> dict[str, Any] | None:
        """Az eszköz legfrissebb adatai, vagy None, ha már nincs a vezérlőn."""
        return self.coordinator.data.get(self._dev_class, {}).get(self._dev_id)

    @property
    def available(self) -> bool:
        dev = self.device
        return super().available and dev is not None and dev.get("status") != "offline"

    async def _async_call(self, call: Awaitable[Any], *, refresh: bool = True) -> None:
        """API hívás; hibánál a felhasználó hibaüzenetet kap, sikernél frissítünk."""
        try:
            await call
        except SinumError as err:
            raise HomeAssistantError(f"SINUM: {err}") from err
        if refresh:
            await self.coordinator.async_request_refresh()

    async def _async_command(self, command: str, payload: Any = None) -> None:
        await self._async_call(
            self.coordinator.client.async_command(self._dev_class, self._dev_id, command, payload)
        )

    async def _async_patch(self, **fields: Any) -> None:
        await self._async_call(
            self.coordinator.client.async_update_device(self._dev_class, self._dev_id, fields)
        )
