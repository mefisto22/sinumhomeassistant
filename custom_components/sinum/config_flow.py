"""Config flow: host + token, kapcsolat-ellenőrzéssel, reauth és reconfigure lépéssel."""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SinumAuthError, SinumClient, SinumConnectionError, SinumError, normalize_host
from .const import CONF_IP, CONF_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

TOKEN_SCHEMA = vol.Schema({vol.Required(CONF_TOKEN): str})


def _host_schema(host: str = "") -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_IP, default=host): str,
            vol.Required(CONF_TOKEN): str,
        }
    )


class SinumThermostatConfigFlow(ConfigFlow, domain=DOMAIN):
    """SINUM vezérlő felvétele."""

    VERSION = 1

    async def _async_validate(self, host: str, token: str) -> dict[str, str]:
        if not host or " " in host:
            return {CONF_IP: "invalid_host"}
        client = SinumClient(async_get_clientsession(self.hass), host, token)
        try:
            await client.async_check_connection()
        except SinumAuthError:
            return {"base": "invalid_auth"}
        except SinumConnectionError:
            return {"base": "cannot_connect"}
        except SinumError:
            return {"base": "invalid_response"}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error while validating SINUM controller")
            return {"base": "unknown"}
        return {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_IP])
            token = user_input[CONF_TOKEN].strip()
            if host:
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
            errors = await self._async_validate(host, token)
            if not errors:
                return self.async_create_entry(
                    title=f"SINUM {host}", data={CONF_IP: host, CONF_TOKEN: token}
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(_host_schema(), user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            errors = await self._async_validate(entry.data[CONF_IP], token)
            if not errors:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=TOKEN_SCHEMA,
            errors=errors,
            description_placeholders={"host": entry.data[CONF_IP]},
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = normalize_host(user_input[CONF_IP])
            token = user_input[CONF_TOKEN].strip()
            if any(
                e.unique_id == host and e.entry_id != entry.entry_id
                for e in self._async_current_entries(include_ignore=False)
            ):
                return self.async_abort(reason="already_configured")
            errors = await self._async_validate(host, token)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, unique_id=host, data_updates={CONF_IP: host, CONF_TOKEN: token}
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_host_schema(entry.data[CONF_IP]),
            errors=errors,
        )
