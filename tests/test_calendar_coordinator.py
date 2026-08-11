# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase calendar coordinator tests (T139, FR-061, FR-071).

The calendar coordinator refreshes on the property cadence (60-minute
default, 15-minute floor) and fans out one calendar fetch per selected
property. A failure fetching a single property's calendar degrades only
that property: the surviving properties still deliver correct data, the
calendar refresh as a whole still succeeds, and the wholly separate
properties coordinator is entirely unaffected.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.helpers import load_fixture


@pytest.mark.xfail(
    raises=TypeError,
    strict=True,
    reason="TDD red phase: T145 calendar coordinator property fan-out missing",
)
async def test_calendar_per_property_failure_isolation(
    hass: Any,
    respx_router: Any,
    api_client_factory: Any,
    mock_httpx_client: Any,
    synthetic_token: str,
) -> None:
    """One property's 500 degrades only that property, not the others."""
    from custom_components.hospitable.api.const import BASE_URL
    from custom_components.hospitable.coordinator import (
        HospitableCalendarCoordinator,
        HospitablePropertiesCoordinator,
    )

    # The calendar coordinator runs on the property cadence.
    assert HospitableCalendarCoordinator.default_minutes == 60
    assert HospitableCalendarCoordinator.floor_minutes == 15

    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(200, json=load_fixture("properties_page1.json")),
            httpx.Response(200, json=load_fixture("properties_page2.json")),
        ]
    )
    # Exactly one property's calendar URL fails; the other succeeds.
    respx_router.get(f"{BASE_URL}/properties/prop-example-001/calendar").mock(
        return_value=httpx.Response(200, json=load_fixture("calendar_prop1.json"))
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-002/calendar").mock(
        return_value=httpx.Response(500, json=load_fixture("error_500.json"))
    )

    client = api_client_factory(mock_httpx_client, synthetic_token)
    calendar_factory: Any = HospitableCalendarCoordinator
    coordinator = calendar_factory(
        hass,
        client,
        property_ids=["prop-example-001", "prop-example-002"],
        lookahead_days=7,
    )
    await coordinator.async_refresh()

    # A partial failure is still a successful refresh.
    assert coordinator.last_update_success is True
    assert coordinator.consecutive_failures == 0

    # The surviving property's data is present and correct.
    assert "prop-example-001" in coordinator.data
    surviving = coordinator.data["prop-example-001"]
    assert surviving.property_id == "prop-example-001"
    assert len(surviving.days) == 3

    # The failing property degrades specifically: no fresh data for it.
    assert "prop-example-002" not in coordinator.data

    # The properties coordinator is wholly separate and untouched.
    properties = HospitablePropertiesCoordinator(hass, client)
    await properties.async_refresh()
    assert properties.last_update_success is True
    assert properties.consecutive_failures == 0
    assert set(properties.data) == {"prop-example-001", "prop-example-002"}


@pytest.mark.xfail(
    raises=TypeError,
    strict=True,
    reason="TDD red phase: T145 calendar coordinator all-fail path missing",
)
async def test_calendar_refresh_fails_only_when_every_property_fails(
    hass: Any,
    respx_router: Any,
    api_client_factory: Any,
    mock_httpx_client: Any,
    synthetic_token: str,
) -> None:
    """The refresh reports failure only when every property fails."""
    from custom_components.hospitable.api.const import BASE_URL
    from custom_components.hospitable.coordinator import (
        HospitableCalendarCoordinator,
    )

    respx_router.get(f"{BASE_URL}/properties/prop-example-001/calendar").mock(
        return_value=httpx.Response(500, json=load_fixture("error_500.json"))
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-002/calendar").mock(
        return_value=httpx.Response(500, json=load_fixture("error_500.json"))
    )

    client = api_client_factory(mock_httpx_client, synthetic_token)
    calendar_factory: Any = HospitableCalendarCoordinator
    coordinator = calendar_factory(
        hass,
        client,
        property_ids=["prop-example-001", "prop-example-002"],
        lookahead_days=7,
    )
    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
