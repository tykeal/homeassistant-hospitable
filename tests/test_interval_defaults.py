# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T108 (FR-019, FR-020, FR-021): shipped cadence and window defaults.

The shipped defaults are five minutes for reservation polling, sixty
minutes for property (and calendar) polling, and a reservation window of
ninety days backward and ninety days forward. The options flow must
present those same defaults for an entry that has not overridden them.
"""

from __future__ import annotations

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


async def test_options_flow_presents_shipped_defaults(
    hass: Any, respx_router: Any
) -> None:
    """The options schema defaults are 5m reservations, 60m properties, 90/90."""
    from custom_components.hospitable.api.const import BASE_URL
    from custom_components.hospitable.coordinator import (
        HospitableCalendarCoordinator,
        HospitablePropertiesCoordinator,
        HospitableReservationsCoordinator,
    )
    from custom_components.hospitable.services.window import (
        LOOKAHEAD_DEFAULT,
        LOOKBACK_DEFAULT,
    )

    # The coordinator and window defaults back the shipped values.
    assert HospitableReservationsCoordinator.default_minutes == 5
    assert HospitablePropertiesCoordinator.default_minutes == 60
    assert HospitableCalendarCoordinator.default_minutes == 60
    assert LOOKBACK_DEFAULT == 90
    assert LOOKAHEAD_DEFAULT == 90

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: "acct-example-0001",
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
        },
        unique_id="acct-example-0001",
    )
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(side_effect=_properties_side_effect)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"]
    assert schema is not None

    filled = schema(
        {CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"]}
    )
    assert filled[CONF_RESERVATION_INTERVAL] == 5
    assert filled[CONF_PROPERTY_INTERVAL] == 60
    assert filled[CONF_LOOKBACK_DAYS] == 90
    assert filled[CONF_LOOKAHEAD_DAYS] == 90

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
