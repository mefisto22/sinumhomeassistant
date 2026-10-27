from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry
from .entity import SinumEntity, slug

SINUM_TO_HVAC = {"heating": HVACMode.HEAT, "cooling": HVACMode.COOL}
HVAC_TO_SINUM = {HVACMode.HEAT: "heating", HVACMode.COOL: "cooling", HVACMode.OFF: "off"}


async def async_setup_entry(
    hass: HomeAssistant, entry: SinumConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        SinumThermostatClimate(coordinator, dev)
        for dev in coordinator.devices("virtual")
        if dev.get("type") == "thermostat"
    )


class SinumThermostatClimate(SinumEntity, ClimateEntity):
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator, device, "climate")
        self._attr_name = f"{slug(device.get('name') or 'thermostat')}_climate"

    def _tenths(self, field: str, default: int | None = None) -> float | None:
        """Az API a hőmérsékleteket tizedfokban adja."""
        dev = self.device
        raw = dev.get(field, default) if dev else default
        return None if raw is None else raw / 10.0

    @property
    def hvac_mode(self) -> HVACMode:
        dev = self.device
        return SINUM_TO_HVAC.get(dev.get("mode"), HVACMode.OFF) if dev else HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        mode = self.hvac_mode
        if mode == HVACMode.OFF:
            return HVACAction.OFF
        # API: "state" = true, ha a termosztát éppen működik (fűt/hűt), false ha tétlen
        dev = self.device
        if not dev or not dev.get("state"):
            return HVACAction.IDLE
        return HVACAction.HEATING if mode == HVACMode.HEAT else HVACAction.COOLING

    @property
    def current_temperature(self) -> float | None:
        return self._tenths("temperature")

    @property
    def target_temperature(self) -> float | None:
        return self._tenths("target_temperature")

    @property
    def min_temp(self) -> float:
        return self._tenths("target_temperature_minimum", 50)

    @property
    def max_temp(self) -> float:
        return self._tenths("target_temperature_maximum", 350)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._async_patch(mode=HVAC_TO_SINUM.get(hvac_mode, "off"))

    async def async_set_temperature(self, **kwargs: Any) -> None:
        new_temp = kwargs.get(ATTR_TEMPERATURE)
        if new_temp is None:
            return
        await self._async_patch(target_temperature=int(new_temp * 10))
