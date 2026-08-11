# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Alignment tests for the single forthcoming predicate (D8).

``next_arrival`` is instant-based and ``upcoming_reservations`` counts
through ``is_forthcoming``. These must never contradict, so a guest
arriving later today has to be simultaneously the value of
``next_arrival``, counted by the upcoming-reservations sensor, and
present in the reservation_status sensor's ``upcoming_reservations``
attribute. When the scheduled instant is unavailable or naive the
predicate falls back to the date comparison, which these tests also
cover.

The reservation_status sensor lists only the non-selected remainder in
its ``upcoming_reservations`` attribute, so each scenario pairs the
reservation under test with a currently-occupied anchor that is chosen
as the representative, leaving the forthcoming stay in the upcoming
list.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

from homeassistant.util import dt as dt_util

from custom_components.hospitable.api.models import HospitableReservation
from custom_components.hospitable.sensor.property import (
    HospitableNextArrivalSensor,
    HospitableUpcomingReservationsSensor,
)
from custom_components.hospitable.sensor.reservation import (
    HospitableReservationSensor,
)
from custom_components.hospitable.services.selection import is_forthcoming
from tests.helpers import load_fixture

_ZONE = timezone(timedelta(hours=-7))


def _reservation(
    reservation_id: str,
    *,
    check_in: datetime | str | None,
    arrival_date: str,
    departure_date: str,
    check_out: str,
    status_current: str = "accepted",
) -> HospitableReservation:
    """Build a reservation with explicit instants and dates."""
    payload = dict(load_fixture("reservation_accepted.json")["data"][0])
    if isinstance(check_in, datetime):
        check_in_value: str | None = check_in.isoformat()
    else:
        check_in_value = check_in
    payload.update(
        {
            "id": reservation_id,
            "properties": [{"id": "prop-example-001"}],
            "arrival_date": arrival_date,
            "departure_date": departure_date,
            "check_in": check_in_value,
            "check_out": check_out,
        }
    )
    payload["reservation_status"] = {
        "current": {"category": status_current, "sub_category": None},
        "history": [],
    }
    return HospitableReservation.from_api(payload)


def _occupied_anchor(now: datetime) -> HospitableReservation:
    """Build a currently-occupied reservation to act as the representative."""
    yesterday = (now.astimezone(_ZONE).date() - timedelta(days=1)).isoformat()
    tomorrow = (now.astimezone(_ZONE).date() + timedelta(days=1)).isoformat()
    return _reservation(
        "res-anchor",
        check_in=(now - timedelta(days=1)).astimezone(_ZONE),
        arrival_date=f"{yesterday}T00:00:00-07:00",
        departure_date=f"{tomorrow}T00:00:00-07:00",
        check_out=(now + timedelta(days=1)).astimezone(_ZONE).isoformat(),
    )


def _all_three_surfaces(
    reservations: list[HospitableReservation],
) -> tuple[int, list[str], datetime | None]:
    """Return the count, the attribute id list, and next_arrival's value."""
    reservations_coordinator = SimpleNamespace(
        data=reservations, consecutive_failures=0
    )
    properties_coordinator = SimpleNamespace(
        data={"prop-example-001": SimpleNamespace(name="Example")},
        consecutive_failures=0,
        monitored_property_ids={"prop-example-001"},
    )
    count_sensor = HospitableUpcomingReservationsSensor(
        cast(Any, reservations_coordinator),
        properties_coordinator=cast(Any, properties_coordinator),
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )
    arrival_sensor = HospitableNextArrivalSensor(
        cast(Any, reservations_coordinator),
        properties_coordinator=cast(Any, properties_coordinator),
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )
    status_sensor = HospitableReservationSensor(
        cast(Any, reservations_coordinator),
        properties_coordinator=cast(Any, properties_coordinator),
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )
    attribute_ids = [
        entry["reservation_id"]
        for entry in status_sensor.extra_state_attributes["upcoming_reservations"]
    ]
    return count_sensor.native_value, attribute_ids, arrival_sensor.native_value


def test_arriving_later_today_agrees_across_all_three() -> None:
    """A guest arriving later today is counted, listed and next_arrival."""
    now = dt_util.utcnow()
    check_in = now + timedelta(hours=3)
    arrival_local = now.astimezone(_ZONE).date()
    day_two = (arrival_local + timedelta(days=2)).isoformat()
    reservation = _reservation(
        "res-today",
        check_in=check_in.astimezone(_ZONE),
        arrival_date=f"{arrival_local.isoformat()}T00:00:00-07:00",
        departure_date=f"{day_two}T00:00:00-07:00",
        check_out=f"{day_two}T11:00:00-07:00",
    )

    count, attribute_ids, next_arrival = _all_three_surfaces(
        [_occupied_anchor(now), reservation]
    )

    assert count == 1
    assert attribute_ids == ["res-today"]
    assert next_arrival is not None
    assert next_arrival == check_in


def test_already_checked_in_today_absent_from_all_three() -> None:
    """A guest already checked in today is in none of the three surfaces."""
    now = dt_util.utcnow()
    check_in = now - timedelta(hours=3)
    arrival_local = now.astimezone(_ZONE).date()
    day_two = (arrival_local + timedelta(days=2)).isoformat()
    reservation = _reservation(
        "res-past-today",
        check_in=check_in.astimezone(_ZONE),
        arrival_date=f"{arrival_local.isoformat()}T00:00:00-07:00",
        departure_date=f"{day_two}T00:00:00-07:00",
        check_out=f"{day_two}T11:00:00-07:00",
    )

    count, attribute_ids, next_arrival = _all_three_surfaces([reservation])

    assert count == 0
    assert attribute_ids == []
    assert next_arrival is None


def test_missing_instant_falls_back_to_future_date() -> None:
    """A missing instant with a future arrival date is forthcoming."""
    now = dt_util.utcnow()
    tomorrow = (now.astimezone(_ZONE).date() + timedelta(days=1)).isoformat()
    day_after = (now.astimezone(_ZONE).date() + timedelta(days=2)).isoformat()
    reservation = _reservation(
        "res-missing-future",
        check_in=None,
        arrival_date=f"{tomorrow}T00:00:00-07:00",
        departure_date=f"{day_after}T00:00:00-07:00",
        check_out=f"{day_after}T11:00:00-07:00",
    )

    assert is_forthcoming(reservation, now) is True

    count, attribute_ids, next_arrival = _all_three_surfaces(
        [_occupied_anchor(now), reservation]
    )

    assert count == 1
    assert attribute_ids == ["res-missing-future"]
    assert next_arrival is None


def test_naive_instant_falls_back_to_date_predicate() -> None:
    """A naive scheduled instant defers to the date comparison in the predicate."""
    now = dt_util.utcnow()
    tomorrow = (now.astimezone(_ZONE).date() + timedelta(days=1)).isoformat()
    yesterday = (now.astimezone(_ZONE).date() - timedelta(days=1)).isoformat()
    day_after = (now.astimezone(_ZONE).date() + timedelta(days=2)).isoformat()
    today = now.astimezone(_ZONE).date().isoformat()

    naive_future = _reservation(
        "res-naive-future",
        check_in=f"{tomorrow}T16:00:00",
        arrival_date=f"{tomorrow}T00:00:00-07:00",
        departure_date=f"{day_after}T00:00:00-07:00",
        check_out=f"{day_after}T11:00:00-07:00",
    )
    naive_past = _reservation(
        "res-naive-past",
        check_in=f"{yesterday}T16:00:00",
        arrival_date=f"{yesterday}T00:00:00-07:00",
        departure_date=f"{today}T00:00:00-07:00",
        check_out=f"{today}T11:00:00-07:00",
    )

    assert is_forthcoming(naive_future, now) is True
    assert is_forthcoming(naive_past, now) is False
