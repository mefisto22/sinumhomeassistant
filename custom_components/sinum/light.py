from __future__ import annotations

import colorsys
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    DEFAULT_MAX_KELVIN,
    DEFAULT_MIN_KELVIN,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry
from .entity import SinumEntity, slug


async def async_setup_entry(
    hass: HomeAssistant, entry: SinumConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """'rgb_controller' típusú SBUS/WTP eszközök."""
    coordinator = entry.runtime_data
    async_add_entities(
        SinumRGBControllerLight(coordinator, dev)
        for dev in coordinator.devices()
        if dev["class"] in ("sbus", "wtp") and dev.get("type") == "rgb_controller"
    )


class SinumRGBControllerLight(SinumEntity, LightEntity):
    """
    LightEntity a "type": "rgb_controller" SBUS/WTP eszközökhöz.
    Fő különbség: a szerver a "led_color" mezőben tárolja a HEX színt,
    ezért a hs_color property is onnan olvassa ki.
    """

    def __init__(self, coordinator, device) -> None:
        super().__init__(coordinator, device, "light")
        self._attr_name = f"{slug(device.get('name', 'rgb_light'))}_light"

        # LED szalag típusa
        strip_type = device.get("led_strip_type", "rgb")  # "rgb", "rgbw", "rgbww"

        # Ha "rgb" => HS, ha "rgbw"/"rgbww" => HS + COLOR_TEMP
        if strip_type == "rgb":
            self._attr_supported_color_modes = {ColorMode.HS}
        else:
            self._attr_supported_color_modes = {ColorMode.HS, ColorMode.COLOR_TEMP}
            # Kelvin alapú default tartomány (HA default értékek)
            self._attr_min_color_temp_kelvin = DEFAULT_MIN_KELVIN
            self._attr_max_color_temp_kelvin = DEFAULT_MAX_KELVIN

    @property
    def is_on(self) -> bool:
        dev = self.device
        if not dev:
            return False
        return bool(dev.get("state", False))

    @property
    def brightness(self) -> int | None:
        """
        0..255 (HA) <-> 0..100 (API)
        """
        dev = self.device
        if not dev:
            return None
        api_bri = dev.get("brightness", 100)
        return round(api_bri * 255 / 100)

    @property
    def hs_color(self) -> tuple[float, float] | None:
        """
        Itt a lényeg: a JSON-ban a szín a "led_color" mezőben van.
        Pl. dev["led_color"] = "#0072c3"
        """
        dev = self.device
        if not dev:
            return None

        # Vedd ki a "led_color" mezőt (nem a "color"-t!)
        hex_color = dev.get("led_color", "#ffffff")

        if len(hex_color) == 7 and hex_color.startswith("#"):
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            h, s, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            return (h * 360, s * 100)
        return None

    @property
    def color_temp_kelvin(self) -> int | None:
        """
        Kelvin alapú színhőmérséklet (új HA API).
        Csak, ha a COLOR_TEMP mód támogatott.
        """
        if not self._attr_supported_color_modes or ColorMode.COLOR_TEMP not in self._attr_supported_color_modes:
            return None
        dev = self.device
        if not dev:
            return None
        kelvin = dev.get("white_temperature")
        if not kelvin:
            return None
        return int(kelvin)

    @property
    def color_mode(self) -> ColorMode:
        """
        dev["color_mode"] == "temperature" => ColorMode.COLOR_TEMP,
        egyébként => ColorMode.HS
        """
        dev = self.device
        if not dev:
            return ColorMode.HS
        mode_in_api = dev.get("color_mode", "rgb")
        if (
            mode_in_api == "temperature"
            and self._attr_supported_color_modes
            and ColorMode.COLOR_TEMP in self._attr_supported_color_modes
        ):
            return ColorMode.COLOR_TEMP
        return ColorMode.HS

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Bekapcsolás + paraméterek."""
        # 1) Bekapcs
        await self._send_command("turn_on")

        # 2) Összerakjuk a brightness factor-t
        new_ha_bri = kwargs.get(ATTR_BRIGHTNESS)
        if new_ha_bri is None:
            old_dev_bri_100 = self._get_device_brightness_100()
            old_ha_bri_255 = round(old_dev_bri_100 * 255 / 100)
            brightness_factor = old_ha_bri_255 / 255
        else:
            brightness_factor = new_ha_bri / 255
            # Elküldjük a set_brightness parancsot
            # API tartomány: 1..100 (0 nem érvényes)
            api_bri = max(1, round(new_ha_bri * 100 / 255))
            await self._send_command("set_brightness", [api_bri])

        # 3) color_temp (Kelvin alapú új API)
        if (
            ATTR_COLOR_TEMP_KELVIN in kwargs
            and self._attr_supported_color_modes
            and ColorMode.COLOR_TEMP in self._attr_supported_color_modes
        ):
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            await self._send_command("set_temperature", [kelvin])

        # 4) hs_color
        if ATTR_HS_COLOR in kwargs:
            (hh, ss) = kwargs[ATTR_HS_COLOR]
            h = hh / 360.0
            s = ss / 100.0
            (r, g, b) = colorsys.hsv_to_rgb(h, s, brightness_factor)
            rr = round(r * 255)
            gg = round(g * 255)
            bb = round(b * 255)
            hex_str = f"#{rr:02x}{gg:02x}{bb:02x}"

            await self._send_command("set_color", [hex_str])

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Kikapcs."""
        await self._send_command("turn_off")
        await self.coordinator.async_request_refresh()

    def _get_device_brightness_100(self) -> int:
        """
        Lekérdezzük a koordinátor adatából a brightness mezőt (0..100).
        Ha nincs, 100 a default.
        """
        dev = self.device
        if not dev:
            return 100
        return dev.get("brightness", 100)

    async def _send_command(self, command: str, payload_data: Any = None) -> None:
        """POST /devices/<class>/<id>/command/<command>; hiba esetén HomeAssistantError."""
        await self._async_call(
            self.coordinator.client.async_command(self._dev_class, self._dev_id, command, payload_data),
            refresh=False,
        )
