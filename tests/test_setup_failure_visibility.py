# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T129 red phase: a config entry never fails setup silently."""

from __future__ import annotations

from typing import Any

import httpx
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


async def test_setup_401_surfaces_auth_failure(hass: Any, respx_router: Any) -> None:
    """A 401 during first refresh must not load the entry silently."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = _entry()
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(
        return_value=httpx.Response(401, json=load_fixture("error_401.json"))
    )
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(401, json=load_fixture("error_401.json"))
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is not ConfigEntryState.LOADED
    reauth = [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["handler"] == DOMAIN and flow["context"].get("source") == SOURCE_REAUTH
    ]
    assert entry.state is ConfigEntryState.SETUP_ERROR or reauth


async def test_setup_server_error_surfaces_not_ready(
    hass: Any, respx_router: Any
) -> None:
    """A 5xx during first refresh must not load the entry silently."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = _entry()
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(
        return_value=httpx.Response(500, json=load_fixture("error_500.json"))
    )
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(500, json=load_fixture("error_500.json"))
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
