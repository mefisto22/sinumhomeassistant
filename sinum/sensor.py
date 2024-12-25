import logging
from datetime import timedelta
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.exceptions import ConfigEntryNotReady

from .api import SinumAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensor platform from config entry."""

    ip = config_entry.data["ip"]
    token = config_entry.data["token"]
    api = SinumAPI(ip, token)

    #----------------------------------------------------------------
    # 1) Thermostat coordinator (virtuális eszközök)
    #----------------------------------------------------------------
    thermostat_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="SINUM Thermostat Coordinator",
        update_method=api.get_virtual_devices,  # -> /devices/virtual
        update_interval=timedelta(seconds=2),
    )

    # Első frissítés (ha nem sikerül, ConfigEntryNotReady)
    try:
        await thermostat_coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning("Thermostat devices fetch failed: %s", err)
        raise ConfigEntryNotReady("Thermostat fetch error") from err

    devices_thermostat = thermostat_coordinator.data or []

    #----------------------------------------------------------------
    # 2) SBUS + WTP coordinator
    #----------------------------------------------------------------
    sbus_wtp_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="SINUM SbusWtp Coordinator",
        update_method=_fetch_sbus_wtp_sensors(api),
        update_interval=timedelta(seconds=2),
    )

    try:
        await sbus_wtp_coordinator.async_config_entry_first_refresh()
    except Exception as err:
        _LOGGER.warning("Sbus/WTP devices fetch failed: %s", err)
        raise ConfigEntryNotReady("Sbus/WTP fetch error") from err

    devices_sbus_wtp = sbus_wtp_coordinator.data or []
    _LOGGER.debug(f"SBUS/WTP devices: {devices_sbus_wtp}")
    #----------------------------------------------------------------
    # 3) Építjük az entitáslistát
    #----------------------------------------------------------------
    entities = []

    # 3/A) Thermostat-szenzorok
    thermostat_count = 0
    for device in devices_thermostat:
        if device.get("type") == "thermostat":
            thermostat_count += 1
            name_in_api = device.get("name", "")
            if not name_in_api:
                name_in_api = f"thermostat{thermostat_count}"

            base_name = name_in_api.lower().replace(" ", "_")

            # 4 szenzor: temp, humidity, mode, tempsetpoint
            entities.append(ThermostatTempSensor(thermostat_coordinator, device, base_name))
            entities.append(ThermostatHumiditySensor(thermostat_coordinator, device, base_name))
            entities.append(ThermostatModeSensor(thermostat_coordinator, device, base_name))
            entities.append(ThermostatTempSetpointSensor(thermostat_coordinator, device, base_name))

    # 3/B) SBUS/WTP-szenzorok (temperature_sensor, humidity_sensor, light_sensor)
    for dev in devices_sbus_wtp:
        dev_type = dev.get("type")
        name_in_api = dev.get("name", "unknown_sensor")
        base_name = name_in_api.lower().replace(" ", "_")

        if dev_type == "temperature_sensor":
            entities.append(SbusWtpTemperatureSensor(sbus_wtp_coordinator, dev, base_name))
        elif dev_type == "humidity_sensor":
            entities.append(SbusWtpHumiditySensor(sbus_wtp_coordinator, dev, base_name))
        elif dev_type == "light_sensor":
            entities.append(SbusWtpLightSensor(sbus_wtp_coordinator, dev, base_name))
        # Ha később bővülne, itt is folytathatod.

    # 3/C) Battery-szenzorok hozzáadása
    seen_addresses = set()
    for dev in devices_sbus_wtp:
        if "battery" not in dev:
            continue  # Csak azok a szenzorok, amelyeknek van battery mezőjük

        address = dev.get("address")
        if address is None:
            _LOGGER.warning(f"Device {dev.get('id')} missing 'address' field. Skipping battery sensor.")
            continue  # 'address' mező hiányzik

        if address in seen_addresses:
            _LOGGER.debug(f"Skipping device with duplicate address: {address}")
            continue  # Már létrehoztunk egy szenzort ehhez az address-hez

        seen_addresses.add(address)

        software_version = dev.get("software_version", "unknown_version")
        # Az entitás nevéhez használhatjuk a 'name' mezőt is, ha egyedi
        sensor_name = f"{software_version}_battery".lower().replace(" ", "_")

        entities.append(
            BatterySensor(sbus_wtp_coordinator, dev, sensor_name)
        )

    #----------------------------------------------------------------
    # 4) Regisztráljuk az entitásokat
    #----------------------------------------------------------------
    async_add_entities(entities, update_before_add=True)


def _fetch_sbus_wtp_sensors(api: SinumAPI):
    """
    Egy factory-függvény, ami visszaad egy aszinkron '_async_fetch_sbus_wtp'
    metódust, amit a DataUpdateCoordinator hív meg periodikusan.

    Ebben gyűjtjük a sbus és wtp eszközöket, és visszaadjuk a listát,
    amiben lehet "temperature_sensor", "humidity_sensor", "light_sensor", stb.
    """
    async def _async_fetch_sbus_wtp():
        sbus_list = await api.get_sbus_devices()
        wtp_list = await api.get_wtp_devices()
        _LOGGER.debug(f"SBUS devices: {sbus_list}")
        _LOGGER.debug(f"WTP devices: {wtp_list}")
        # Összefésüljük a két listát
        combined = sbus_list + wtp_list
        _LOGGER.debug(f"Combined device list: {combined}")
        return combined

    return _async_fetch_sbus_wtp


#----------------------------------------------------------------
#                          BASE CLASSES
#----------------------------------------------------------------

class ThermostatBase(CoordinatorEntity, SensorEntity):
    """Alap osztály a thermostat-szenzorokhoz (virtuális eszköz)."""

    def __init__(self, coordinator, device, base_name):
        super().__init__(coordinator)
        self._device = device
        self._device_id = device.get("id")
        self._base_name = base_name

    def _find_device_in_coordinator(self):
        data = self.coordinator.data
        if not data:
            return None
        for dev in data:
            if dev.get("id") == self._device_id:
                return dev
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Minden entitás a 'all_in_one' device-hoz tartozik."""
        return DeviceInfo(
            identifiers={(DOMAIN, "all_in_one")},
            name="SINUM All-in-One",
            manufacturer="SINUM",
            model="Thermostat Integration"
        )


class SbusWtpBase(CoordinatorEntity, SensorEntity):
    """
    Alap osztály az SBUS/WTP eszközök szenzoraihoz:
    - 'temperature_sensor', 'humidity_sensor', 'light_sensor', stb.
    """

    def __init__(self, coordinator, device, base_name):
        super().__init__(coordinator)
        self._device = device
        self._device_id = f"{device.get('class')}_{device.get('id')}"  # Egyedi azonosító: class_id
        self._base_name = base_name

    def _find_device_in_coordinator(self):
        data = self.coordinator.data
        if not data:
            return None
        for dev in data:
            unique_id = f"{dev.get('class')}_{dev.get('id')}"
            if unique_id == self._device_id:
                return dev
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Szintén a 'all_in_one' device-hoz soroljuk."""
        return DeviceInfo(
            identifiers={(DOMAIN, "all_in_one")},
            name="SINUM All-in-One",
            manufacturer="SINUM",
            model="SBUS/WTP Integration"
        )


#----------------------------------------------------------------
#                  THERMOSTAT SENSOR ENTITIES
#----------------------------------------------------------------

class ThermostatTempSensor(ThermostatBase):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"

    def __init__(self, coordinator, device, base_name):
        super().__init__(coordinator, device, base_name)
        self._attr_name = f"{base_name}_temp"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_temp"

    @property
    def native_value(self):
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        raw_temp = dev.get("temperature")
        if raw_temp is None:
            return None
        return raw_temp / 10.0


class ThermostatHumiditySensor(ThermostatBase):
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, device, base_name):
        super().__init__(coordinator, device, base_name)
        self._attr_name = f"{base_name}_humidity"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_humidity"

    @property
    def native_value(self):
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        raw_hum = dev.get("humidity")
        if raw_hum is None:
            return None
        return raw_hum / 10.0


class ThermostatModeSensor(ThermostatBase):
    """Üzemmód szenzor (off, heating, cooling)."""

    def __init__(self, coordinator, device, base_name):
        super().__init__(coordinator, device, base_name)
        self._attr_name = f"{base_name}_mode"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_mode"

    @property
    def native_value(self):
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        return dev.get("mode")


class ThermostatTempSetpointSensor(ThermostatBase):
    """Célhőmérséklet-szenzor."""
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"

    def __init__(self, coordinator, device, base_name):
        super().__init__(coordinator, device, base_name)
        self._attr_name = f"{base_name}_tempsetpoint"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_tempsetpoint"

    @property
    def native_value(self):
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        raw_target = dev.get("target_temperature")
        if raw_target is None:
            return None
        return raw_target / 10.0


#----------------------------------------------------------------
#                  SBUS/WTP SENSOR ENTITIES
#----------------------------------------------------------------

class SbusWtpTemperatureSensor(SbusWtpBase):
    """
    type == "temperature_sensor"
    A dev-ben várhatóan dev["temperature"] van, amit 10-zel osztunk,
    mértékegysége: °C
    """
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = "°C"

    def __init__(self, coordinator, device, base_name):
        super().__init__(coordinator, device, base_name)
        self._attr_name = f"{base_name}_temperature"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_temperature"

    @property
    def native_value(self):
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        raw_val = dev.get("temperature")
        if raw_val is None:
            return None
        return raw_val / 10.0


class SbusWtpHumiditySensor(SbusWtpBase):
    """
    type == "humidity_sensor"
    A dev-ben dev["humidity"], amit 10-zel osztunk,
    mértékegysége: %
    """
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, device, base_name):
        super().__init__(coordinator, device, base_name)
        self._attr_name = f"{base_name}_humidity"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_humidity_sbuswtp"

    @property
    def native_value(self):
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        raw_hum = dev.get("humidity")
        if raw_hum is None:
            return None
        return raw_hum / 10.0


class SbusWtpLightSensor(SbusWtpBase):
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = "lx"

    def __init__(self, coordinator, device, base_name):
        super().__init__(coordinator, device, base_name)
        self._attr_name = f"{base_name}_light"
        self._attr_unique_id = f"{DOMAIN}_{self._device_id}_light"

    @staticmethod
    def debug_device(dev):
        """Log the entire device object for debugging."""
        _LOGGER.debug(f"Light Sensor Device Data: {dev}")

    @property
    def native_value(self):
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        self.debug_device(dev)
        raw_lx = dev.get("illuminance")
        if raw_lx is None:
            return None
        return raw_lx


#----------------------------------------------------------------
#                  BATTERY SENSOR ENTITIES
#----------------------------------------------------------------

class BatterySensor(SbusWtpBase):
    """
    Battery sensor for SBUS/WTP devices.
    device_class = battery
    unit = %
    """

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = "%"

    def __init__(self, coordinator, device, base_name):
        super().__init__(coordinator, device, base_name)
        # Használjuk az 'address' és 'id' mezőket a unique_id biztosítására
        address = device.get("address", "unknown_address")
        device_id = device.get("id", "unknown_id")
        self._attr_name = f"{base_name}_battery"
        self._attr_unique_id = f"{DOMAIN}_battery_{address}_{device_id}"

    @property
    def native_value(self):
        dev = self._find_device_in_coordinator()
        if not dev:
            return None
        battery = dev.get("battery")
        if battery is None:
            return None
        return battery


#----------------------------------------------------------------
#                  ADDITIONAL SENSOR CLASSES IF NEEDED
#----------------------------------------------------------------

# Ha később bővülne, itt is folytathatod.