"""A SINUM e-Home helyi API (http://<host>/api/v1) kliense."""
from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)

# A vezérlő nem mindig küld megbízható charset-et. Sorrend: UTF-8 (BOM-mal vagy anélkül),
# aztán a magyar ékezeteket helyesen kezelő cp1250, végül latin-1, ami mindent dekódol.
_ENCODINGS = ("utf-8-sig", "cp1250", "latin-1")


class SinumError(Exception):
    """Általános SINUM API hiba."""


class SinumConnectionError(SinumError):
    """A vezérlő nem érhető el (hálózati hiba vagy timeout)."""


class SinumAuthError(SinumError):
    """A vezérlő elutasította az API tokent."""


class SinumApiError(SinumError):
    """A vezérlő hibás vagy értelmezhetetlen választ adott."""


def normalize_host(host: str) -> str:
    """'http://Sinum.local:80/api/v1/' -> 'sinum.local:80'."""
    host = host.strip()
    for prefix in ("http://", "https://"):
        if host.lower().startswith(prefix):
            host = host[len(prefix):]
    return host.split("/", 1)[0].lower()


def _decode_json(raw: bytes, path: str) -> Any:
    for enc in _ENCODINGS:
        try:
            return json.loads(raw.decode(enc))
        except (UnicodeDecodeError, ValueError):
            continue
    raise SinumApiError(f"{path}: invalid JSON response ({len(raw)} bytes)")


def _error_message(raw: bytes) -> str:
    """Az API hibaválaszából ({"error": {"message": ...}}) kiolvasható üzenet."""
    try:
        body = _decode_json(raw, "")
    except SinumApiError:
        return raw[:200].decode("latin-1")
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        return str(body["error"].get("message", body["error"]))
    return str(body)[:200]


class SinumClient:
    """Egy SINUM vezérlő API-ja, a HA közös aiohttp session-jével."""

    def __init__(self, session: aiohttp.ClientSession, host: str, token: str) -> None:
        self._session = session
        self.host = normalize_host(host)
        self.base_url = f"http://{self.host}/api/v1"
        self._headers = {
            "Authorization": token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _request(
        self, method: str, path: str, payload: Any = None, *, allow_404: bool = False
    ) -> Any:
        url = f"{self.base_url}{path}"
        try:
            async with self._session.request(
                method, url, headers=self._headers, json=payload, timeout=REQUEST_TIMEOUT
            ) as resp:
                status = resp.status
                raw = await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise SinumConnectionError(
                f"{method} {path}: {err or type(err).__name__}"
            ) from err

        if status in (401, 403):
            raise SinumAuthError(f"{method} {path}: HTTP {status}")
        if status == 404 and allow_404:
            return None
        if status >= 400:
            raise SinumApiError(f"{method} {path}: HTTP {status} {_error_message(raw)}")
        if not raw:
            return None
        return _decode_json(raw, path)

    async def async_check_connection(self) -> None:
        """Kapcsolat és token ellenőrzése (config flow)."""
        data = await self._request("GET", "/devices/virtual")
        if not isinstance(data, (dict, list)):
            raise SinumApiError("/devices/virtual: unexpected response format")

    async def async_get_devices(self, device_class: str) -> list[dict[str, Any]]:
        """GET /devices/<class> -> eszközlista; minden elem 'class' mezőt kap."""
        path = f"/devices/{device_class}"
        data = await self._request("GET", path, allow_404=True)
        if data is None:
            # Ezt az eszközosztályt a vezérlő nem ismeri
            return []
        if isinstance(data, dict):
            data = next(
                (data[k] for k in ("data", "items", "results", "devices") if isinstance(data.get(k), list)),
                None,
            )
        if not isinstance(data, list):
            raise SinumApiError(f"{path}: unexpected response format")
        devices = [d for d in data if isinstance(d, dict) and "id" in d]
        for dev in devices:
            dev["class"] = device_class
        return devices

    async def async_get_rooms(self) -> dict[int, str]:
        """GET /rooms -> {szoba id: név}."""
        data = await self._request("GET", "/rooms", allow_404=True)
        rooms = data.get("data") if isinstance(data, dict) else data
        if not isinstance(rooms, list):
            return {}
        return {
            room["id"]: room["name"]
            for room in rooms
            if isinstance(room, dict) and "id" in room and room.get("name")
        }

    async def async_get_region(self) -> str:
        """GET /settings/locale -> 'eu' (°C, lx) vagy 'us' (°F, fc)."""
        data = await self._request("GET", "/settings/locale", allow_404=True)
        locale = data.get("data") if isinstance(data, dict) else None
        region = locale.get("region") if isinstance(locale, dict) else None
        return region if region in ("eu", "us") else "eu"

    async def async_command(
        self, device_class: str, device_id: int, command: str, payload: Any = None
    ) -> Any:
        """POST /devices/<class>/<id>/command/<command>, body: {<command>: payload} vagy {}."""
        body = {} if payload is None else {command: payload}
        _LOGGER.debug("Command %s/%s %s %s", device_class, device_id, command, body)
        return await self._request(
            "POST", f"/devices/{device_class}/{device_id}/command/{command}", body
        )

    async def async_update_device(
        self, device_class: str, device_id: int, fields: dict[str, Any]
    ) -> Any:
        """PATCH /devices/<class>/<id> a megadott mezőkkel."""
        _LOGGER.debug("Patch %s/%s %s", device_class, device_id, fields)
        return await self._request(
            "PATCH", f"/devices/{device_class}/{device_id}", {"id": device_id, **fields}
        )
