# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T105 (FR-072): the options screen shows a labelled request estimate.

The options step displays the estimated number of upstream requests per
day implied by the currently entered intervals, window, and property
selection; the estimate is clearly labelled as an estimate; and it
recomputes when the user changes an interval or the selection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_LOOKAHEAD_DAYS,
    CONF_LOOKBACK_DAYS,
    CONF_NAMESPACE_SOURCE,
    CONF_PROPERTY_INTERVAL,
    CONF_RESERVATION_INTERVAL,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from tests.helpers import load_fixture

TZ_FIELD_PREFIX = "timezone_override_"


def _properties_side_effect(request: httpx.Request) -> httpx.Response:
    """Return the paginated properties fixture for the requested page."""
    page = request.url.params.get("page", "1")
    fixture = "properties_page2.json" if page == "2" else "properties_page1.json"
    return httpx.Response(200, json=load_fixture(fixture))


def _entry() -> MockConfigEntry:
    """Build a config entry selecting both example properties."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: "acct-example-0001",
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
            CONF_RESERVATION_INTERVAL: 5,
            CONF_PROPERTY_INTERVAL: 60,
            CONF_LOOKBACK_DAYS: 90,
            CONF_LOOKAHEAD_DAYS: 90,
        },
        unique_id="acct-example-0001",
    )


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T112 estimate not rendered on options screen",
)
async def test_options_screen_shows_labelled_estimate(
    hass: Any, respx_router: Any
) -> None:
    """The estimate appears in the options form and is labelled an estimate."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = _entry()
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(side_effect=_properties_side_effect)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    result = await hass.config_entries.options.async_init(entry.entry_id)
    placeholders = result.get("description_placeholders") or {}
    assert "estimate" in placeholders
    initial = int(placeholders["estimate"])
    assert initial > 0

    # The description template must LABEL the number as an estimate.
    strings = json.loads(
        Path("custom_components/hospitable/strings.json").read_text(encoding="utf-8")
    )
    description = strings["options"]["step"]["init"]["description"]
    assert "{estimate}" in description
    assert "estimate" in description.lower()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T112 estimate does not recompute on change",
)
async def test_estimate_recomputes_on_interval_change(
    hass: Any, respx_router: Any
) -> None:
    """A longer property interval lowers the displayed estimate on re-render."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = _entry()
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(side_effect=_properties_side_effect)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    initial_placeholders = result.get("description_placeholders") or {}
    assert "estimate" in initial_placeholders
    initial = int(initial_placeholders["estimate"])

    # An invalid timezone forces a re-render while the interval is valid.
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
            CONF_RESERVATION_INTERVAL: 5,
            CONF_PROPERTY_INTERVAL: 120,
            CONF_LOOKBACK_DAYS: 90,
            CONF_LOOKAHEAD_DAYS: 90,
            f"{TZ_FIELD_PREFIX}prop-example-001": "-0700",
        },
    )
    assert result["type"] == "form"
    recomputed = int((result.get("description_placeholders") or {})["estimate"])
    assert recomputed < initial

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
