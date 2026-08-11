# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase whole-lifecycle read-only tests (T140, FR-059).

FR-059 forbids any calendar modification request absolutely. This is
proved structurally, over the full entry lifecycle: setup, a refresh of
every coordinator, an options change (which triggers the reload
listener), a reload, and an unload. After all of that the ``respx``
router must have recorded zero requests whose method is anything other
than ``GET`` — covering ``POST``/``PUT``/``PATCH``/``DELETE`` alike, not
merely the absence of a ``POST``.
"""

from __future__ import annotations

from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_LOOKAHEAD_DAYS,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from tests.helpers import load_fixture

_ACCOUNT = "acct-example-0001"


def _properties_side_effect(request: httpx.Request) -> httpx.Response:
    """Return the paginated properties fixture for the requested page."""
    page = request.url.params.get("page", "1")
    fixture = "properties_page2.json" if page == "2" else "properties_page1.json"
    return httpx.Response(200, json=load_fixture(fixture))


def _mock_all_endpoints(respx_router: Any) -> None:
    """Mock every GET endpoint reused across setup and reload."""
    respx_router.get(f"{BASE_URL}/properties").mock(side_effect=_properties_side_effect)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-001/calendar").mock(
        return_value=httpx.Response(200, json=load_fixture("calendar_prop1.json"))
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-002/calendar").mock(
        return_value=httpx.Response(200, json=load_fixture("calendar_prop2.json"))
    )


async def test_full_lifecycle_issues_only_get_requests(
    hass: Any, respx_router: Any
) -> None:
    """A full entry lifecycle records exclusively ``GET`` requests."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: _ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
            CONF_LOOKAHEAD_DAYS: 30,
        },
        unique_id=_ACCOUNT,
    )
    entry.add_to_hass(hass)
    _mock_all_endpoints(respx_router)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    # Every coordinator, calendar included, participates in the lifecycle.
    coordinators = entry.runtime_data["coordinators"]
    assert set(coordinators) == {"properties", "reservations", "calendar"}
    for coordinator in coordinators.values():
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    # An options change fires the reload listener added in US4.
    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
            CONF_LOOKAHEAD_DAYS: 45,
        },
    )
    await hass.async_block_till_done()

    # An explicit reload and unload complete the lifecycle.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert len(respx_router.calls) > 0
    for call in respx_router.calls:
        assert call.request.method == "GET", (
            f"Non-GET request recorded: {call.request.method} {call.request.url}"
        )
