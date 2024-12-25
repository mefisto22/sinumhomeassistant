import logging
import colorsys
from datetime import timedelta
from typing import Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)
from homeassistant.components.light import (
    LightEntity,
    ATTR_BRIGHTNESS,
    ATTR_HS_COLOR,
    ATTR_COLOR_TEMP,
    COLOR_MODE_HS,
    COLOR_MODE_COLOR_TEMP,
    LightEntityFeature,
)

from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.device_registry import DeviceInfo

from .api import SinumAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the 'light' platform for 'rgb_controller' devices."""
    ip = config_entry.data["ip"]
    token = config_entry.data["token"]
    api = SinumAPI(ip, token)

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="SINUM RGB Controllers",
        update_method=_create_rgb_fetcher(api),
        update_interval=timedelta(seconds=1),
    )

    try:
        # Első frissítés
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"RGB controllers fetch failed: {err}") from err

    devices = coordinator.data or []

    entities = []
    for dev in devices:
        # dev["type"] == "rgb_controller"
        device_class = dev.get("class")  # "wtp" / "sbus"
        device_id = dev.get("id")
        name_in_api = dev.get("name", "rgb_light")
        base_name = name_in_api.lower().replace(" ", "_")

        entities.append(
            SinumRGBControllerLight(
                coordinator=coordinator,
                device=dev,
                device_class=device_class,
                device_id=device_id,
                base_name=base_name,
                api=api
            )
        )

    async_add_entities(entities)


def _create_rgb_fetcher(api: SinumAPI):
    """
    Egy factory-függvény, ami visszaad egy aszinkron _fetch_rgb_controllers
    függvényt, hogy a coordinator update_method-ként tudja használni.
    """
    async def _fetch_rgb_controllers():
        sbus_list = await api.get_sbus_devices()
        wtp_list = await api.get_wtp_devices()

        sbus_lights = [d for d in sbus_list if d.get("type") == "rgb_controller"]
        for dev in sbus_lights:
            dev["class"] = "sbus"

        wtp_lights = [d for d in wtp_list if d.get("type") == "rgb_controller"]
        for dev in wtp_lights:
            dev["class"] = "wtp"

        return sbus_lights + wtp_lights

    return _fetch_rgb_controllers


class SinumRGBControllerLight(CoordinatorEntity, LightEntity):
    """
    LightEntity a "type": "rgb_controller" SBUS/WTP eszközökhöz.
    Fő különbség: a szerver a "led_color" mezőben tárolja a HEX színt,
    ezért a hs_color property is onnan olvassa ki.
    """

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device: dict,
        device_class: str,
        device_id: int,
        base_name: str,
        api: SinumAPI
    ):
        super().__init__(coordinator)
        self._device = device
        self._device_class = device_class
        self._device_id = device_id
        self._api = api

        # Entitás paraméterek
        self._attr_name = f"{base_name}_light"
        self._attr_unique_id = f"{DOMAIN}_{device_class}_{device_id}_light"

        # LED szalag típusa
        strip_type = device.get("led_strip_type", "rgb")  # "rgb", "rgbw", "rgbww"

        # Ha "rgb" => HS, ha "rgbw"/"rgbww" => HS + color_temp
        if strip_type == "rgb":
            self._attr_supported_color_modes = {COLOR_MODE_HS}
        else:
            self._attr_supported_color_modes = {COLOR_MODE_HS, COLOR_MODE_COLOR_TEMP}

    @property
    def device_info(self) -> DeviceInfo:
        """Egyetlen eszközbe csoportosítjuk (all_in_one)."""
        return DeviceInfo(
            identifiers={(DOMAIN, "all_in_one")},
            name="SINUM All-in-One",
            manufacturer="SINUM",
            model="RGB Controller Integration",
        )

    def _find_device_in_coordinator(self):
        data = self.coordinator.data
        if not data:
            return None
        for dev in data:
            if dev.get("id") == self._device_id and dev.get("class") == self._device_class:
                return dev
        return None

    @property
    def is_on(self) -> bool:
        dev = self._find_device_in_coordinator()
        if not dev:
            return False
        return bool(dev.get("state", False))

    @property
    def brightness(self) -> int | None:
        """
        0..255 (HA) <-> 0..100 (API)
        """
        dev = self._find_device_in_coordinator()
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
        dev = self._find_device_in_coordinator()
        if not dev:
            return None

        # Vedd ki a "led_color" mezőt (nem a "color"-t!)
        hex_color = dev.get("led_color", "#ffffff")

        if len(hex_color) == 7 and hex_color.startswith("#"):
            r = int(hex_color[1:3], 16)
            g = int(hex_color[3:5], 16)
            b = int(hex_color[5:7], 16)
            h, s, _ = colorsys.rgb_to_hsv(r/255, g/255, b/255)
            return (h*360, s*100)
        return None

    @property
    def color_temp(self) -> int | None:
        """
        Kelvin => HA mired.
        Csak, ha a color_temp mód támogatott.
        """
        if COLOR_MODE_COLOR_TEMP not in self._attr_supported_color_modes:
            return None
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        kelvin = dev.get("white_temperature")
        if not kelvin:
            return None
        return int(1_000_000 / kelvin)

    @property
    def color_mode(self) -> str:
        """
        dev["color_mode"] == "temperature" => COLOR_MODE_COLOR_TEMP,
        egyébként => COLOR_MODE_HS
        """
        dev = self._find_device_in_coordinator()
        if not dev:
            return COLOR_MODE_HS
        mode_in_api = dev.get("color_mode", "rgb")
        if (mode_in_api == "temperature") and (COLOR_MODE_COLOR_TEMP in self._attr_supported_color_modes):
            return COLOR_MODE_COLOR_TEMP
        return COLOR_MODE_HS

    async def async_turn_on(self, **kwargs) -> None:
        """Bekapcsolás + paraméterek."""
        # 1) Bekapcs
        await self._send_command("turn_on", {})

        # 2) Összerakjuk a brightness factor-t
        new_ha_bri = kwargs.get(ATTR_BRIGHTNESS)
        if new_ha_bri is None:
            old_dev_bri_100 = self._get_device_brightness_100()
            old_ha_bri_255 = round(old_dev_bri_100 * 255 / 100)
            brightness_factor = old_ha_bri_255 / 255
        else:
            brightness_factor = new_ha_bri / 255
            # Elküldjük a set_brightness parancsot
            api_bri = round(new_ha_bri * 100 / 255)
            await self._send_command("set_brightness", [api_bri])

        # 3) color_temp
        if ATTR_COLOR_TEMP in kwargs and COLOR_MODE_COLOR_TEMP in self._attr_supported_color_modes:
            mired = kwargs[ATTR_COLOR_TEMP]
            kelvin = round(1_000_000 / mired)
            await self._send_command("set_temperature", [kelvin])

        # 4) hs_color
        if ATTR_HS_COLOR in kwargs:
            (hh, ss) = kwargs[ATTR_HS_COLOR]
            h = hh / 360.0
            s = ss / 100.0
            (r, g, b) = colorsys.hsv_to_rgb(h, s, brightness_factor)
            rr = round(r*255)
            gg = round(g*255)
            bb = round(b*255)
            hex_str = f"#{rr:02x}{gg:02x}{bb:02x}"

            await self._send_command("set_color", [hex_str])

        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        """Kikapcs."""
        await self._send_command("turn_off", {})
        await self.coordinator.async_request_refresh()

    def _get_device_brightness_100(self) -> int:
        """
        Lekérdezzük a koordinátor adatából a brightness mezőt (0..100).
        Ha nincs, 100 a default.
        """
        dev = self._find_device_in_coordinator()
        if not dev:
            return 100
        return dev.get("brightness", 100)

    async def _send_command(self, command: str, payload_data):
        """
        POST /devices/<class>/<id>/command/<command>, body=...
        """
        import aiohttp

        url = f"{self._api.base_url}/devices/{self._device_class}/{self._device_id}/command/{command}"

        body = {}
        if command == "set_color":
            body = {"set_color": payload_data}
        elif command == "set_brightness":
            body = {"set_brightness": payload_data}
        elif command == "set_temperature":
            body = {"set_temperature": payload_data}

        _LOGGER.debug("Sending command=%s body=%s to device=%s/%s", command, body, self._device_class, self._device_id)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url,
                    headers=self._api.headers,
                    json=body
                ) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except Exception as e:
                _LOGGER.debug("Error sending %s command: %s", command, e)
                return None