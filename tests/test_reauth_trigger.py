# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T123 red phase: HTTP 401 triggers reauth naming the account."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import CONF_TOKEN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from tests.helpers import load_fixture

_ACCOUNT = "acct-example-0001"


def _entry() -> MockConfigEntry:
    """Build a Hospitable config entry for the example account."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: _ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"]},
        unique_id=_ACCOUNT,
    )


def _reauth_flows(hass: Any) -> list[dict[str, Any]]:
    """Return in-progress reauth flows for the Hospitable domain."""
    return [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["handler"] == DOMAIN and flow["context"].get("source") == SOURCE_REAUTH
    ]


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason=(
        "TDD red phase: T123 401 does not yet raise ConfigEntryAuthFailed so no "
        "reauth flow is started"
    ),
)
async def test_401_triggers_reauth_naming_account(hass: Any, respx_router: Any) -> None:
    """A 401 during polling starts a reauth flow whose prompt names the account."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = _entry()
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(200, json=load_fixture("properties_page1.json")),
            httpx.Response(200, json=load_fixture("properties_page2.json")),
        ]
    )
    reservations = respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    reservations.mock(
        return_value=httpx.Response(401, json=load_fixture("error_401.json"))
    )
    coordinator = entry.runtime_data["coordinators"]["reservations"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    flows = _reauth_flows(hass)
    assert len(flows) == 1

    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"])
    assert result["type"] == "form"
    placeholders = result.get("description_placeholders") or {}
    assert placeholders.get("account") == _ACCOUNT
