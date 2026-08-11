# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase reservation sensor attribute-contract tests (T073)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

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
    "status_sub_category",
    "upcoming_reservations",
}

PII_VALUES = {"Example Guest", "guest@example.com", "+15550101000"}


def _reservation(fixture: str) -> HospitableReservation:
    """Build a reservation model from a fixture's first item."""
    return HospitableReservation.from_api(load_fixture(fixture)["data"][0])


def _sensor(reservations: list[HospitableReservation]) -> Any:
    """Build a reservation sensor bound to a fake coordinator."""
    from custom_components.hospitable.sensor.reservation import (
        HospitableReservationSensor,
    )

    coordinator = SimpleNamespace(data=reservations, consecutive_failures=0)
    return HospitableReservationSensor(
        cast(Any, coordinator),
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )


def test_attribute_keys_match_contract() -> None:
    """The attribute keys match the entities.md contract exactly."""
    sensor = _sensor([_reservation("reservation_accepted.json")])
    assert set(sensor.extra_state_attributes) == EXPECTED_ATTRIBUTES


def test_guest_counts_present_and_typed() -> None:
    """Guest counts are exposed as integers, not identities."""
    sensor = _sensor([_reservation("reservation_accepted.json")])
    attributes = sensor.extra_state_attributes
    assert attributes["guests_total"] == 3
    assert attributes["guests_adults"] == 2
    assert attributes["guests_children"] == 1
    assert attributes["guests_infants"] == 0
    assert attributes["guests_pets"] == 0


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
    assert type(attributes["arrival_date"]) is date
    assert not isinstance(attributes["arrival_date"], datetime)
    assert type(attributes["departure_date"]) is date
    assert attributes["reservation_id"] == "res-example-accepted"


def test_no_personal_data_in_any_attribute() -> None:
    """No guest name, email, or phone leaks into any attribute value."""
    sensor = _sensor([_reservation("reservation_accepted.json")])
    rendered = repr(sensor.extra_state_attributes)
    for personal in PII_VALUES:
        assert personal not in rendered


def test_upcoming_reservations_carry_no_identity() -> None:
    """Upcoming entries carry status and stay type but no guest identity."""
    soonest = _relative_reservation("res-soon", 3, 5)
    other = _relative_reservation("res-later", 10, 12)
    sensor = _sensor([soonest, other])
    upcoming = sensor.extra_state_attributes["upcoming_reservations"]
    assert isinstance(upcoming, list)
    assert upcoming
    entry = upcoming[0]
    assert entry["reservation_id"] == "res-later"
    assert set(entry) == {
        "reservation_id",
        "arrival_date",
        "departure_date",
        "status_category",
        "stay_type",
    }


def _relative_reservation(
    reservation_id: str,
    arrival_offset: int,
    departure_offset: int,
    status_current: str = "accepted",
) -> HospitableReservation:
    """Build a reservation with dates offset from today in a fixed zone."""
    zone = timezone(timedelta(hours=-7))
    base = datetime.now(zone).date()
    arrival = base + timedelta(days=arrival_offset)
    departure = base + timedelta(days=departure_offset)
    payload = cast(dict[str, Any], load_fixture("reservation_accepted.json")["data"][0])
    payload = dict(payload)
    payload.update(
        {
            "id": reservation_id,
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


def test_upcoming_excludes_past_and_cancelled() -> None:
    """Upcoming lists only genuine forthcoming stays, not past or cancelled."""
    soonest = _relative_reservation("res-future-1", 5, 7)
    later = _relative_reservation("res-future-2", 10, 12)
    past = _relative_reservation("res-past", -10, -8)
    cancelled = _relative_reservation("res-cancelled", 6, 8, status_current="cancelled")
    sensor = _sensor([soonest, later, past, cancelled])

    upcoming_ids = {
        entry["reservation_id"]
        for entry in sensor.extra_state_attributes["upcoming_reservations"]
    }
    assert "res-future-2" in upcoming_ids
    assert "res-past" not in upcoming_ids
    assert "res-cancelled" not in upcoming_ids
