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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry
from .entity import (
    HUMIDITY_RANGE,
    TEMPERATURE_RANGE,
    SinumEntity,
    ensure_mode_mutable,
    has_label,
    measurement,
    slug,
)

SINUM_TO_HVAC = {"heating": HVACMode.HEAT, "cooling": HVACMode.COOL}
HVAC_TO_SINUM = {HVACMode.HEAT: "heating", HVACMode.COOL: "cooling", HVACMode.OFF: "off"}

# A célhőmérséklet-módok (target_temperature_mode.current) presetként jelennek meg
PRESET_SCHEDULE = "schedule"
PRESET_CONSTANT = "constant"
PRESET_TIME_LIMITED = "time_limited"


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
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL]
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_translation_key = "thermostat"

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator, device, "climate")
        self._attr_name = f"{slug(device.get('name') or 'thermostat')}_climate"
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        # Régebbi vezérlőkön a célhőmérséklet-mód hiányozhat
        if isinstance(device.get("target_temperature_mode"), dict):
            self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE

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
        # 0: nincs hozzárendelt hőérzékelő
        dev = self.device
        return measurement(
            dev and dev.get("temperature"), 10, TEMPERATURE_RANGE, zero_is_none=True
        )

    @property
    def current_humidity(self) -> float | None:
        dev = self.device
        return measurement(dev and dev.get("humidity"), 10, HUMIDITY_RANGE, zero_is_none=True)

    @property
    def target_temperature(self) -> float | None:
        return self._tenths("target_temperature")

    @property
    def min_temp(self) -> float:
        return self._tenths("target_temperature_minimum", 50)

    @property
    def max_temp(self) -> float:
        return self._tenths("target_temperature_maximum", 350)

    @property
    def preset_mode(self) -> str | None:
        dev = self.device
        mode = dev.get("target_temperature_mode") if dev else None
        return mode.get("current") if isinstance(mode, dict) else None

    @property
    def preset_modes(self) -> list[str]:
        presets = [PRESET_CONSTANT]
        if has_label(self.device, "has_schedule"):
            presets.insert(0, PRESET_SCHEDULE)
        # Az időkorlátos mód csak megjelenik; elindításához időtartam kell (SINUM app)
        if self.preset_mode == PRESET_TIME_LIMITED:
            presets.append(PRESET_TIME_LIMITED)
        return presets

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode == self.preset_mode:
            return
        if preset_mode == PRESET_SCHEDULE:
            await self._async_command("enable_schedule_mode")
        elif preset_mode == PRESET_CONSTANT:
            dev = self.device
            target = dev.get("target_temperature") if dev else None
            if target is None:
                raise HomeAssistantError("SINUM: the thermostat has no target temperature")
            await self._async_command("enable_constant_mode", target)
        else:
            raise HomeAssistantError(f"SINUM: preset '{preset_mode}' cannot be activated")

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        ensure_mode_mutable(self.device)
        await self._async_patch(mode=HVAC_TO_SINUM.get(hvac_mode, "off"))

    async def async_set_temperature(self, **kwargs: Any) -> None:
        new_temp = kwargs.get(ATTR_TEMPERATURE)
        if new_temp is None:
            return
        # Ütemezés módban a vezérlő ettől állandó módba vált
        await self._async_patch(target_temperature=round(new_temp * 10))
