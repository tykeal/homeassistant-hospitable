# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for the next-arrival/next-departure timestamp sensors.

These cover T089 (FR-051): ``next_arrival`` and ``next_departure`` are
``TIMESTAMP`` sensors whose state is the reservation's own offset-aware
instant, and are ``None`` rather than a stale value when there is no
applicable future reservation.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.api.models import HospitableReservation
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from custom_components.hospitable.entity import build_unique_id
from tests.helpers import load_fixture

_ZONE = timezone(timedelta(hours=-7))


def _reservation(
    reservation_id: str,
    property_id: str,
    arrival_offset: int,
    departure_offset: int,
    status_current: str = "accepted",
) -> HospitableReservation:
    """Build a reservation offset from today in a fixed -0700 zone."""
    base = datetime.now(_ZONE).date()
    arrival = base + timedelta(days=arrival_offset)
    departure = base + timedelta(days=departure_offset)
    payload = dict(load_fixture("reservation_accepted.json")["data"][0])
    payload.update(
        {
            "id": reservation_id,
            "properties": [{"id": property_id}],
            "arrival_date": f"{arrival.isoformat()}T00:00:00-07:00",
            "departure_date": f"{departure.isoformat()}T00:00:00-07:00",
            "check_in": f"{arrival.isoformat()}T16:00:00-07:00",
            "check_out": f"{departure.isoformat()}T11:00:00-07:00",
        }
    )
    payload["reservation_status"] = {"current": status_current, "history": []}
    return HospitableReservation.from_api(payload)


def _timestamp_sensors(reservations: list[HospitableReservation]) -> tuple[Any, Any]:
    """Build next-arrival and next-departure sensors on fake coordinators."""
    from custom_components.hospitable.sensor.property import (  # type: ignore
        HospitableNextArrivalSensor,
        HospitableNextDepartureSensor,
    )

    reservations_coordinator = SimpleNamespace(
        data=reservations, consecutive_failures=0
    )
    properties_coordinator = SimpleNamespace(
        data={"prop-example-001": SimpleNamespace(name="Example")},
        consecutive_failures=0,
        monitored_property_ids={"prop-example-001"},
    )
    kwargs = {
        "properties_coordinator": cast(Any, properties_coordinator),
        "account_namespace": "acct",
        "property_id": "prop-example-001",
        "property_name": "Example",
    }
    arrival = HospitableNextArrivalSensor(cast(Any, reservations_coordinator), **kwargs)
    departure = HospitableNextDepartureSensor(
        cast(Any, reservations_coordinator), **kwargs
    )
    return arrival, departure


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T089 sensor/property.py not implemented",
)
def test_timestamp_sensors_declare_timestamp_device_class() -> None:
    """Both timestamp sensors advertise ``SensorDeviceClass.TIMESTAMP``."""
    arrival, departure = _timestamp_sensors(
        [_reservation("res-future", "prop-example-001", 3, 5)]
    )
    assert arrival.device_class is SensorDeviceClass.TIMESTAMP
    assert departure.device_class is SensorDeviceClass.TIMESTAMP


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T089 sensor/property.py not implemented",
)
def test_next_arrival_preserves_offset_aware_instant() -> None:
    """Next arrival is the reservation's own offset-aware check-in moment."""
    arrival, _ = _timestamp_sensors(
        [_reservation("res-future", "prop-example-001", 3, 5)]
    )
    value = arrival.native_value
    assert isinstance(value, datetime)
    assert value.tzinfo is not None
    assert value.utcoffset() == timedelta(hours=-7)
    assert value.hour == 16


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T089 sensor/property.py not implemented",
)
def test_next_departure_preserves_offset_aware_instant() -> None:
    """Next departure is the reservation's own offset-aware check-out moment."""
    _, departure = _timestamp_sensors(
        [_reservation("res-future", "prop-example-001", 3, 5)]
    )
    value = departure.native_value
    assert isinstance(value, datetime)
    assert value.tzinfo is not None
    assert value.hour == 11


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T089 sensor/property.py not implemented",
)
def test_no_future_reservation_reports_none_not_stale() -> None:
    """With only a past reservation both sensors report ``None``, not stale."""
    arrival, departure = _timestamp_sensors(
        [_reservation("res-past", "prop-example-001", -10, -8)]
    )
    assert arrival.native_value is None
    assert departure.native_value is None


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T089 sensor/property.py not implemented",
)
def test_cancelled_future_reservation_is_not_next_arrival() -> None:
    """A cancelled future stay never becomes the next arrival or departure."""
    arrival, departure = _timestamp_sensors(
        [_reservation("res-x", "prop-example-001", 4, 6, status_current="cancelled")]
    )
    assert arrival.native_value is None
    assert departure.native_value is None


def _occupied_reservation(reservation_id: str, property_id: str) -> dict[str, Any]:
    """Build an accepted reservation arriving in the future for a property."""
    base = datetime.now(_ZONE).date()
    arrival = base + timedelta(days=3)
    departure = base + timedelta(days=6)
    payload = dict(load_fixture("reservation_accepted.json")["data"][0])
    payload.update(
        {
            "id": reservation_id,
            "properties": [{"id": property_id}],
            "arrival_date": f"{arrival.isoformat()}T00:00:00-07:00",
            "departure_date": f"{departure.isoformat()}T00:00:00-07:00",
            "check_in": f"{arrival.isoformat()}T16:00:00-07:00",
            "check_out": f"{departure.isoformat()}T11:00:00-07:00",
        }
    )
    return payload


def _past_reservation(reservation_id: str, property_id: str) -> dict[str, Any]:
    """Build an accepted reservation entirely in the past for a property."""
    base = datetime.now(_ZONE).date()
    arrival = base - timedelta(days=10)
    departure = base - timedelta(days=8)
    payload = dict(load_fixture("reservation_accepted.json")["data"][0])
    payload.update(
        {
            "id": reservation_id,
            "properties": [{"id": property_id}],
            "arrival_date": f"{arrival.isoformat()}T00:00:00-07:00",
            "departure_date": f"{departure.isoformat()}T00:00:00-07:00",
            "check_in": f"{arrival.isoformat()}T16:00:00-07:00",
            "check_out": f"{departure.isoformat()}T11:00:00-07:00",
        }
    )
    return payload


def _reservations_payload() -> dict[str, Any]:
    """Envelope: prop-001 has a future stay, prop-002 only a past stay."""
    return {
        "data": [
            _occupied_reservation("res-e2e-001", "prop-example-001"),
            _past_reservation("res-e2e-002", "prop-example-002"),
        ],
        "meta": {
            "current_page": 1,
            "last_page": 1,
            "path": "http://public.api.hospitable.com/v2/reservations",
            "per_page": 100,
            "total": 2,
        },
    }


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T089 timestamp sensors not created by platform",
)
async def test_timestamp_sensors_end_to_end(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """A full setup creates the timestamp sensors with correct state.

    prop-001 has a future reservation so ``next_arrival`` and
    ``next_departure`` carry offset-aware instants; prop-002 has only a
    past reservation so both report ``None`` rather than a stale value.
    """
    from custom_components.hospitable.api.const import BASE_URL

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: synthetic_token,
            CONF_ACCOUNT_NAMESPACE: "acct-example-0001",
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
        },
        unique_id="acct-example-0001",
    )
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(200, json=load_fixture("properties_page1.json")),
            httpx.Response(200, json=load_fixture("properties_page2.json")),
        ]
    )
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=_reservations_payload())
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    entity_registry = er.async_get(hass)

    arrival_uid = build_unique_id(
        "acct-example-0001", "prop-example-001", "next_arrival"
    )
    arrival_id = entity_registry.async_get_entity_id("sensor", DOMAIN, arrival_uid)
    assert arrival_id is not None
    arrival_state = hass.states.get(arrival_id)
    assert arrival_state is not None
    assert arrival_state.state not in ("unknown", "unavailable")

    dep_uid = build_unique_id("acct-example-0001", "prop-example-001", "next_departure")
    dep_id = entity_registry.async_get_entity_id("sensor", DOMAIN, dep_uid)
    assert dep_id is not None

    empty_uid = build_unique_id("acct-example-0001", "prop-example-002", "next_arrival")
    empty_id = entity_registry.async_get_entity_id("sensor", DOMAIN, empty_uid)
    assert empty_id is not None
    empty_state = hass.states.get(empty_id)
    assert empty_state is not None
    assert empty_state.state == "unknown"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
