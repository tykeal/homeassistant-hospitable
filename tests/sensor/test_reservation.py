# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase reservation sensor state tests (T072)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from custom_components.hospitable.api.models import HospitableReservation
from tests.helpers import load_fixture

NINE_OPTIONS = {
    "no_reservation",
    "awaiting_checkin",
    "occupied",
    "checked_out",
    "pending_request",
    "checkpoint",
    "cancelled",
    "not_accepted",
    "unknown",
}


def _module() -> Any:
    """Import the not-yet-implemented reservation sensor module."""
    import custom_components.hospitable.sensor.reservation as reservation

    return reservation


def _reservation(fixture: str) -> HospitableReservation:
    """Build a reservation model from a fixture's first item."""
    return HospitableReservation.from_api(load_fixture(fixture)["data"][0])


def test_exactly_one_sensor_per_property() -> None:
    """The builder yields exactly one reservation sensor per property."""
    module = _module()
    coordinator = SimpleNamespace(data=[], consecutive_failures=0)
    sensors = module.build_reservation_sensors(
        coordinator,
        "acct",
        {"prop-example-001": "One", "prop-example-002": "Two"},
    )
    assert len(sensors) == 2
    unique_ids = {sensor.unique_id for sensor in sensors}
    assert unique_ids == {
        "acct_prop-example-001_reservation_status",
        "acct_prop-example-002_reservation_status",
    }


def test_options_are_the_nine_without_unavailable() -> None:
    """The enum options are exactly the nine states and never unavailable."""
    module = _module()
    assert set(module.RESERVATION_STATUS_OPTIONS) == NINE_OPTIONS
    assert len(module.RESERVATION_STATUS_OPTIONS) == 9
    assert "unavailable" not in module.RESERVATION_STATUS_OPTIONS

    coordinator = SimpleNamespace(data=[], consecutive_failures=0)
    sensor = module.HospitableReservationSensor(
        coordinator,
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )
    assert set(sensor.options) == NINE_OPTIONS


def test_state_is_always_one_of_nine_options() -> None:
    """Every computed state is a member of the enum option set."""
    module = _module()
    coordinator = SimpleNamespace(
        data=[_reservation("reservation_accepted.json")], consecutive_failures=0
    )
    sensor = module.HospitableReservationSensor(
        coordinator,
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )
    now = datetime.fromisoformat("2025-06-15T12:00:00-07:00")
    state = sensor._compute_state(now)
    assert state == "occupied"
    assert state in NINE_OPTIONS
