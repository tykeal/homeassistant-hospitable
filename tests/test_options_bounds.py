# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T104 (FR-016, FR-022, FR-064): options bounds name the permitted bound.

Every option is validated at the options step against its documented
bound, and an out-of-range value is rejected with a message that NAMES
the bound and states the remedy — never a bare validation code. The
per-property IANA timezone override is validated at the same step,
closing the deferred US3/T094 obligation.
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

TZ_FIELD_PREFIX = "timezone_override_"


def _translations_errors() -> dict[str, str]:
    """Return the options-flow error strings from translations/en.json."""
    path = Path("custom_components/hospitable/translations/en.json").resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data["options"]["error"])


def _entry() -> MockConfigEntry:
    """Build a config entry with a single selected property."""
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
    """Return a set of otherwise-valid options-flow inputs."""
    return {
        CONF_SELECTED_PROPERTIES: ["prop-example-001"],
        CONF_RESERVATION_INTERVAL: 5,
        CONF_PROPERTY_INTERVAL: 60,
        CONF_LOOKBACK_DAYS: 90,
        CONF_LOOKAHEAD_DAYS: 90,
    }


@pytest.mark.parametrize(
    ("field", "value", "error_key", "bound_phrase"),
    [
        (CONF_RESERVATION_INTERVAL, 0, "reservation_interval_min", "1 minute"),
        (CONF_PROPERTY_INTERVAL, 5, "property_interval_min", "15 minutes"),
        (CONF_LOOKBACK_DAYS, 3, "lookback_range", "7 and 365"),
        (CONF_LOOKBACK_DAYS, 400, "lookback_range", "7 and 365"),
        (CONF_LOOKAHEAD_DAYS, 0, "lookahead_range", "1 and 730"),
        (CONF_LOOKAHEAD_DAYS, 900, "lookahead_range", "1 and 730"),
    ],
)
async def test_out_of_range_option_names_bound(
    hass: Any,
    field: str,
    value: int,
    error_key: str,
    bound_phrase: str,
) -> None:
    """An out-of-range option is rejected with a message naming the bound."""
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    user_input = _base_input()
    user_input[field] = value
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] == "form"
    assert result["errors"].get(field) == error_key

    messages = _translations_errors()
    assert error_key in messages
    message = messages[error_key]
    # The message must NAME the bound and must not be a bare code.
    assert message != error_key
    assert bound_phrase in message
    assert message.rstrip().endswith((".", "!"))


async def test_invalid_timezone_override_rejected_at_options_step(
    hass: Any,
) -> None:
    """A non-IANA per-property override is rejected at the options step."""
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    user_input = _base_input()
    user_input[f"{TZ_FIELD_PREFIX}prop-example-001"] = "-0700"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] == "form"
    error_values = set(result["errors"].values())
    assert "invalid_timezone" in error_values

    messages = _translations_errors()
    assert "invalid_timezone" in messages
    assert "IANA" in messages["invalid_timezone"]


async def test_valid_options_saved(hass: Any) -> None:
    """In-bounds values with a valid override are accepted and saved."""
    entry = _entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    user_input = _base_input()
    user_input[CONF_RESERVATION_INTERVAL] = 3
    user_input[CONF_LOOKBACK_DAYS] = 30
    user_input[f"{TZ_FIELD_PREFIX}prop-example-001"] = "America/New_York"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )

    assert result["type"] == "create_entry"
    assert entry.options[CONF_RESERVATION_INTERVAL] == 3
    assert entry.options[CONF_LOOKBACK_DAYS] == 30
