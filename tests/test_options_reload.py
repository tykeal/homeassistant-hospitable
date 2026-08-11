# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T103 (FR-017, SC-011): options changes reload the entry, no restart.

Drives the real options flow to change the reservation polling interval
and asserts the update listener reloads the entry so the change takes
effect immediately, without a Home Assistant restart. The rebuilt
reservations coordinator must pick up the new interval.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
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


def _properties_side_effect(request: httpx.Request) -> httpx.Response:
    """Return the paginated properties fixture for the requested page."""
    page = request.url.params.get("page", "1")
    fixture = "properties_page2.json" if page == "2" else "properties_page1.json"
    return httpx.Response(200, json=load_fixture(fixture))


def _entry() -> MockConfigEntry:
    """Build a loaded-style config entry with both example properties."""
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


async def test_options_change_reloads_without_restart(
    hass: Any, respx_router: Any
) -> None:
    """Changing the reservation interval reloads the entry immediately."""
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
    before = entry.runtime_data["coordinators"]["reservations"]
    assert before.update_interval == timedelta(minutes=5)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
            CONF_RESERVATION_INTERVAL: 2,
            CONF_PROPERTY_INTERVAL: 60,
            CONF_LOOKBACK_DAYS: 90,
            CONF_LOOKAHEAD_DAYS: 90,
        },
    )
    await hass.async_block_till_done()

    assert entry.options[CONF_RESERVATION_INTERVAL] == 2
    assert entry.state is ConfigEntryState.LOADED
    after = entry.runtime_data["coordinators"]["reservations"]
    assert after.update_interval == timedelta(minutes=2)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
