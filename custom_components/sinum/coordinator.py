"""Egyetlen koordinátor, ami az összes eszközosztályt lekérdezi."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SinumAuthError, SinumClient, SinumError
from .const import DEVICE_CLASSES, DOMAIN, PARENT_CLASSES, UPDATE_INTERVAL

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
        # A beállításkor egyszer lekérdezett kiegészítő adatok
        self.rooms: dict[int, str] = {}
        self.region = "eu"
        # Fizikai modulok: (osztály, parent_id) -> modul adatai
        self.parents: dict[tuple[str, int], dict[str, Any]] = {}
        # A vezérlő HA eszköze; a SINUM eszközök ehhez kapcsolódnak
        self.hub_device_id: str | None = None

    async def async_load_metadata(self) -> None:
        """Szobanevek (területekhez), régió (mértékegységekhez) és a fizikai modulok
        (eszköznevekhez); hiba esetén alapértékek."""
        try:
            self.rooms = await self.client.async_get_rooms()
        except SinumAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SinumError as err:
            _LOGGER.debug("Could not read SINUM rooms: %s", err)
        for cls in PARENT_CLASSES:
            try:
                parents = await self.client.async_get_parent_devices(cls)
            except SinumAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except SinumError as err:
                _LOGGER.debug("Could not read SINUM %s modules: %s", cls, err)
                continue
            self.parents.update({(cls, parent["id"]): parent for parent in parents})
        try:
            self.region = await self.client.async_get_region()
        except SinumError as err:
            _LOGGER.debug("Could not read SINUM locale, assuming 'eu': %s", err)

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

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        """Az API a régió szerinti egységben (tizedfok) adja a hőmérsékletet."""
        return UnitOfTemperature.FAHRENHEIT if self.region == "us" else UnitOfTemperature.CELSIUS

    @property
    def temperature_range(self) -> tuple[int, int]:
        """Érvényes nyers hőmérséklet-tartomány (-40..100 °C, ill. -40..212 °F)."""
        return (-400, 2120) if self.region == "us" else (-400, 1000)

    def devices(self, device_class: str | None = None) -> list[dict[str, Any]]:
        """Az aktuális eszközök listája (opcionálisan egy osztályra szűrve)."""
        classes = DEVICE_CLASSES if device_class is None else (device_class,)
        return [dev for cls in classes for dev in self.data.get(cls, {}).values()]
