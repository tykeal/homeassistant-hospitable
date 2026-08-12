# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for the US4 options (T121, T121a).

Two new options land with US4: the task polling cadence and the task
lookahead window. Both are validated at the options step against a
documented bound, using the SAME ``options_bounds`` module and named
error keys every other option uses.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_LOOKAHEAD_DAYS,
    CONF_LOOKBACK_DAYS,
    CONF_NAMESPACE_SOURCE,
    CONF_PROPERTY_INTERVAL,
    CONF_RESERVATION_INTERVAL,
    CONF_SELECTED_PROPERTIES,
    CONF_TOKEN,
    DOMAIN,
)

# Written as literals rather than imported constants on purpose: a
# module-level import of a not-yet-existing constant is an ImportError
# at collection time, which no xfail marker can rescue and which would
# pin the red phase on the wrong failure.
TASK_INTERVAL = "task_interval_minutes"
TASK_WINDOW_DAYS = "task_window_days"

# The upstream ceiling is hard: an end_date more than three years ahead
# returns HTTP 400. The option bound must sit comfortably below it.
UPSTREAM_CEILING_DAYS = 3 * 365


def _entry() -> MockConfigEntry:
    """Build a config entry with a single selected property.

    Returns:
        The unloaded config entry.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: "acct-example-0001",
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001"],
            CONF_RESERVATION_INTERVAL: 5,
            CONF_PROPERTY_INTERVAL: 60,
            CONF_LOOKBACK_DAYS: 90,
            CONF_LOOKAHEAD_DAYS: 90,
        },
        unique_id="acct-example-0001",
    )


def _base_input() -> dict[str, Any]:
    """Return a set of otherwise-valid options-flow inputs.

    Returns:
        Valid values for every pre-existing option.
    """
    return {
        CONF_SELECTED_PROPERTIES: ["prop-example-001"],
        CONF_RESERVATION_INTERVAL: 5,
        CONF_PROPERTY_INTERVAL: 60,
        CONF_LOOKBACK_DAYS: 90,
        CONF_LOOKAHEAD_DAYS: 90,
        TASK_INTERVAL: 15,
        TASK_WINDOW_DAYS: 14,
    }


def _translation_errors() -> dict[str, str]:
    """Return the options-flow error strings from ``translations/en.json``.

    Returns:
        The error key to message mapping.
    """
    path = Path("custom_components/hospitable/translations/en.json").resolve()
    return dict(json.loads(path.read_text(encoding="utf-8"))["options"]["error"])


def _schema_defaults(result: Any) -> dict[str, Any]:
    """Return the default value for every key in a form's schema.

    Args:
        result: The flow result carrying ``data_schema``.

    Returns:
        Mapping of option key to its schema default.
    """
    defaults: dict[str, Any] = {}
    for key in result["data_schema"].schema:
        default = getattr(key, "default", None)
        defaults[str(key)] = default() if callable(default) else default
    return defaults


def _require_new_fields(result: Any) -> None:
    """Assert both new fields are in the schema before submitting.

    Submitting a key the schema does not declare raises ``InvalidData``
    from voluptuous, which would pin the red phase on the wrong
    exception and prove nothing. Checking the schema first makes the
    red-phase failure an ``AssertionError`` about the missing field.

    Args:
        result: The flow result carrying ``data_schema``.
    """
    defaults = _schema_defaults(result)
    assert TASK_INTERVAL in defaults, f"no task interval field: {sorted(defaults)}"
    assert TASK_WINDOW_DAYS in defaults, f"no task window field: {sorted(defaults)}"


async def test_the_options_flow_offers_the_task_interval(hass: Any) -> None:
    """The task cadence is offered with a 15-minute default (T121, FR-034)."""
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    defaults = _schema_defaults(result)
    assert TASK_INTERVAL in defaults, f"no task interval field: {sorted(defaults)}"
    assert defaults[TASK_INTERVAL] == 15


async def test_a_below_floor_task_interval_names_its_bound(hass: Any) -> None:
    """A below-floor cadence is rejected by name (T121, FR-034)."""
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    _require_new_fields(result)
    user_input = _base_input()
    user_input[TASK_INTERVAL] = 1
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] == "form"
    error_key = result["errors"].get(TASK_INTERVAL)
    assert error_key == "task_interval_min", result["errors"]
    messages = _translation_errors()
    assert error_key in messages
    assert "5 minutes" in messages[error_key]
    assert messages[error_key].rstrip().endswith(".")


async def test_the_options_flow_offers_the_task_window(hass: Any) -> None:
    """The task window is offered with a 14-day default (T121a, FR-030).

    14 matches the upstream default measured on 2026-08-12, so turning
    explicit dates on does not change an existing user's task counts.
    """
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    defaults = _schema_defaults(result)
    assert TASK_WINDOW_DAYS in defaults, f"no task window field: {sorted(defaults)}"
    assert defaults[TASK_WINDOW_DAYS] == 14


@pytest.mark.parametrize("value", [0, -1, 5000])
async def test_an_out_of_range_task_window_names_its_bound(
    hass: Any, value: int
) -> None:
    """An out-of-range window is rejected by name (T121a, FR-030).

    The upper bound exists because ``end_date`` more than three years
    ahead is an upstream HTTP 400, so an unbounded option would produce
    a poll that can never succeed.
    """
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    _require_new_fields(result)
    user_input = _base_input()
    user_input[TASK_WINDOW_DAYS] = value
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] == "form"
    error_key = result["errors"].get(TASK_WINDOW_DAYS)
    assert error_key == "task_window_range", result["errors"]
    messages = _translation_errors()
    assert error_key in messages
    assert messages[error_key] != error_key
    assert messages[error_key].rstrip().endswith(".")


def test_the_task_window_bound_sits_below_the_upstream_ceiling() -> None:
    """The permitted maximum can never breach the 3-year ceiling (T121a).

    Asserting the bound directly is what makes this a real guarantee: an
    ``end_date`` of today plus the maximum must stay comfortably inside
    the window upstream will accept, otherwise the option would let a
    user configure a poll that always 400s.
    """
    from custom_components.hospitable import options_bounds

    maximum = getattr(options_bounds, "TASK_WINDOW_MAX", None)
    minimum = getattr(options_bounds, "TASK_WINDOW_MIN", None)
    assert maximum is not None, "options_bounds defines no TASK_WINDOW_MAX"
    assert minimum is not None, "options_bounds defines no TASK_WINDOW_MIN"
    assert minimum >= 1
    assert maximum < UPSTREAM_CEILING_DAYS, (
        f"a window of {maximum} days can breach the upstream 3-year ceiling"
    )


async def test_the_new_options_are_persisted(hass: Any) -> None:
    """In-bounds values for both new options are saved (T121, T121a)."""
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    _require_new_fields(result)
    user_input = _base_input()
    user_input[TASK_INTERVAL] = 30
    user_input[TASK_WINDOW_DAYS] = 60
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] == "create_entry", result
    assert entry.options[TASK_INTERVAL] == 30
    assert entry.options[TASK_WINDOW_DAYS] == 60
