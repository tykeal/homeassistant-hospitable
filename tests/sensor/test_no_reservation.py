# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase no-reservation availability tests (T075, SC-012)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast


def _sensor(reservations: list[object]) -> Any:
    """Build a reservation sensor over a fake coordinator."""
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


def test_no_reservation_reads_no_reservation_state() -> None:
    """A property with no reservation reads the no_reservation state."""
    from datetime import datetime

    sensor = _sensor([])
    now = datetime.fromisoformat("2025-06-15T12:00:00-07:00")
    assert sensor._compute_state(now) == "no_reservation"


def test_no_reservation_entity_remains_available() -> None:
    """A property with no reservation remains available, not unavailable."""
    sensor = _sensor([])
    assert sensor.available is True
