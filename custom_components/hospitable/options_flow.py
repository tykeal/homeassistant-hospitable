# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Options flow for the Hospitable integration.

Extracted from ``config_flow`` so that module stays within the project's
file-size budget; the behaviour is unchanged. ``config_flow`` re-exports
``HospitableOptionsFlow`` so the documented import path still works.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult, OptionsFlow
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from custom_components.hospitable.const import (
    CONF_AWAITING_HOST_REPLY,
    CONF_GUEST_CONTACT_DETAILS,
    CONF_LOOKAHEAD_DAYS,
    CONF_LOOKBACK_DAYS,
    CONF_PROPERTY_INTERVAL,
    CONF_RESERVATION_INTERVAL,
    CONF_SELECTED_PROPERTIES,
    CONF_TASK_INTERVAL,
    CONF_TASK_WINDOW_DAYS,
    CONF_TIMEZONE_OVERRIDES,
    DEFAULT_AWAITING_HOST_REPLY,
    DEFAULT_GUEST_CONTACT_DETAILS,
    DEFAULT_PROPERTY_INTERVAL,
    DEFAULT_RESERVATION_INTERVAL,
    DEFAULT_TASK_INTERVAL,
    DEFAULT_TASK_WINDOW_DAYS,
)
from custom_components.hospitable.options_bounds import _validate_bounds
from custom_components.hospitable.services.estimator import estimate_requests_per_day
from custom_components.hospitable.services.timezones import resolve_timezone
from custom_components.hospitable.services.window import (
    LOOKAHEAD_DEFAULT,
    LOOKBACK_DEFAULT,
)

TZ_FIELD_PREFIX = "timezone_override_"

DEFAULT_OPTIONS: dict[str, Any] = {
    CONF_SELECTED_PROPERTIES: [],
    # OFF by requirement (FR-038b), not by preference.
    CONF_GUEST_CONTACT_DETAILS: DEFAULT_GUEST_CONTACT_DETAILS,
    # Also OFF by requirement (FR-038a). This one additionally costs one
    # request per property per reservation poll cycle, so opting in is a
    # decision the user has to make deliberately.
    CONF_AWAITING_HOST_REPLY: DEFAULT_AWAITING_HOST_REPLY,
    CONF_RESERVATION_INTERVAL: DEFAULT_RESERVATION_INTERVAL,
    CONF_PROPERTY_INTERVAL: DEFAULT_PROPERTY_INTERVAL,
    CONF_LOOKBACK_DAYS: LOOKBACK_DEFAULT,
    CONF_LOOKAHEAD_DAYS: LOOKAHEAD_DEFAULT,
    CONF_TASK_INTERVAL: DEFAULT_TASK_INTERVAL,
    CONF_TASK_WINDOW_DAYS: DEFAULT_TASK_WINDOW_DAYS,
    CONF_TIMEZONE_OVERRIDES: {},
}


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
                CONF_TASK_INTERVAL,
                CONF_TASK_WINDOW_DAYS,
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
                        CONF_TASK_INTERVAL: user_input[CONF_TASK_INTERVAL],
                        CONF_TASK_WINDOW_DAYS: user_input[CONF_TASK_WINDOW_DAYS],
                        CONF_TIMEZONE_OVERRIDES: resolved_overrides,
                        CONF_GUEST_CONTACT_DETAILS: bool(
                            user_input.get(
                                CONF_GUEST_CONTACT_DETAILS,
                                DEFAULT_GUEST_CONTACT_DETAILS,
                            )
                        ),
                        CONF_AWAITING_HOST_REPLY: bool(
                            user_input.get(
                                CONF_AWAITING_HOST_REPLY,
                                DEFAULT_AWAITING_HOST_REPLY,
                            )
                        ),
                    },
                )

        estimate = estimate_requests_per_day(
            len(selection),
            _safe_interval(options[CONF_PROPERTY_INTERVAL], DEFAULT_PROPERTY_INTERVAL),
            _safe_interval(
                options[CONF_RESERVATION_INTERVAL], DEFAULT_RESERVATION_INTERVAL
            ),
            self._last_reservation_count(),
            _safe_interval(options[CONF_TASK_INTERVAL], DEFAULT_TASK_INTERVAL),
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
            vol.Optional(
                CONF_TASK_INTERVAL, default=options[CONF_TASK_INTERVAL]
            ): vol.Coerce(int),
            vol.Optional(
                CONF_TASK_WINDOW_DAYS, default=options[CONF_TASK_WINDOW_DAYS]
            ): vol.Coerce(int),
            vol.Optional(
                CONF_GUEST_CONTACT_DETAILS,
                default=bool(
                    options.get(
                        CONF_GUEST_CONTACT_DETAILS, DEFAULT_GUEST_CONTACT_DETAILS
                    )
                ),
            ): bool,
            vol.Optional(
                CONF_AWAITING_HOST_REPLY,
                default=bool(
                    options.get(CONF_AWAITING_HOST_REPLY, DEFAULT_AWAITING_HOST_REPLY)
                ),
            ): bool,
        }
        for property_id in selection:
            fields[
                vol.Optional(
                    f"{TZ_FIELD_PREFIX}{property_id}",
                    default=overrides.get(property_id, ""),
                )
            ] = str
        return vol.Schema(fields)
