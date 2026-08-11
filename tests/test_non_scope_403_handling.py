# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T125 red phase: a non-scope 403 raises a repair issue, never reauth."""

from __future__ import annotations

from typing import Any

import httpx
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from tests.helpers import load_fixture

_ACCOUNT = "acct-example-0001"


async def _setup_loaded(hass: Any, respx_router: Any) -> MockConfigEntry:
    """Set up a loaded Hospitable entry with two properties."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: _ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"]},
        unique_id=_ACCOUNT,
    )
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(200, json=load_fixture("properties_page1.json")),
            httpx.Response(200, json=load_fixture("properties_page2.json")),
        ]
    )
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_non_scope_403_raises_repair_issue(hass: Any, respx_router: Any) -> None:
    """A non-scope 403 creates a repair issue and starts no reauth flow."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = await _setup_loaded(hass, respx_router)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(403, json=load_fixture("error_403_other.json"))
    )
    coordinator = entry.runtime_data["coordinators"]["reservations"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    issues = [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN
    ]
    assert len(issues) == 1

    reauth = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["handler"] == DOMAIN and flow["context"].get("source") == SOURCE_REAUTH
    ]
    assert reauth == []
