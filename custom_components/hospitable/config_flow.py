# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Config and options flow placeholders for Hospitable."""

from __future__ import annotations

from typing import Any, ClassVar

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_LOOKAHEAD_DAYS,
    CONF_LOOKBACK_DAYS,
    CONF_PROPERTY_INTERVAL,
    CONF_RESERVATION_INTERVAL,
    CONF_SELECTED_PROPERTIES,
    CONF_TIMEZONE_OVERRIDES,
    CONF_TOKEN,
)

DEFAULT_OPTIONS: dict[str, Any] = {
    CONF_SELECTED_PROPERTIES: [],
    CONF_RESERVATION_INTERVAL: 5,
    CONF_PROPERTY_INTERVAL: 60,
    CONF_LOOKBACK_DAYS: 90,
    CONF_LOOKAHEAD_DAYS: 90,
    CONF_TIMEZONE_OVERRIDES: {},
}


class HospitableConfigFlow(ConfigFlow, domain="hospitable"):
    """Minimal config-flow surface for US1 tests and HA discovery."""

    supported_steps: ClassVar[set[str]] = {"user", "properties", "reauth_confirm"}
    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize transient flow state."""
        self._token = ""

    @staticmethod
    def async_get_options_flow(config_entry: object) -> HospitableOptionsFlow:
        """Return an options flow handler."""
        return HospitableOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect a token and advance to property selection."""
        if user_input is not None:
            self._token = str(user_input.get(CONF_TOKEN, ""))
            return await self.async_step_properties()
        return self.async_show_form(step_id="user", errors={})

    async def async_step_properties(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect selected properties and create the config entry."""
        if user_input is not None:
            selected = list(user_input.get(CONF_SELECTED_PROPERTIES, []))
            if not selected:
                return self.async_show_form(
                    step_id="properties", errors={"base": "no_properties_selected"}
                )
            return self.async_create_entry(
                title="Hospitable",
                data={CONF_TOKEN: self._token, CONF_ACCOUNT_NAMESPACE: "pending"},
                options={**DEFAULT_OPTIONS, CONF_SELECTED_PROPERTIES: selected},
            )
        return self.async_show_form(step_id="properties", errors={})


class HospitableOptionsFlow(OptionsFlow):
    """Minimal options-flow holder for Hospitable entries."""

    def __init__(self, config_entry: object) -> None:
        """Store the config entry for later options handling."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options form until full options validation runs."""
        return self.async_show_form(step_id="init", errors={})
