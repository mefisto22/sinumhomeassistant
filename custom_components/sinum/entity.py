"""Közös alaposztály a SINUM entitásokhoz."""
from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, cast

from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import SinumAuthError, SinumConnectionError, SinumError
from .const import DOMAIN
from .coordinator import SinumConfigEntry, SinumCoordinator

CLASS_LABELS = {"sbus": "SBUS", "wtp": "WTP", "virtual": "Virtual"}

# HA 2026.10 óta a szülőeszközt id-vel kell megadni (via_device_id); a régebbi
# verziók csak az azonosító-párt (via_device) ismerik.
_HAS_VIA_DEVICE_ID = "via_device_id" in DeviceInfo.__annotations__


def hub_device_info(entry: SinumConfigEntry) -> DeviceInfo:
    """A vezérlő maga; a SINUM eszközök ehhez kapcsolódnak (via_device)."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="SINUM All-in-One",
        manufacturer="SINUM",
        model="All-in-One Integration",
        configuration_url=f"http://{entry.runtime_data.client.host}",
    )


def device_identifier(entry_id: str, device_class: str, device_id: int) -> tuple[str, str]:
    return (DOMAIN, f"{entry_id}_{device_class}_{device_id}")


def device_info(coordinator: SinumCoordinator, device: dict[str, Any]) -> DeviceInfo:
    """Minden SINUM eszköz (class + id) külön HA eszköz, a SINUM szobájának területével."""
    entry_id = coordinator.config_entry.entry_id
    dev_class, dev_type = device["class"], device.get("type") or "device"
    type_label = dev_type.replace("_", " ")
    room_id = device.get("room_id")
    info = DeviceInfo(
        identifiers={device_identifier(entry_id, dev_class, device["id"])},
        name=device.get("name") or f"{type_label.capitalize()} {device['id']}",
        manufacturer="SINUM",
        model=f"{CLASS_LABELS.get(dev_class, dev_class)} {type_label}",
        sw_version=device.get("software_version"),
        # Csak az eszköz létrehozásakor számít; utána a felhasználó beállítása marad
        suggested_area=coordinator.rooms.get(room_id) if isinstance(room_id, int) else None,
    )
    if _HAS_VIA_DEVICE_ID and coordinator.hub_device_id:
        info["via_device_id"] = coordinator.hub_device_id
    else:
        # A via_device kulcs a régebbi HA-verziók DeviceInfo típusában még szerepel
        cast(dict[str, Any], info)["via_device"] = (DOMAIN, entry_id)
    return info


def entity_unique_id(entry_id: str, device_class: str, device_id: int, key: str) -> str:
    return f"{entry_id}_{device_class}_{device_id}_{key}"


# Az API érvényes nyers páratartalom-tartománya (tized-rH%); a hőmérsékleté régiófüggő
# (SinumCoordinator.temperature_range). Ezen kívül eső érték (pl. -32768) azt jelzi,
# hogy nincs mérés.
HUMIDITY_RANGE = (0, 1000)


def measurement(
    raw: Any,
    divisor: float = 1,
    valid_range: tuple[int, int] | None = None,
    *,
    zero_is_none: bool = False,
) -> float | None:
    """Mért érték skálázva; a 'nincs érzékelő' jelzésekből None lesz.

    A termosztát 0-t ad, ha nincs hozzárendelt érzékelő, a szenzorok pedig
    tartományon kívüli értéket, ha nincs szonda vagy nincs mérés.
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if zero_is_none and raw == 0:
        return None
    if valid_range is not None and not valid_range[0] <= raw <= valid_range[1]:
        return None
    return raw / divisor


def has_label(device: dict[str, Any] | None, label: str) -> bool:
    return device is not None and label in (device.get("labels") or [])


def ensure_mode_mutable(device: dict[str, Any] | None) -> None:
    """A termosztát üzemmódja zárolható (mode_mutable = false)."""
    if device and device.get("mode_mutable") is False:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="mode_locked")


@callback
def async_add_device_entities(
    entry: SinumConfigEntry,
    async_add_entities: AddEntitiesCallback,
    build: Callable[[list[dict[str, Any]]], Sequence[Entity]],
) -> None:
    """Entitások a meglévő és a később a vezérlőn megjelenő eszközökhöz (újratöltés nélkül)."""
    coordinator = entry.runtime_data
    known: set[tuple[str, int]] = set()

    @callback
    def _async_add_new() -> None:
        new = [d for d in coordinator.devices() if (d["class"], d["id"]) not in known]
        if not new:
            return
        known.update((d["class"], d["id"]) for d in new)
        if entities := build(new):
            async_add_entities(entities)

    _async_add_new()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new))


class SinumEntity(CoordinatorEntity[SinumCoordinator]):
    """Egy SINUM eszköz (class + id) egy jellemzője."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SinumCoordinator, device: dict[str, Any], key: str) -> None:
        super().__init__(coordinator)
        self._dev_class: str = device["class"]
        self._dev_id: int = device["id"]
        entry = coordinator.config_entry
        self._attr_unique_id = entity_unique_id(entry.entry_id, self._dev_class, self._dev_id, key)
        self._attr_device_info = device_info(coordinator, device)

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
            if isinstance(err, SinumConnectionError):
                key = "cannot_connect"
            elif isinstance(err, SinumAuthError):
                key = "invalid_auth"
            else:
                key = "command_failed"
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=key,
                translation_placeholders={"error": str(err)},
            ) from err
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
