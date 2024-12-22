import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN, CONF_IP, CONF_TOKEN

class SinumThermostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="SINUM Thermostat", data=user_input)
        
        schema = vol.Schema({
            vol.Required(CONF_IP): str,
            vol.Required(CONF_TOKEN): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema)
    


    import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, CONF_IP, CONF_TOKEN

class SinumThermostatConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SINUM Thermostat integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step where user provides IP and token."""
        errors = {}

        if user_input is not None:
            # Validate the input (optional validation logic)
            if not self._is_valid_ip(user_input[CONF_IP]):
                errors["base"] = "invalid_ip"
            else:
                return self.async_create_entry(
                    title="SINUM Thermostat",
                    data=user_input
                )

        # Configuration schema
        schema = vol.Schema({
            vol.Required(CONF_IP): str,
            vol.Required(CONF_TOKEN): str,
            vol.Optional("update_interval", default=60): vol.All(
                vol.Coerce(int), vol.Range(min=10, max=3600)
            ),  # Seconds, between 10 and 3600
        })

        return self.async_show_form(
            step_id="user", 
            data_schema=schema, 
            errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the options flow for this config entry."""
        return SinumThermostatOptionsFlowHandler(config_entry)

    def _is_valid_ip(self, ip):
        """Check if the provided IP address is valid."""
        import ipaddress
        try:
            ipaddress.ip_address(ip)
            return True
        except ValueError:
            return False

class SinumThermostatOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for the integration."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Handle the options configuration."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Options schema
        schema = vol.Schema({
            vol.Optional(
                "update_interval", 
                default=self.config_entry.options.get("update_interval", 60)
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600))
        })

        return self.async_show_form(step_id="init", data_schema=schema)