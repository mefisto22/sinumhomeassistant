from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import LIGHT_LUX, PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry, SinumCoordinator
from .entity import SinumEntity, slug


async def async_setup_entry(
    hass: HomeAssistant, entry: SinumConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []

    # Termosztátok (virtuális eszközök): hőmérséklet, páratartalom, üzemmód, célhőmérséklet
    for count, dev in enumerate(
        (d for d in coordinator.devices("virtual") if d.get("type") == "thermostat"), start=1
    ):
        base = slug(dev.get("name") or f"thermostat{count}")
        entities += [
            SinumSensor(coordinator, dev, "temp", f"{base}_temp", "temperature", 10, TEMPERATURE),
            SinumSensor(coordinator, dev, "humidity", f"{base}_humidity", "humidity", 10, HUMIDITY),
            SinumSensor(coordinator, dev, "mode", f"{base}_mode", "mode", None, None),
            SinumSensor(
                coordinator, dev, "tempsetpoint", f"{base}_tempsetpoint", "target_temperature", 10, TEMPERATURE
            ),
        ]

    sbus_wtp = [d for d in coordinator.devices() if d["class"] in ("sbus", "wtp")]
    for dev in sbus_wtp:
        base = slug(dev.get("name", "unknown_sensor"))
        dev_type = dev.get("type")
        if dev_type == "temperature_sensor":
            entities.append(
                SinumSensor(coordinator, dev, "temperature", f"{base}_temperature", "temperature", 10, TEMPERATURE)
            )
        elif dev_type == "humidity_sensor":
            entities.append(
                SinumSensor(coordinator, dev, "humidity", f"{base}_humidity", "humidity", 10, HUMIDITY)
            )
        elif dev_type == "light_sensor":
            entities.append(
                SinumSensor(coordinator, dev, "illuminance", f"{base}_light", "illuminance", None, ILLUMINANCE)
            )

    # Akkumulátor: egy fizikai eszköz (address) több logikai eszközként jelenik meg,
    # ezért címenként csak egy szenzort hozunk létre.
    seen_addresses: set[Any] = set()
    for dev in sbus_wtp:
        address = dev.get("address")
        if "battery" not in dev or address is None or address in seen_addresses:
            continue
        seen_addresses.add(address)
        base = slug(f"{dev.get('software_version', 'unknown_version')}_battery")
        entities.append(SinumSensor(coordinator, dev, "battery", f"{base}_battery", "battery", None, BATTERY))

    async_add_entities(entities)


# (device_class, unit, state_class)
TEMPERATURE = (SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS, SensorStateClass.MEASUREMENT)
HUMIDITY = (SensorDeviceClass.HUMIDITY, PERCENTAGE, SensorStateClass.MEASUREMENT)
ILLUMINANCE = (SensorDeviceClass.ILLUMINANCE, LIGHT_LUX, SensorStateClass.MEASUREMENT)
BATTERY = (SensorDeviceClass.BATTERY, PERCENTAGE, SensorStateClass.MEASUREMENT)


class SinumSensor(SinumEntity, SensorEntity):
    """Egy eszközmező értéke, opcionális osztóval (pl. tizedfok -> fok)."""

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device: dict[str, Any],
        key: str,
        name: str,
        field: str,
        divisor: int | None,
        kind: tuple[SensorDeviceClass, str, SensorStateClass] | None,
    ) -> None:
        super().__init__(coordinator, device, key)
        self._attr_name = name
        self._field = field
        self._divisor = divisor
        if kind is not None:
            (
                self._attr_device_class,
                self._attr_native_unit_of_measurement,
                self._attr_state_class,
            ) = kind

    @property
    def native_value(self) -> Any:
        dev = self.device
        raw = dev.get(self._field) if dev else None
        if raw is None or self._divisor is None:
            return raw
        return raw / self._divisor
