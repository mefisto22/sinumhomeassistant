from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry
from .entity import SinumEntity, async_add_device_entities

# type -> az állapotot tartalmazó mező
BINARY_TYPES = {
    "motion_sensor": "motion_detected",
    "two_state_input_sensor": "state",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: SinumConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_device_entities(
        entry,
        async_add_entities,
        lambda devices: [
            SinumBinarySensor(coordinator, dev)
            for dev in devices
            if dev["class"] in ("sbus", "wtp") and dev.get("type") in BINARY_TYPES
        ],
    )


class SinumBinarySensor(SinumEntity, BinarySensorEntity):
    _attr_name = None

    def __init__(self, coordinator, device) -> None:
        self._type = device["type"]
        super().__init__(coordinator, device, self._type)
        # two_state_input_sensor: általános bemenet, nincs ismert jelentése -> nincs device_class
        if self._type == "motion_sensor":
            self._attr_device_class = BinarySensorDeviceClass.MOTION

    @property
    def is_on(self) -> bool | None:
        dev = self.device
        return bool(dev.get(BINARY_TYPES[self._type], False)) if dev else None
