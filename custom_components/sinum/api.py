import aiohttp
import logging
import json

_LOGGER = logging.getLogger(__name__)

class SinumAPI:
    """A SINUM rendszer API-hívásainak kezelője."""

    def __init__(self, ip: str, token: str):
        """
        :param ip: pl. '192.168.22.22'
        :param token: A cURL-ből ismert hitelesítési token
        """
        self.base_url = f"http://{ip}/api/v1"
        self.headers = {
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    #
    # ========== Virtuális eszközök (thermostat) ==========
    #

    async def get_virtual_devices(self):
        url = f"{self.base_url}/devices/virtual"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers) as resp:
                    resp.raise_for_status()

                    # Mindig nyers bájtokat olvasunk, majd több kódolással próbálunk JSON-t pars-olni.
                    raw = await resp.read()
                    raw_data = None
                    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1250", "cp1252"):
                        try:
                            raw_text = raw.decode(enc)
                            raw_data = json.loads(raw_text)
                            break
                        except Exception:
                            continue

                    if raw_data is None:
                        _LOGGER.error(
                            "Virtual devices: JSON dekódolás sikertelen "
                            "(content_type=%s, charset=%s, size=%dB, first200=%r)",
                            getattr(resp, "content_type", None),
                            getattr(resp, "charset", None),
                            len(raw),
                            raw[:200],
                        )
                        return []

                    # Kimenet normalizálás (dict-ben 'data' lista, vagy top-level lista)
                    if isinstance(raw_data, dict):
                        if isinstance(raw_data.get("data"), list):
                            return raw_data["data"]
                        for k in ("items", "results", "devices"):
                            if isinstance(raw_data.get(k), list):
                                return raw_data[k]
                        return []
                    elif isinstance(raw_data, list):
                        return raw_data
                    return []
            except Exception as e:
                _LOGGER.error("Error fetching virtual devices: %s", e)
                return []

    async def set_thermostat_mode(self, device_id: int, new_mode: str):
        url = f"{self.base_url}/devices/virtual/{device_id}"
        payload = {
            "id": device_id,
            "mode": new_mode
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.patch(url, headers=self.headers, json=payload) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except Exception as e:
                _LOGGER.error("Error setting thermostat mode: %s", e)
                return None

    async def set_thermostat_target_temperature(self, device_id: int, new_target: int):
        url = f"{self.base_url}/devices/virtual/{device_id}"
        payload = {
            "id": device_id,
            "target_temperature": new_target
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.patch(url, headers=self.headers, json=payload) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except Exception as e:
                _LOGGER.error("Error setting target temperature: %s", e)
                return None

    #
    # ========== SBUS + WTP -> relék, redőnyök, stb. ==========
    #

    async def get_sbus_devices(self):
        url = f"{self.base_url}/devices/sbus"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers) as resp:
                    resp.raise_for_status()
                    raw_data = await resp.json()
                    if isinstance(raw_data, dict) and "data" in raw_data:
                        return raw_data["data"]
                    return []
            except Exception as e:
                _LOGGER.error("Error fetching sbus devices: %s", e)
                return []

    async def get_wtp_devices(self):
        url = f"{self.base_url}/devices/wtp"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, headers=self.headers) as resp:
                    resp.raise_for_status()
                    raw_data = await resp.json()
                    if isinstance(raw_data, dict) and "data" in raw_data:
                        return raw_data["data"]
                    return []
            except Exception as e:
                _LOGGER.error("Error fetching wtp devices: %s", e)
                return []

    #
    # ========== ÚJ: Analog Output ==========
    #

    async def set_analog_output_value(self, device_id: int, value: int):
        """
        Set the value of an analog output.
        POST /devices/sbus/<device_id>/command/set_value
        Body: { "set_value": <value> }
        """
        url = f"{self.base_url}/devices/sbus/{device_id}/command/set_value"
        payload = {"set_value": value}
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as e:
                error_body = await e.response.text()
                _LOGGER.error(f"Error setting analog output value for device {device_id}: {e.status}, body='{error_body}', url='{url}'")
                return None
            except Exception as e:
                _LOGGER.error(f"Error setting analog output value for device {device_id}: {e}")
                return None

    #
    # ========== ÚJ: PWM Duty Cycle Beállítása ==========
    #

    async def set_pwm_duty_cycle(self, device_class: str, device_id: int, duty_cycle: int):
        """
        Set the PWM duty cycle.
        POST /devices/<device_class>/<device_id>/command/set_duty_cycle
        Body: { "set_duty_cycle": <value> }
        """
        url = f"{self.base_url}/devices/{device_class}/{device_id}/command/set_duty_cycle"
        payload = {"set_duty_cycle": duty_cycle}  # "set_duty_cycle" várható
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json=payload) as resp:
                    if resp.status == 422:
                        # Részletes hibaüzenet naplózása
                        error_details = await resp.text()
                        _LOGGER.error(f"Unprocessable Entity when setting PWM duty cycle for device {device_id} ({device_class}): {error_details}")
                        return None
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as e:
                error_body = await e.response.text()
                _LOGGER.error(f"Client response error setting PWM duty cycle for device {device_id} ({device_class}): {e.status}, body='{error_body}', url='{url}'")
                return None
            except Exception as e:
                _LOGGER.error(f"Error setting PWM duty cycle for device {device_id} ({device_class}): {e}")
                return None

    #
    # ========== Egyéb eszközkezelések ==========
    #

    async def get_all_relays(self):
        sbus_list = await self.get_sbus_devices()
        wtp_list = await self.get_wtp_devices()

        sbus_relays = [d for d in sbus_list if d.get("type") == "relay"]
        for dev in sbus_relays:
            dev["class"] = "sbus"

        wtp_relays = [d for d in wtp_list if d.get("type") == "relay"]
        for dev in wtp_relays:
            dev["class"] = "wtp"

        return sbus_relays + wtp_relays

    async def relay_turn_on(self, device_class: str, device_id: int):
        url = f"{self.base_url}/devices/{device_class}/{device_id}/command/turn_on"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json={}) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as e:
                error_body = await e.response.text()
                _LOGGER.error(f"Client response error turning relay ON for device {device_id} ({device_class}): {e.status}, body='{error_body}', url='{url}'")
                return None
            except Exception as e:
                _LOGGER.error("Error turning relay ON: %s", e)
                return None

    async def relay_turn_off(self, device_class: str, device_id: int):
        url = f"{self.base_url}/devices/{device_class}/{device_id}/command/turn_off"
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json={}) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as e:
                error_body = await e.response.text()
                _LOGGER.error(f"Client response error turning relay OFF for device {device_id} ({device_class}): {e.status}, body='{error_body}', url='{url}'")
                return None
            except Exception as e:
                _LOGGER.error("Error turning relay OFF: %s", e)
                return None

    async def get_all_blind_controllers(self):
        sbus_list = await self.get_sbus_devices()
        wtp_list = await self.get_wtp_devices()

        sbus_covers = [
            dev for dev in sbus_list if dev.get("type") == "blind_controller"
        ]
        for dev in sbus_covers:
            dev["class"] = "sbus"

        wtp_covers = [
            dev for dev in wtp_list if dev.get("type") == "blind_controller"
        ]
        for dev in wtp_covers:
            dev["class"] = "wtp"

        return sbus_covers + wtp_covers

    async def set_cover_position(self, device_class: str, device_id: int, position: int):
        url = f"{self.base_url}/devices/{device_class}/{device_id}"
        payload = {
            "id": device_id,
            "target_opening": position
        }
        async with aiohttp.ClientSession() as session:
            try:
                async with session.patch(url, headers=self.headers, json=payload) as resp:
                    resp.raise_for_status()
                    return await resp.json()
            except aiohttp.ClientResponseError as e:
                error_body = await e.response.text()
                _LOGGER.error(f"Client response error setting cover position for device {device_id} ({device_class}): {e.status}, body='{error_body}', url='{url}'")
                return None
            except Exception as e:
                _LOGGER.error("Error setting cover position: %s", e)
                return None