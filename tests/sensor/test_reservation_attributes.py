# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase reservation sensor attribute-contract tests (T073)."""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from custom_components.hospitable.api.models import HospitableReservation
from tests.helpers import load_fixture

EXPECTED_ATTRIBUTES = {
    "reservation_id",
    "arrival_date",
    "departure_date",
    "nights",
    "scheduled_checkin",
    "scheduled_checkout",
    "guests_total",
    "guests_adults",
    "guests_children",
    "guests_infants",
    "guests_pets",
    "booking_channel",
    "channel_confirmation",
    "booking_date",
    "stay_type",
    "upcoming_reservations",
}

PII_VALUES = {"Example Guest", "guest@example.com", "+15550101000"}


def _reservation(fixture: str) -> HospitableReservation:
    """Build a reservation model from a fixture's first item."""
    return HospitableReservation.from_api(load_fixture(fixture)["data"][0])


def _sensor(reservations: list[HospitableReservation]) -> Any:
    """Build a reservation sensor bound to a fake coordinator."""
    from custom_components.hospitable.sensor.reservation import (  # type: ignore
        HospitableReservationSensor,
    )

    coordinator = SimpleNamespace(data=reservations, consecutive_failures=0)
    return HospitableReservationSensor(
        coordinator,
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T073 sensor/reservation.py not implemented",
)
def test_attribute_keys_match_contract() -> None:
    """The attribute keys match the entities.md contract exactly."""
    sensor = _sensor([_reservation("reservation_accepted.json")])
    assert set(sensor.extra_state_attributes) == EXPECTED_ATTRIBUTES


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T073 sensor/reservation.py not implemented",
)
def test_guest_counts_present_and_typed() -> None:
    """Guest counts are exposed as integers, not identities."""
    sensor = _sensor([_reservation("reservation_accepted.json")])
    attributes = sensor.extra_state_attributes
    assert attributes["guests_total"] == 3
    assert attributes["guests_adults"] == 2
    assert attributes["guests_children"] == 1
    assert attributes["guests_infants"] == 0
    assert attributes["guests_pets"] == 0


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T073 sensor/reservation.py not implemented",
)
def test_scheduled_times_are_offset_aware() -> None:
    """Scheduled check-in and check-out are the reservation's own instants."""
    sensor = _sensor([_reservation("reservation_accepted.json")])
    attributes = sensor.extra_state_attributes
    checkin = attributes["scheduled_checkin"]
    checkout = attributes["scheduled_checkout"]
    assert isinstance(checkin, datetime)
    assert checkin.tzinfo is not None
    assert isinstance(checkout, datetime)
    assert checkout.tzinfo is not None
    assert isinstance(attributes["arrival_date"], date)
    assert attributes["reservation_id"] == "res-example-accepted"


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T073 sensor/reservation.py not implemented",
)
def test_no_personal_data_in_any_attribute() -> None:
    """No guest name, email, or phone leaks into any attribute value."""
    sensor = _sensor([_reservation("reservation_accepted.json")])
    rendered = repr(sensor.extra_state_attributes)
    for personal in PII_VALUES:
        assert personal not in rendered


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T073 sensor/reservation.py not implemented",
)
def test_upcoming_reservations_carry_no_identity() -> None:
    """Upcoming entries carry status and stay type but no guest identity."""
    accepted = _reservation("reservation_accepted.json")
    other = HospitableReservation.from_api(
        {
            **load_fixture("reservation_accepted.json")["data"][0],
            "id": "res-later",
            "arrival_date": "2025-08-01T00:00:00-07:00",
            "departure_date": "2025-08-03T00:00:00-07:00",
            "check_in": "2025-08-01T16:00:00-07:00",
            "check_out": "2025-08-03T11:00:00-07:00",
        }
    )
    sensor = _sensor([accepted, other])
    upcoming = sensor.extra_state_attributes["upcoming_reservations"]
    assert isinstance(upcoming, list)
    assert upcoming
    entry = upcoming[0]
    assert set(entry) == {
        "reservation_id",
        "arrival_date",
        "departure_date",
        "status_category",
        "stay_type",
    }
