from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration from a config entry."""
    # Ha több platformot is használsz, mindet ide tedd:
    await hass.config_entries.async_forward_entry_setups(
        entry,
        ["sensor", "select", "number", "climate", "switch", "cover", "light", "binary_sensor"]   # <--- LÉNYEGES
    )
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload integration."""
    return await hass.config_entries.async_unload_platforms(
        entry,
        ["sensor", "select", "number", "climate", "switch", "cover", "light", "binary_sensor"]   # <--- LÉNYEGES
    )


