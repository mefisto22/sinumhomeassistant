from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, CoordinatorEntity
from .api import SinumAPI

async def async_setup_entry(hass, config_entry, async_add_entities):
    ip = config_entry.data["ip"]
    token = config_entry.data["token"]

    api = SinumAPI(ip, token)

    # Define update interval
    update_interval = timedelta(seconds=60)  # 60 másodperces frissítési időköz

    # Create a coordinator for fetching data
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="SINUM Thermostats",
        update_method=api.get_virtual_devices,
        update_interval=update_interval,
    )

    # Fetch initial data
    await coordinator.async_refresh()

    entities = []
    thermostat_count = 0

    for device in coordinator.data:
        if device.get("type") == "thermostat":
            thermostat_count += 1
            name = f"termosztat{thermostat_count}"
            entities.append(ThermostatSensor(coordinator, name, device))

    async_add_entities(entities)

class ThermostatSensor(CoordinatorEntity):
    def __init__(self, coordinator, name, device):
        super().__init__(coordinator)
        self._name = name
        self._device = device

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._device.get("temperature")