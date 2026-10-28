from __future__ import annotations

import colorsys
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_TRANSITION,
    DEFAULT_MAX_KELVIN,
    DEFAULT_MIN_KELVIN,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry, SinumCoordinator
from .entity import SinumEntity, async_add_device_entities


# Egyszerre egy parancs platformonként, hogy a vezérlőt ne terheljük túl
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: SinumConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """'rgb_controller' típusú SBUS/WTP eszközök."""
    coordinator = entry.runtime_data
    async_add_device_entities(
        entry,
        async_add_entities,
        lambda devices: [
            SinumRGBControllerLight(coordinator, dev)
            for dev in devices
            if dev["class"] in ("sbus", "wtp") and dev.get("type") == "rgb_controller"
        ],
    )


def _hex_to_hs(hex_color: Any) -> tuple[float, float] | None:
    if not isinstance(hex_color, str) or len(hex_color) != 7 or not hex_color.startswith("#"):
        return None
    try:
        r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    except ValueError:
        return None
    h, s, _ = colorsys.rgb_to_hsv(r, g, b)
    return (h * 360, s * 100)


def _hs_to_hex(hs_color: tuple[float, float]) -> str:
    # Teljes értékű szín: a fényerőt a vezérlő külön ('brightness') kezeli
    r, g, b = colorsys.hsv_to_rgb(hs_color[0] / 360, hs_color[1] / 100, 1)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


class SinumRGBControllerLight(SinumEntity, LightEntity):
    """RGB vezérlő: szín 'led_color' (HEX), fényerő 'brightness' (1..100%), külön-külön."""

    _attr_name = None
    _attr_supported_features = LightEntityFeature.TRANSITION
    _attr_min_color_temp_kelvin = DEFAULT_MIN_KELVIN
    _attr_max_color_temp_kelvin = DEFAULT_MAX_KELVIN

    def __init__(self, coordinator: SinumCoordinator, device: dict[str, Any]) -> None:
        super().__init__(coordinator, device, "light")
        # Fehér csatornás szalagnál ("rgbw"/"rgbww") színhőmérséklet is állítható
        if device.get("led_strip_type", "rgb") == "rgb":
            self._attr_supported_color_modes = {ColorMode.HS}
        else:
            self._attr_supported_color_modes = {ColorMode.HS, ColorMode.COLOR_TEMP}

    @property
    def _supports_color_temp(self) -> bool:
        return ColorMode.COLOR_TEMP in (self._attr_supported_color_modes or ())

    @property
    def is_on(self) -> bool:
        dev = self.device
        return bool(dev and dev.get("state"))

    @property
    def brightness(self) -> int | None:
        """0..255 (HA) <-> 1..100 (API)."""
        dev = self.device
        level = dev.get("brightness") if dev else None
        return None if level is None else round(level * 255 / 100)

    @property
    def hs_color(self) -> tuple[float, float] | None:
        dev = self.device
        return _hex_to_hs(dev.get("led_color")) if dev else None

    @property
    def color_temp_kelvin(self) -> int | None:
        dev = self.device
        if not self._supports_color_temp or not dev or not dev.get("white_temperature"):
            return None
        return int(dev["white_temperature"])

    @property
    def color_mode(self) -> ColorMode:
        dev = self.device
        if self._supports_color_temp and dev and dev.get("color_mode") == "temperature":
            return ColorMode.COLOR_TEMP
        return ColorMode.HS

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Előbb a szín és a fényerő, utána a bekapcsolás, hogy ne villanjon a régi szín."""
        transition = _transition(kwargs)

        def args(value: Any) -> list[Any]:
            return [value] if transition is None else [value, transition]

        if ATTR_HS_COLOR in kwargs:
            await self._send_command("set_color", args(_hs_to_hex(kwargs[ATTR_HS_COLOR])))
        elif ATTR_COLOR_TEMP_KELVIN in kwargs and self._supports_color_temp:
            await self._send_command("set_temperature", args(int(kwargs[ATTR_COLOR_TEMP_KELVIN])))

        if ATTR_BRIGHTNESS in kwargs:
            # API tartomány: 1..100 (0 nem érvényes)
            level = max(1, round(kwargs[ATTR_BRIGHTNESS] * 100 / 255))
            await self._send_command("set_brightness", args(level))

        if not self.is_on:
            await self._send_command("turn_on", transition)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_command("turn_off", _transition(kwargs))
        await self.coordinator.async_request_refresh()

    async def _send_command(self, command: str, payload: Any = None) -> None:
        """Frissítés nélkül, hogy több parancs után csak egyszer kérdezzünk le."""
        await self._async_call(
            self.coordinator.client.async_command(self._dev_class, self._dev_id, command, payload),
            refresh=False,
        )


def _transition(kwargs: dict[str, Any]) -> int | None:
    """Átmenetidő tized másodpercben (API: 1..6000); None esetén a vezérlő alapértéke."""
    seconds = kwargs.get(ATTR_TRANSITION)
    if seconds is None:
        return None
    return min(6000, max(1, round(float(seconds) * 10)))
