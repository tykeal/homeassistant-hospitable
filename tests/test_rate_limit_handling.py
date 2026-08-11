# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T137 red phase: 429 self-resolves and repair issues clear on recovery.

Found by contract-versus-implementation review. The status-to-outcome
table characterises 429 as ``Backoff; normal polling resumes`` (SC-007),
yet the blanket persistence check escalated every repeated error - 429
included - to an ERROR repair issue. A repair issue must also not outlive
the condition that raised it (FR-065).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from homeassistant.config_entries import ConfigEntryState
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


def _domain_issues(hass: Any) -> list[Any]:
    """Return the repair issues currently raised for the integration."""
    return [
        issue
        for (domain, _), issue in ir.async_get(hass).issues.items()
        if domain == DOMAIN
    ]


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase T137: 429 wrongly escalates to a repair issue",
)
async def test_repeated_rate_limit_raises_no_repair_issue(
    hass: Any, respx_router: Any
) -> None:
    """A throttled account never surfaces a persistent-failure alarm."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = await _setup_loaded(hass, respx_router)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(429, json={"message": "Too Many Requests"})
    )
    coordinator = entry.runtime_data["coordinators"]["reservations"]

    for _ in range(3):
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False
    assert _domain_issues(hass) == []


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase T137: repair issue outlives the failing condition",
)
async def test_persistent_repair_issue_clears_on_recovery(
    hass: Any, respx_router: Any
) -> None:
    """A repair issue is removed once a later poll succeeds."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = await _setup_loaded(hass, respx_router)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(500, json=load_fixture("error_500.json"))
    )
    coordinator = entry.runtime_data["coordinators"]["reservations"]

    for _ in range(3):
        await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert len(_domain_issues(hass)) == 1

    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is True
    assert _domain_issues(hass) == []
