# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Config and options flows for the Hospitable integration."""

from __future__ import annotations

import logging
from typing import Any, TypeGuard

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
    DEFAULT_PROPERTY_INTERVAL,
    DEFAULT_RESERVATION_INTERVAL,
    DOMAIN,
    MIN_PROPERTY_INTERVAL,
    MIN_RESERVATION_INTERVAL,
)
from custom_components.hospitable.services.estimator import (
    estimate_requests_per_day,
)
from custom_components.hospitable.services.timezones import resolve_timezone
from custom_components.hospitable.services.window import (
    LOOKAHEAD_DEFAULT,
    LOOKBACK_DEFAULT,
)

_LOGGER = logging.getLogger(__name__)

TZ_FIELD_PREFIX = "timezone_override_"
LOOKBACK_MIN = 7
LOOKBACK_MAX = 365
LOOKAHEAD_MIN = 1
LOOKAHEAD_MAX = 730

DEFAULT_OPTIONS: dict[str, Any] = {
    CONF_SELECTED_PROPERTIES: [],
    CONF_RESERVATION_INTERVAL: DEFAULT_RESERVATION_INTERVAL,
    CONF_PROPERTY_INTERVAL: DEFAULT_PROPERTY_INTERVAL,
    CONF_LOOKBACK_DAYS: LOOKBACK_DEFAULT,
    CONF_LOOKAHEAD_DAYS: LOOKAHEAD_DEFAULT,
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


def _safe_interval(value: Any, fallback: int) -> int:
    """Return a positive integer interval, or the fallback for bad input."""
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int) and value >= 1:
        return value
    return fallback


class HospitableOptionsFlow(OptionsFlow):
    """Options flow for Hospitable config entries."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Store the config entry for later options handling."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and persist tuning options, showing a live estimate."""
        options: dict[str, Any] = {**DEFAULT_OPTIONS, **self._config_entry.options}
        available = self._available_properties()
        selection = list(options.get(CONF_SELECTED_PROPERTIES, []))
        saved_overrides = dict(options.get(CONF_TIMEZONE_OVERRIDES) or {})
        overrides = dict(saved_overrides)
        errors: dict[str, str] = {}

        if user_input is not None:
            selection = list(user_input.get(CONF_SELECTED_PROPERTIES, [])) or selection
            for field in (
                CONF_RESERVATION_INTERVAL,
                CONF_PROPERTY_INTERVAL,
                CONF_LOOKBACK_DAYS,
                CONF_LOOKAHEAD_DAYS,
            ):
                if field in user_input:
                    options[field] = user_input[field]
            for key, value in user_input.items():
                if key.startswith(TZ_FIELD_PREFIX):
                    overrides[key[len(TZ_FIELD_PREFIX) :]] = str(value)

            if not user_input.get(CONF_SELECTED_PROPERTIES):
                errors["base"] = "no_properties_selected"
            errors.update(_validate_bounds(user_input))
            tz_errors, resolved_overrides = await self._validate_timezones(
                user_input, saved_overrides
            )
            errors.update(tz_errors)

            if not errors:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_SELECTED_PROPERTIES: selection,
                        CONF_RESERVATION_INTERVAL: user_input[
                            CONF_RESERVATION_INTERVAL
                        ],
                        CONF_PROPERTY_INTERVAL: user_input[CONF_PROPERTY_INTERVAL],
                        CONF_LOOKBACK_DAYS: user_input[CONF_LOOKBACK_DAYS],
                        CONF_LOOKAHEAD_DAYS: user_input[CONF_LOOKAHEAD_DAYS],
                        CONF_TIMEZONE_OVERRIDES: resolved_overrides,
                    },
                )

        estimate = estimate_requests_per_day(
            len(selection),
            _safe_interval(options[CONF_PROPERTY_INTERVAL], DEFAULT_PROPERTY_INTERVAL),
            _safe_interval(
                options[CONF_RESERVATION_INTERVAL], DEFAULT_RESERVATION_INTERVAL
            ),
            self._last_reservation_count(),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=self._build_schema(available, options, selection, overrides),
            errors=errors,
            description_placeholders={"estimate": str(estimate)},
        )

    def _available_properties(self) -> dict[str, str]:
        """Return selectable properties keyed by id with a display name."""
        result: dict[str, str] = {}
        runtime = getattr(self._config_entry, "runtime_data", None)
        if isinstance(runtime, dict):
            coordinators = runtime.get("coordinators", {})
            coordinator = coordinators.get("properties")
            data = getattr(coordinator, "data", None) or {}
            for property_id, model in data.items():
                result[property_id] = str(getattr(model, "name", property_id))
        for property_id in self._config_entry.options.get(CONF_SELECTED_PROPERTIES, []):
            result.setdefault(property_id, property_id)
        return result

    def _last_reservation_count(self) -> int:
        """Return the most recently observed reservation count, or zero."""
        runtime = getattr(self._config_entry, "runtime_data", None)
        if isinstance(runtime, dict):
            coordinators = runtime.get("coordinators", {})
            coordinator = coordinators.get("reservations")
            data = getattr(coordinator, "data", None)
            if data is not None:
                return len(data)
        return 0

    async def _validate_timezones(
        self, user_input: dict[str, Any], existing: dict[str, str]
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Validate per-property IANA overrides at the options step.

        Merges the submitted overrides onto the previously saved ones so
        overrides for properties not shown in this submission (for
        example deselected properties) are retained. A blank submitted
        value clears that property's override.
        """
        errors: dict[str, str] = {}
        resolved: dict[str, str] = dict(existing)
        for key, value in user_input.items():
            if not key.startswith(TZ_FIELD_PREFIX):
                continue
            property_id = key[len(TZ_FIELD_PREFIX) :]
            text = str(value).strip()
            if not text:
                resolved.pop(property_id, None)
                continue
            try:
                await resolve_timezone(self.hass, text)
            except ValueError:
                errors[key] = "invalid_timezone"
                continue
            resolved[property_id] = text
        return errors, resolved

    def _build_schema(
        self,
        available: dict[str, str],
        options: dict[str, Any],
        selection: list[str],
        overrides: dict[str, str],
    ) -> vol.Schema:
        """Build the options schema with defaults and per-property overrides."""
        property_options = [
            SelectOptionDict(value=property_id, label=name)
            for property_id, name in sorted(
                available.items(), key=lambda pair: pair[1].casefold()
            )
        ]
        fields: dict[Any, Any] = {
            vol.Required(CONF_SELECTED_PROPERTIES, default=selection): SelectSelector(
                SelectSelectorConfig(
                    options=property_options,
                    mode=SelectSelectorMode.DROPDOWN,
                    multiple=True,
                )
            ),
            vol.Optional(
                CONF_RESERVATION_INTERVAL,
                default=options[CONF_RESERVATION_INTERVAL],
            ): vol.Coerce(int),
            vol.Optional(
                CONF_PROPERTY_INTERVAL, default=options[CONF_PROPERTY_INTERVAL]
            ): vol.Coerce(int),
            vol.Optional(
                CONF_LOOKBACK_DAYS, default=options[CONF_LOOKBACK_DAYS]
            ): vol.Coerce(int),
            vol.Optional(
                CONF_LOOKAHEAD_DAYS, default=options[CONF_LOOKAHEAD_DAYS]
            ): vol.Coerce(int),
        }
        for property_id in selection:
            fields[
                vol.Optional(
                    f"{TZ_FIELD_PREFIX}{property_id}",
                    default=overrides.get(property_id, ""),
                )
            ] = str
        return vol.Schema(fields)


def _validate_bounds(user_input: dict[str, Any]) -> dict[str, str]:
    """Return per-field errors naming the bound each value violated."""
    errors: dict[str, str] = {}
    reservation = user_input.get(CONF_RESERVATION_INTERVAL)
    if not _is_int(reservation) or reservation < MIN_RESERVATION_INTERVAL:
        errors[CONF_RESERVATION_INTERVAL] = "reservation_interval_min"
    property_interval = user_input.get(CONF_PROPERTY_INTERVAL)
    if not _is_int(property_interval) or property_interval < MIN_PROPERTY_INTERVAL:
        errors[CONF_PROPERTY_INTERVAL] = "property_interval_min"
    lookback = user_input.get(CONF_LOOKBACK_DAYS)
    if not _is_int(lookback) or not LOOKBACK_MIN <= lookback <= LOOKBACK_MAX:
        errors[CONF_LOOKBACK_DAYS] = "lookback_range"
    lookahead = user_input.get(CONF_LOOKAHEAD_DAYS)
    if not _is_int(lookahead) or not LOOKAHEAD_MIN <= lookahead <= LOOKAHEAD_MAX:
        errors[CONF_LOOKAHEAD_DAYS] = "lookahead_range"
    return errors


def _is_int(value: Any) -> TypeGuard[int]:
    """Return whether a value is a real integer, excluding booleans."""
    return isinstance(value, int) and not isinstance(value, bool)
