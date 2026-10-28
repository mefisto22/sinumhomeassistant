from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "sinum"
CONF_IP = "ip"  # host vagy IP, opcionálisan porttal (pl. "sinum.local" vagy "192.168.1.5:8080")
CONF_TOKEN = "token"

# A lekérdezett eszközosztályok (/devices/<class>)
DEVICE_CLASSES = ("sbus", "wtp", "virtual")
# A fizikai modullal (/parent-devices/<class>) rendelkező osztályok
PARENT_CLASSES = ("sbus", "wtp")

UPDATE_INTERVAL = timedelta(seconds=2)

PLATFORMS = [
    Platform.SENSOR,
    Platform.SELECT,
    Platform.NUMBER,
    Platform.CLIMATE,
    Platform.SWITCH,
    Platform.COVER,
    Platform.LIGHT,
    Platform.BINARY_SENSOR,
]
