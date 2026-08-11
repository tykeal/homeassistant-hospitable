# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase availability state tests (T136, FR-058).

Each selected property gains exactly one availability sensor whose state
is ``available``, ``booked``, or ``unknown``. The literal ``unavailable``
is reserved by Home Assistant to mean the entity has no data and MUST
NEVER be used for a booked night — a sold night reads ``booked`` while
the entity remains in a real state, not ``unavailable``.

These are genuine end-to-end tests: a full config-entry setup drives the
real state machine with ``respx``-mocked endpoints, so an absent sensor
fails on a real assertion rather than an import error.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN, STATE_UNAVAILABLE
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from custom_components.hospitable.entity import build_unique_id
from tests.helpers import load_fixture

_ACCOUNT = "acct-example-0001"


def _calendar_payload(*, available: bool, reason: str) -> dict[str, Any]:
    """Build a one-day calendar payload dated today with a given status."""
    today = datetime.now(UTC).date().isoformat()
    return {
        "data": {
            "days": [
                {
                    "date": today,
                    "day": "MONDAY",
                    "min_stay": 2,
                    "note": None,
                    "closed_for_checkin": False,
                    "closed_for_checkout": False,
                    "status": {
                        "reason": reason,
                        "source": None,
                        "source_type": "PLATFORM" if available else "RESERVATION",
                        "available": available,
                    },
                    "price": {
                        "amount": 6000,
                        "currency": "USD",
                        "formatted": "$60.00",
                    },
                }
            ],
            "start_date": today,
            "end_date": today,
            "listing_id": "listing-cosmetic-0001",
            "provider": "airbnb-official",
        }
    }


def _entry(hass: Any) -> MockConfigEntry:
    """Register a two-property Hospitable entry."""
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
    return entry


def _mock_core_endpoints(respx_router: Any) -> None:
    """Mock the properties and reservations endpoints."""
    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(200, json=load_fixture("properties_page1.json")),
            httpx.Response(200, json=load_fixture("properties_page2.json")),
        ]
    )
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )


async def test_availability_states_available_and_booked(
    hass: Any, respx_router: Any
) -> None:
    """One property reads ``available``, the booked one reads ``booked``."""
    entry = _entry(hass)
    _mock_core_endpoints(respx_router)
    respx_router.get(f"{BASE_URL}/properties/prop-example-001/calendar").mock(
        return_value=httpx.Response(
            200, json=_calendar_payload(available=True, reason="AVAILABLE")
        )
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-002/calendar").mock(
        return_value=httpx.Response(
            200, json=_calendar_payload(available=False, reason="RESERVED")
        )
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    entity_registry = er.async_get(hass)
    availability_entries = [
        registry_entry
        for registry_entry in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        )
        if registry_entry.unique_id.endswith("availability")
    ]
    assert len(availability_entries) == 2

    available_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, build_unique_id(_ACCOUNT, "prop-example-001", "availability")
    )
    booked_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, build_unique_id(_ACCOUNT, "prop-example-002", "availability")
    )
    assert available_id is not None
    assert booked_id is not None

    available_state = hass.states.get(available_id)
    booked_state = hass.states.get(booked_id)
    assert available_state is not None
    assert booked_state is not None

    assert available_state.state == "available"
    # A booked night reads ``booked`` and is NOT the HA ``unavailable``
    # state, which would conflate a sold night with a broken integration.
    assert booked_state.state == "booked"
    assert booked_state.state != STATE_UNAVAILABLE

    for state in (available_state, booked_state):
        assert state.attributes["options"] == ["available", "booked", "unknown"]
        assert STATE_UNAVAILABLE not in state.attributes["options"]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_unrecognised_reason_maps_to_unknown_not_booked(
    hass: Any, respx_router: Any
) -> None:
    """An unavailable night with an unrecognised reason reads ``unknown``.

    ``available: false`` does not by itself mean a guest booked the night;
    a host can block it. Only ``reason == RESERVED`` may claim ``booked``.
    Any other reason maps to the honest ``unknown`` rather than asserting
    a booking that may not exist.
    """
    entry = _entry(hass)
    _mock_core_endpoints(respx_router)
    respx_router.get(f"{BASE_URL}/properties/prop-example-001/calendar").mock(
        return_value=httpx.Response(
            200, json=_calendar_payload(available=False, reason="HOST_BLOCKED")
        )
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-002/calendar").mock(
        return_value=httpx.Response(
            200, json=_calendar_payload(available=True, reason="AVAILABLE")
        )
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    entity_registry = er.async_get(hass)
    blocked_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, build_unique_id(_ACCOUNT, "prop-example-001", "availability")
    )
    assert blocked_id is not None
    blocked_state = hass.states.get(blocked_id)
    assert blocked_state is not None
    assert blocked_state.state == "unknown"
    assert blocked_state.state != "booked"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
