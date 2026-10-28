"""Diagnosztika: a vezérlő nyers eszközadatai, a hitelesítő adatok nélkül."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_IP, CONF_TOKEN
from .coordinator import SinumConfigEntry

# A bejegyzés unique_id-je és címe is tartalmazhatja a hostot; a szobai panelek
# menüzárának PIN-kódja az eszközadatokban van
TO_REDACT = {CONF_IP, CONF_TOKEN, "unique_id", "title", "pin_code"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SinumConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "region": coordinator.region,
        "rooms": coordinator.rooms,
        "last_update_success": coordinator.last_update_success,
        "parents": async_redact_data(
            {f"{cls}_{parent_id}": parent for (cls, parent_id), parent in coordinator.parents.items()},
            TO_REDACT,
        ),
        "devices": async_redact_data(coordinator.data, TO_REDACT),
    }
