# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase per-property calendar degradation test (T163, FR-057).

research.md D-15 makes two promises for the calendar: a failed
property keeps its last-good day map, AND its availability sensor alone
degrades. Retention without degradation lets a property whose calendar
route has been failing for days report confident, arbitrarily stale
data with no signal that it is stale, which is worse for automation than
an honest ``unavailable``.

This is a genuine end-to-end test: a real config entry drives the state
machine while exactly one property's calendar URL fails repeatedly. The
sensor must retain its last-good state through the first two failures
(the FR-057 three-strike grace) and flip to Home Assistant's
``unavailable`` on the third, while a sibling property stays available
and the properties coordinator is untouched. Recovery must restore it.
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
_FAILING = "prop-example-002"
_SIBLING = "prop-example-001"


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
        options={CONF_SELECTED_PROPERTIES: [_SIBLING, _FAILING]},
        unique_id=_ACCOUNT,
    )
    entry.add_to_hass(hass)
    return entry


async def test_calendar_sensor_degrades_after_three_property_strikes(
    hass: Any, respx_router: Any
) -> None:
    """A property's sensor degrades on the third calendar strike."""
    entry = _entry(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(200, json=load_fixture("properties_page1.json")),
            httpx.Response(200, json=load_fixture("properties_page2.json")),
        ]
    )
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )
    # The sibling always succeeds. The failing property succeeds once at
    # setup, fails three consecutive times, then recovers.
    respx_router.get(f"{BASE_URL}/properties/{_SIBLING}/calendar").mock(
        return_value=httpx.Response(
            200, json=_calendar_payload(available=True, reason="AVAILABLE")
        )
    )
    booked_response = _calendar_payload_response(available=False, reason="RESERVED")
    failure = httpx.Response(500, json=load_fixture("error_500.json"))
    respx_router.get(f"{BASE_URL}/properties/{_FAILING}/calendar").mock(
        side_effect=[
            booked_response,
            failure,
            failure,
            failure,
            _calendar_payload_response(available=False, reason="RESERVED"),
        ]
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    entity_registry = er.async_get(hass)
    failing_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, build_unique_id(_ACCOUNT, _FAILING, "availability")
    )
    sibling_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, build_unique_id(_ACCOUNT, _SIBLING, "availability")
    )
    assert failing_id is not None
    assert sibling_id is not None

    coordinators = entry.runtime_data["coordinators"]
    calendar = coordinators["calendar"]
    properties = coordinators["properties"]

    def _failing_state() -> str:
        """Return the failing property's current sensor state string."""
        state = hass.states.get(failing_id)
        assert state is not None
        return str(state.state)

    def _sibling_state() -> str:
        """Return the sibling property's current sensor state string."""
        state = hass.states.get(sibling_id)
        assert state is not None
        return str(state.state)

    # After setup the failing property booked correctly.
    assert _failing_state() == "booked"
    assert _sibling_state() == "available"

    # First two strikes: last-good "booked" is retained, not "unavailable".
    for _ in range(2):
        await calendar.async_refresh()
        await hass.async_block_till_done()
        assert _failing_state() == "booked"
        assert _failing_state() != STATE_UNAVAILABLE
        assert _sibling_state() == "available"

    # Third consecutive strike: the failing sensor degrades to unavailable
    # while the sibling stays available and correct.
    await calendar.async_refresh()
    await hass.async_block_till_done()
    assert _failing_state() == STATE_UNAVAILABLE
    assert _sibling_state() == "available"

    # The properties coordinator is entirely unaffected throughout.
    assert properties.last_update_success is True
    assert properties.consecutive_failures == 0

    # Recovery: a successful fetch resets the counter and restores state.
    await calendar.async_refresh()
    await hass.async_block_till_done()
    assert _failing_state() == "booked"
    assert _failing_state() != STATE_UNAVAILABLE
    assert _sibling_state() == "available"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


def _calendar_payload_response(*, available: bool, reason: str) -> httpx.Response:
    """Return a fresh 200 response so respx does not reuse a consumed one."""
    return httpx.Response(
        200, json=_calendar_payload(available=available, reason=reason)
    )
