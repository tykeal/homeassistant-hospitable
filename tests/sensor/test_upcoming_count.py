# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the upcoming-reservations count sensor.

Covers T090 (FR-052): the count sensor counts only reservations that are
real forthcoming stays, using the shared ``is_forthcoming`` predicate so
its value can never disagree with the reservation-status sensor's
``upcoming_reservations`` attribute.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

from homeassistant.components.sensor import SensorStateClass

from custom_components.hospitable.api.models import HospitableReservation
from custom_components.hospitable.sensor.property import (
    HospitableUpcomingReservationsSensor,
)
from custom_components.hospitable.services.selection import is_forthcoming
from tests.helpers import load_fixture

_ZONE = timezone(timedelta(hours=-7))


def _reservation(
    reservation_id: str,
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
            "properties": [{"id": "prop-example-001"}],
            "arrival_date": f"{arrival.isoformat()}T00:00:00-07:00",
            "departure_date": f"{departure.isoformat()}T00:00:00-07:00",
            "check_in": f"{arrival.isoformat()}T16:00:00-07:00",
            "check_out": f"{departure.isoformat()}T11:00:00-07:00",
        }
    )
    payload["reservation_status"] = {
        "current": {"category": status_current, "sub_category": None},
        "history": [],
    }
    return HospitableReservation.from_api(payload)


def _count_sensor(reservations: list[HospitableReservation]) -> Any:
    """Build an upcoming-reservations count sensor on fake coordinators."""
    reservations_coordinator = SimpleNamespace(
        data=reservations, consecutive_failures=0
    )
    properties_coordinator = SimpleNamespace(
        data={"prop-example-001": SimpleNamespace(name="Example")},
        consecutive_failures=0,
        monitored_property_ids={"prop-example-001"},
    )
    return HospitableUpcomingReservationsSensor(
        cast(Any, reservations_coordinator),
        properties_coordinator=cast(Any, properties_coordinator),
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )


def test_count_declares_measurement_state_class() -> None:
    """The count sensor uses the ``MEASUREMENT`` state class."""
    sensor = _count_sensor([_reservation("res-a", 3, 5)])
    assert sensor.state_class is SensorStateClass.MEASUREMENT


def test_count_excludes_past_and_cancelled() -> None:
    """The count includes only forthcoming, non-cancelled reservations."""
    reservations = [
        _reservation("res-future-1", 5, 7),
        _reservation("res-future-2", 10, 12),
        _reservation("res-past", -10, -8),
        _reservation("res-cancelled", 6, 8, status_current="cancelled"),
    ]
    sensor = _count_sensor(reservations)
    assert sensor.native_value == 2


def test_count_matches_is_forthcoming_predicate() -> None:
    """The count equals the number of reservations ``is_forthcoming`` accepts."""
    now = datetime.now(UTC)
    reservations = [
        _reservation("res-future-1", 5, 7),
        _reservation("res-future-2", 10, 12),
        _reservation("res-past", -3, -1),
        _reservation("res-cancelled", 6, 8, status_current="cancelled"),
        _reservation("res-not-accepted", 9, 11, status_current="not accepted"),
    ]
    sensor = _count_sensor(reservations)
    expected = sum(1 for r in reservations if is_forthcoming(r, now))
    assert sensor.native_value == expected


def test_count_zero_when_no_forthcoming() -> None:
    """With only past reservations the count is zero, never ``None``."""
    sensor = _count_sensor([_reservation("res-past", -10, -8)])
    assert sensor.native_value == 0
