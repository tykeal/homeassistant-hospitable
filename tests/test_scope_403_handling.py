# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T124 red phase: a scope-403 is a capability limit, not an auth failure."""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest
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


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason=(
        "TDD red phase: T124 scope-403 is currently surfaced as UpdateFailed "
        "instead of a tolerated capability limitation"
    ),
)
async def test_scope_403_is_capability_limit(
    hass: Any, respx_router: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """A scope-403 yields no reauth, no repair issue, and one capability log."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = await _setup_loaded(hass, respx_router)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(403, json=load_fixture("error_403_scope.json"))
    )
    coordinator = entry.runtime_data["coordinators"]["reservations"]

    with caplog.at_level(logging.WARNING):
        await coordinator.async_refresh()
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    reauth = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["handler"] == DOMAIN and flow["context"].get("source") == SOURCE_REAUTH
    ]
    assert reauth == []

    issues = [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN
    ]
    assert issues == []

    capability_logs = [
        record
        for record in caplog.records
        if "capability" in record.getMessage().lower()
    ]
    assert len(capability_logs) == 1
    assert coordinator.last_update_success is True
