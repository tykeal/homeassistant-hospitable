# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase coordinator tests."""

from __future__ import annotations


def test_three_distinct_coordinators() -> None:
    """Assert coordinator classes and intervals exist."""
    from custom_components.hospitable.coordinator import (
        HospitableCalendarCoordinator,
        HospitablePropertiesCoordinator,
        HospitableReservationsCoordinator,
    )

    assert {
        HospitableReservationsCoordinator.default_minutes,
        HospitablePropertiesCoordinator.default_minutes,
        HospitableCalendarCoordinator.default_minutes,
    } == {5, 60}
    assert id(HospitablePropertiesCoordinator) != id(HospitableCalendarCoordinator)
