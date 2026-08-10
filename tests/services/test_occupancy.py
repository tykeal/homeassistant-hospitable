# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase occupancy derivation tests (T070)."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pytest

from custom_components.hospitable.api.models import HospitableReservation
from tests.helpers import load_fixture


def _derive_occupancy() -> Any:
    """Import the not-yet-implemented occupancy derivation function."""
    from custom_components.hospitable.services.occupancy import (
        derive_occupancy,
    )

    return derive_occupancy


def _reservation(fixture: str) -> HospitableReservation:
    """Build a reservation model from a fixture's first item."""
    return HospitableReservation.from_api(load_fixture(fixture)["data"][0])


def test_future_arrival_is_awaiting_checkin() -> None:
    """Before the arrival date the state is awaiting check-in."""
    derive_occupancy = _derive_occupancy()
    reservation = _reservation("reservation_accepted.json")
    now = datetime.fromisoformat("2025-06-10T12:00:00-07:00")
    assert derive_occupancy(reservation, now).state == "awaiting_checkin"


def test_mid_stay_is_occupied() -> None:
    """Between scheduled check-in and check-out the state is occupied."""
    derive_occupancy = _derive_occupancy()
    reservation = _reservation("reservation_accepted.json")
    now = datetime.fromisoformat("2025-06-15T12:00:00-07:00")
    assert derive_occupancy(reservation, now).state == "occupied"


def test_after_checkout_is_checked_out() -> None:
    """At or after the scheduled check-out moment the state is checked out."""
    derive_occupancy = _derive_occupancy()
    reservation = _reservation("reservation_accepted.json")
    now = datetime.fromisoformat("2025-06-16T12:00:00-07:00")
    assert derive_occupancy(reservation, now).state == "checked_out"


def test_arrives_today_before_checkin_is_awaiting_not_occupied() -> None:
    """On the arrival date before check-in the state is awaiting check-in."""
    derive_occupancy = _derive_occupancy()
    reservation = _reservation("reservation_accepted.json")
    now = datetime.fromisoformat("2025-06-14T10:00:00-07:00")
    state = derive_occupancy(reservation, now).state
    assert state == "awaiting_checkin"
    assert state != "occupied"


def test_departs_today_after_checkout_is_checked_out_not_occupied() -> None:
    """On the departure date after check-out the state is checked out."""
    derive_occupancy = _derive_occupancy()
    reservation = _reservation("reservation_accepted.json")
    now = datetime.fromisoformat("2025-06-16T14:00:00-07:00")
    state = derive_occupancy(reservation, now).state
    assert state == "checked_out"
    assert state != "occupied"


def test_missing_checkin_on_arrival_date_is_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A missing check-in time on the arrival date yields unknown positively."""
    derive_occupancy = _derive_occupancy()
    reservation = _reservation("reservation_missing_checkin_time.json")
    now = datetime.fromisoformat("2025-06-14T20:00:00-07:00")
    with caplog.at_level(logging.WARNING):
        result = derive_occupancy(reservation, now)
    assert result.state == "unknown"
    assert result.state != "awaiting_checkin"
    assert "res-example-001" in caplog.text
    assert "check_in" in caplog.text


def test_missing_checkout_on_departure_date_is_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A missing check-out time on the departure date yields unknown."""
    derive_occupancy = _derive_occupancy()
    reservation = _reservation("reservation_missing_checkout_time.json")
    now = datetime.fromisoformat("2025-06-16T20:00:00-07:00")
    with caplog.at_level(logging.WARNING):
        result = derive_occupancy(reservation, now)
    assert result.state == "unknown"
    assert "res-example-001" in caplog.text
    assert "check_out" in caplog.text


def test_unparsable_checkin_on_arrival_date_is_unknown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unparsable check-in time on the arrival date yields unknown."""
    derive_occupancy = _derive_occupancy()
    reservation = _reservation("reservation_unparsable_time.json")
    now = datetime.fromisoformat("2025-06-14T20:00:00-07:00")
    with caplog.at_level(logging.WARNING):
        result = derive_occupancy(reservation, now)
    assert result.state == "unknown"
    assert result.state != "awaiting_checkin"
    assert "res-example-001" in caplog.text
    assert "check_in" in caplog.text


def test_degradation_scoped_to_boundary_dates_only() -> None:
    """Three days into the stay an unparsable time still resolves to occupied."""
    derive_occupancy = _derive_occupancy()
    reservation = _reservation("reservation_unparsable_time.json")
    now = datetime.fromisoformat("2025-06-15T12:00:00-07:00")
    result = derive_occupancy(reservation, now)
    assert result.state == "occupied"
    assert result.state != "unknown"
