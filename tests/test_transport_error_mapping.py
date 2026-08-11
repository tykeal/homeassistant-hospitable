# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T136 red phase: transport and non-JSON failures become typed errors.

Surfaced by US5 isolation testing: a raw ``httpx.ConnectError`` and a
non-JSON success body both escape ``HospitableApiClient`` unmapped, so a
DNS/TLS/timeout failure never reaches the error-to-outcome mapping and a
user sees a raw exception repr instead of an actionable message (FR-064,
FR-065).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from homeassistant.config_entries import ConfigEntryState
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


async def test_transport_error_maps_to_connection_error(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """A transport failure becomes a typed ``HospitableConnectionError``."""
    from custom_components.hospitable.api.const import BASE_URL, USER_PATH
    from custom_components.hospitable.api.exceptions import (
        HospitableConnectionError,
    )

    client = api_client_factory(mock_httpx_client, synthetic_token)
    boom = httpx.ConnectError("name resolution failed")
    respx_router.get(f"{BASE_URL}{USER_PATH}").mock(side_effect=boom)

    with pytest.raises(HospitableConnectionError) as exc_info:
        await client.get_user()

    assert exc_info.value.endpoint == USER_PATH
    assert exc_info.value.__cause__ is boom


async def test_non_json_success_maps_to_response_error(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """A 200 with a non-JSON body becomes a typed response error."""
    from custom_components.hospitable.api.const import BASE_URL, USER_PATH
    from custom_components.hospitable.api.exceptions import (
        HospitableResponseError,
    )

    client = api_client_factory(mock_httpx_client, synthetic_token)
    respx_router.get(f"{BASE_URL}{USER_PATH}").mock(
        return_value=httpx.Response(200, text="<html>not json</html>")
    )

    with pytest.raises(HospitableResponseError) as exc_info:
        await client.get_user()

    assert exc_info.value.endpoint == USER_PATH
    assert exc_info.value.__cause__ is not None


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


async def test_connection_failure_message_states_cause_and_action(
    hass: Any, respx_router: Any
) -> None:
    """A connection failure surfaces an actionable message, not a repr."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = await _setup_loaded(hass, respx_router)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        side_effect=httpx.ConnectError("name resolution failed")
    )
    coordinator = entry.runtime_data["coordinators"]["reservations"]

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success is False
    message = str(coordinator.last_exception)
    assert "Hospitable" in message
    assert "name resolution failed" not in message
    assert "ConnectError" not in message
    lowered = message.casefold()
    assert any(cue in lowered for cue in ("check", "verify", "ensure", "retr"))
