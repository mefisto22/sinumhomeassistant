"""Egyetlen koordinátor, ami az összes eszközosztályt lekérdezi."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SinumAuthError, SinumClient, SinumError
from .const import DEVICE_CLASSES, DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

# class -> id -> eszköz
type SinumData = dict[str, dict[int, dict[str, Any]]]
type SinumConfigEntry = ConfigEntry[SinumCoordinator]


class SinumCoordinator(DataUpdateCoordinator[SinumData]):
    """GET /devices/sbus, /devices/wtp, /devices/virtual egy menetben."""

    config_entry: SinumConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SinumConfigEntry, client: SinumClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    async def _async_update_data(self) -> SinumData:
        try:
            results = await asyncio.gather(
                *(self.client.async_get_devices(cls) for cls in DEVICE_CLASSES)
            )
        except SinumAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SinumError as err:
            raise UpdateFailed(str(err)) from err
        return {
            cls: {dev["id"]: dev for dev in devices}
            for cls, devices in zip(DEVICE_CLASSES, results)
        }

    def devices(self, device_class: str | None = None) -> list[dict[str, Any]]:
        """Az aktuális eszközök listája (opcionálisan egy osztályra szűrve)."""
        classes = DEVICE_CLASSES if device_class is None else (device_class,)
        return [dev for cls in classes for dev in self.data.get(cls, {}).values()]
