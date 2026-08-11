# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase owner-stay classification tests (T076)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from custom_components.hospitable.api.models import HospitableReservation
from tests.helpers import load_fixture


def _reservation(fixture: str) -> HospitableReservation:
    """Build a reservation model from a fixture's first item."""
    return HospitableReservation.from_api(load_fixture(fixture)["data"][0])


def test_owner_stay_occupancy_matches_guest_stay() -> None:
    """An owner stay derives the same occupancy as an equivalent guest stay."""
    from custom_components.hospitable.services.occupancy import (
        derive_occupancy,
    )

    owner = _reservation("reservation_owner_stay.json")
    guest = _reservation("reservation_accepted.json")
    now = datetime.fromisoformat("2025-06-15T12:00:00-07:00")

    assert owner.stay_type == "owner"
    assert guest.stay_type == "guest"
    assert (
        derive_occupancy(owner, now).state
        == derive_occupancy(guest, now).state
        == "occupied"
    )


def test_owner_stay_distinguished_by_attribute_not_state() -> None:
    """Stay type appears as an attribute, never folded into the enum state."""
    from types import SimpleNamespace

    from custom_components.hospitable.sensor.reservation import (
        HospitableReservationSensor,
    )

    owner = _reservation("reservation_owner_stay.json")
    coordinator = SimpleNamespace(data=[owner], consecutive_failures=0)
    sensor = HospitableReservationSensor(
        cast(Any, coordinator),
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )
    now = datetime.fromisoformat("2025-06-15T12:00:00-07:00")
    state = sensor._compute_state(now)
    assert state == "occupied"
    assert state != "owner"
    assert sensor.extra_state_attributes["stay_type"] == "owner"
