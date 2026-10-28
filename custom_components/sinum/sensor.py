from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import LIGHT_LUX, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SinumConfigEntry, SinumCoordinator
from .entity import (
    HUMIDITY_RANGE,
    SinumEntity,
    async_add_device_entities,
    measurement,
    module_of,
)

# 'us' régióban a fényszenzor foot-candle-t ad; 1 fc = 10,764 lx
FOOT_CANDLE_PER_LUX = 0.09290304

THERMOSTAT_MODES = ["off", "heating", "cooling"]


# A frissítést a koordinátor végzi
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: SinumConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    temp_range = coordinator.temperature_range
    lux_divisor = FOOT_CANDLE_PER_LUX if coordinator.region == "us" else None
    # Akkumulátor: egy fizikai eszköz (address) több logikai eszközként jelenik meg,
    # ezért címenként csak egy szenzort hozunk létre (az első logikai eszközön).
    seen_addresses: set[Any] = set()

    def build(devices: list[dict[str, Any]]) -> list[SensorEntity]:
        entities: list[SensorEntity] = []
        for dev in devices:
            dev_type = dev.get("type")
            if dev["class"] == "virtual" and dev_type == "thermostat":
                # A szobai panel eszközén a panel saját érzékelői mellett külön névvel
                merged = module_of(coordinator, dev) is not None
                entities += [
                    # 0: nincs hozzárendelt érzékelő
                    SinumSensor(
                        coordinator, dev, "temp", "temperature", 10, TEMPERATURE,
                        valid_range=temp_range, zero_is_none=True,
                        translation_key="thermostat_temperature" if merged else None,
                    ),
                    SinumSensor(
                        coordinator, dev, "humidity", "humidity", 10, HUMIDITY,
                        valid_range=HUMIDITY_RANGE, zero_is_none=True,
                        translation_key="thermostat_humidity" if merged else None,
                    ),
                    # A klíma entitás ugyanezt mutatja, ezért alapból letiltva
                    SinumSensor(
                        coordinator, dev, "mode", "mode", None, MODE,
                        translation_key="mode", enabled_default=False,
                    ),
                    SinumSensor(
                        coordinator, dev, "tempsetpoint", "target_temperature", 10, TEMPERATURE,
                        translation_key="target_temperature", enabled_default=False,
                    ),
                ]
                continue
            if dev["class"] not in ("sbus", "wtp"):
                continue
            if dev_type == "temperature_sensor":
                entities.append(
                    SinumSensor(
                        coordinator, dev, "temperature", "temperature", 10, TEMPERATURE,
                        valid_range=temp_range, primary=True,
                    )
                )
            elif dev_type == "humidity_sensor":
                entities.append(
                    SinumSensor(
                        coordinator, dev, "humidity", "humidity", 10, HUMIDITY,
                        valid_range=HUMIDITY_RANGE, primary=True,
                    )
                )
            elif dev_type == "light_sensor":
                entities.append(
                    SinumSensor(
                        coordinator, dev, "illuminance", "illuminance", lux_divisor, ILLUMINANCE,
                        primary=True,
                    )
                )
            address = dev.get("address")
            if "battery" in dev and address is not None and address not in seen_addresses:
                seen_addresses.add(address)
                entities.append(SinumSensor(coordinator, dev, "battery", "battery", None, BATTERY))
        return entities

    async_add_device_entities(entry, async_add_entities, build)


# (device_class, unit, state_class); a hőmérséklet egysége a régiótól függ
TEMPERATURE = (SensorDeviceClass.TEMPERATURE, None, SensorStateClass.MEASUREMENT)
HUMIDITY = (SensorDeviceClass.HUMIDITY, PERCENTAGE, SensorStateClass.MEASUREMENT)
ILLUMINANCE = (SensorDeviceClass.ILLUMINANCE, LIGHT_LUX, SensorStateClass.MEASUREMENT)
BATTERY = (SensorDeviceClass.BATTERY, PERCENTAGE, SensorStateClass.MEASUREMENT)
MODE = (SensorDeviceClass.ENUM, None, None)


class SinumSensor(SinumEntity, SensorEntity):
    """Egy eszközmező értéke, opcionális osztóval (pl. tizedfok -> fok).

    Megadott érvényes tartománynál a 'nincs mérés' jelzésekből ismeretlen állapot lesz.
    """

    def __init__(
        self,
        coordinator: SinumCoordinator,
        device: dict[str, Any],
        key: str,
        field: str,
        divisor: float | None,
        kind: tuple[SensorDeviceClass, str | None, SensorStateClass | None],
        *,
        valid_range: tuple[int, int] | None = None,
        zero_is_none: bool = False,
        primary: bool = False,
        translation_key: str | None = None,
        enabled_default: bool = True,
    ) -> None:
        super().__init__(coordinator, device, key, primary=primary)
        self._field = field
        self._divisor = divisor
        self._valid_range = valid_range
        self._zero_is_none = zero_is_none
        device_class, unit, state_class = kind
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        if device_class is SensorDeviceClass.TEMPERATURE:
            unit = coordinator.temperature_unit
        elif device_class is SensorDeviceClass.ENUM:
            self._attr_options = THERMOSTAT_MODES
        elif device_class is SensorDeviceClass.ILLUMINANCE and divisor is not None:
            self._attr_suggested_display_precision = 0
        self._attr_native_unit_of_measurement = unit
        self._attr_translation_key = translation_key
        self._attr_entity_registry_enabled_default = enabled_default

    @property
    def native_value(self) -> Any:
        dev = self.device
        raw = dev.get(self._field) if dev else None
        if self._valid_range is not None or self._zero_is_none:
            return measurement(raw, self._divisor or 1, self._valid_range, zero_is_none=self._zero_is_none)
        if self.device_class is SensorDeviceClass.ENUM:
            return raw if raw in THERMOSTAT_MODES else None
        if raw is None or self._divisor is None:
            return raw
        return raw / self._divisor
