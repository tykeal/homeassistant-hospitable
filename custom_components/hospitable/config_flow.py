# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Config and options flows for the Hospitable integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.httpx_client import get_async_client
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from custom_components.hospitable.api.auth import StaticTokenProvider
from custom_components.hospitable.api.client import HospitableApiClient
from custom_components.hospitable.api.exceptions import (
    HospitableAuthError,
    HospitableConnectionError,
    HospitableForbiddenError,
    HospitableNotFoundError,
    HospitableResponseError,
    HospitableScopeError,
)
from custom_components.hospitable.api.models import HospitableProperty
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_LOOKAHEAD_DAYS,
    CONF_LOOKBACK_DAYS,
    CONF_NAMESPACE_SOURCE,
    CONF_PROPERTY_INTERVAL,
    CONF_RESERVATION_INTERVAL,
    CONF_SELECTED_PROPERTIES,
    CONF_TIMEZONE_OVERRIDES,
    CONF_TOKEN,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_OPTIONS: dict[str, Any] = {
    CONF_SELECTED_PROPERTIES: [],
    CONF_RESERVATION_INTERVAL: 5,
    CONF_PROPERTY_INTERVAL: 60,
    CONF_LOOKBACK_DAYS: 90,
    CONF_LOOKAHEAD_DAYS: 90,
    CONF_TIMEZONE_OVERRIDES: {},
}

USER_SCHEMA = vol.Schema({vol.Required(CONF_TOKEN): str})


def _client(hass: Any, token: str) -> HospitableApiClient:
    """Build an API client for config-flow validation."""
    return HospitableApiClient(StaticTokenProvider(token), get_async_client(hass))


def _error_key(exc: Exception) -> str:
    """Map API exceptions to config-flow error keys."""
    if isinstance(exc, HospitableAuthError):
        return "invalid_auth"
    if isinstance(exc, HospitableScopeError):
        return "scope_limited"
    if isinstance(exc, HospitableConnectionError):
        return "cannot_connect"
    if isinstance(
        exc,
        HospitableForbiddenError | HospitableNotFoundError | HospitableResponseError,
    ):
        return "cannot_connect"
    return "unknown"


class HospitableConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle Hospitable config, reauth, and property selection flows."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize transient flow state."""
        self._token = ""
        self._account_id = ""
        self._properties: dict[str, HospitableProperty] = {}
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HospitableOptionsFlow:
        """Return the options flow handler for a config entry."""
        return HospitableOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate a token, fetch properties, and advance to selection."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

        token = str(user_input[CONF_TOKEN])
        api = _client(self.hass, token)
        try:
            account = await api.get_user()
            await self.async_set_unique_id(account.account_id)
            self._abort_if_unique_id_configured()
            properties = await api.get_properties()
        except AbortFlow:
            raise
        except Exception as exc:
            if isinstance(exc, HospitableScopeError):
                _LOGGER.warning("Hospitable token lacks a required capability")
            elif not isinstance(exc, HospitableAuthError | HospitableConnectionError):
                _LOGGER.exception("Unexpected Hospitable config-flow error")
            return self.async_show_form(
                step_id="user",
                data_schema=USER_SCHEMA,
                errors={"base": _error_key(exc)},
            )

        if not properties:
            return self.async_abort(reason="no_properties")
        self._token = token
        self._account_id = account.account_id
        self._properties = properties
        return await self.async_step_properties()

    async def async_step_properties(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the entry after the user selects at least one property."""
        if user_input is not None:
            selected = list(user_input.get(CONF_SELECTED_PROPERTIES, []))
            if not selected:
                return self.async_show_form(
                    step_id="properties",
                    data_schema=self._properties_schema(),
                    errors={"base": "no_properties_selected"},
                )
            return self.async_create_entry(
                title="Hospitable",
                data={
                    CONF_TOKEN: self._token,
                    CONF_ACCOUNT_NAMESPACE: self._account_id,
                    CONF_NAMESPACE_SOURCE: "account",
                },
                options={**DEFAULT_OPTIONS, CONF_SELECTED_PROPERTIES: selected},
            )
        return self.async_show_form(
            step_id="properties", data_schema=self._properties_schema(), errors={}
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication for an existing config entry."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self._account_id = str(
            entry_data.get(CONF_ACCOUNT_NAMESPACE)
            or getattr(self._reauth_entry, "unique_id", "")
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate a replacement token for the same account."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm", data_schema=USER_SCHEMA, errors={}
            )
        token = str(user_input[CONF_TOKEN])
        try:
            account = await _client(self.hass, token).get_user()
        except Exception as exc:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=USER_SCHEMA,
                errors={"base": _error_key(exc)},
            )
        if account.account_id != self._account_id:
            return self.async_abort(reason="wrong_account")
        if self._reauth_entry is not None:
            self.hass.config_entries.async_update_entry(
                self._reauth_entry,
                data={**self._reauth_entry.data, CONF_TOKEN: token},
            )
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
        return self.async_abort(reason="reauth_successful")

    def _properties_schema(self) -> vol.Schema:
        """Build the property multi-select schema from fetched properties."""
        options: list[SelectOptionDict] = [
            SelectOptionDict(value=property_id, label=item.name)
            for property_id, item in sorted(
                self._properties.items(), key=lambda pair: pair[1].name.casefold()
            )
        ]
        return vol.Schema(
            {
                vol.Required(CONF_SELECTED_PROPERTIES): SelectSelector(
                    SelectSelectorConfig(
                        options=options, mode=SelectSelectorMode.DROPDOWN, multiple=True
                    )
                )
            }
        )


class HospitableOptionsFlow(OptionsFlow):
    """Options flow for Hospitable config entries."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Store the config entry for later options handling."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options form until full options validation runs."""
        return self.async_show_form(step_id="init", errors={})
