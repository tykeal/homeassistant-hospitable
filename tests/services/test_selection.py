# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase reservation-selection tests (T071)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from custom_components.hospitable.api.models import HospitableReservation
from tests.helpers import load_fixture


def _select_reservation() -> Any:
    """Import the not-yet-implemented selection function."""
    from custom_components.hospitable.services.selection import (  # type: ignore
        select_reservation,
    )

    return select_reservation


def _reservation(overrides: dict[str, Any]) -> HospitableReservation:
    """Build a reservation model from the accepted fixture plus overrides."""
    payload = load_fixture("reservation_accepted.json")["data"][0]
    payload.update(overrides)
    return HospitableReservation.from_api(payload)


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T071 services/selection.py not implemented",
)
def test_tie_break_is_deterministic_by_ascending_id() -> None:
    """Two equally ranked reservations select the lower identifier."""
    select_reservation = _select_reservation()
    res_b = _reservation({"id": "res-b"})
    res_a = _reservation({"id": "res-a"})
    now = datetime.fromisoformat("2025-06-01T12:00:00-07:00")

    selected_one, _ = select_reservation([res_a, res_b], now)
    selected_two, _ = select_reservation([res_b, res_a], now)
    assert selected_one is not None
    assert selected_one.reservation_id == "res-a"
    assert selected_two is not None
    assert selected_two.reservation_id == "res-a"


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T071 services/selection.py not implemented",
)
def test_in_progress_reservation_wins() -> None:
    """A currently occupied reservation outranks a future arrival."""
    select_reservation = _select_reservation()
    occupied = _reservation({"id": "res-now"})
    future = _reservation(
        {
            "id": "res-future",
            "arrival_date": "2025-07-01T00:00:00-07:00",
            "departure_date": "2025-07-03T00:00:00-07:00",
            "check_in": "2025-07-01T16:00:00-07:00",
            "check_out": "2025-07-03T11:00:00-07:00",
        }
    )
    now = datetime.fromisoformat("2025-06-15T12:00:00-07:00")

    selected, upcoming = select_reservation([future, occupied], now)
    assert selected is not None
    assert selected.reservation_id == "res-now"
    assert any(r.reservation_id == "res-future" for r in upcoming)


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T071 services/selection.py not implemented",
)
def test_cancelled_ranks_below_active() -> None:
    """A cancelled reservation ranks below an active one in the same tier."""
    select_reservation = _select_reservation()
    active = _reservation(
        {
            "id": "res-active",
            "arrival_date": "2025-07-05T00:00:00-07:00",
            "departure_date": "2025-07-07T00:00:00-07:00",
            "check_in": "2025-07-05T16:00:00-07:00",
            "check_out": "2025-07-07T11:00:00-07:00",
        }
    )
    cancelled_payload = load_fixture("reservation_cancelled.json")["data"][0]
    cancelled_payload.update(
        {
            "id": "res-cancelled",
            "arrival_date": "2025-07-01T00:00:00-07:00",
            "departure_date": "2025-07-03T00:00:00-07:00",
            "check_in": "2025-07-01T16:00:00-07:00",
            "check_out": "2025-07-03T11:00:00-07:00",
        }
    )
    cancelled = HospitableReservation.from_api(cancelled_payload)
    now = datetime.fromisoformat("2025-06-15T12:00:00-07:00")

    selected, _ = select_reservation([cancelled, active], now)
    assert selected is not None
    assert selected.reservation_id == "res-active"


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T071 services/selection.py not implemented",
)
def test_no_reservations_returns_none() -> None:
    """An empty reservation list selects nothing."""
    select_reservation = _select_reservation()
    now = datetime.fromisoformat("2025-06-15T12:00:00-07:00")
    selected, upcoming = select_reservation([], now)
    assert selected is None
    assert upcoming == []
