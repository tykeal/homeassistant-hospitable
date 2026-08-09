# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase coordinator tests."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T038 coordinators"
)
def test_three_distinct_coordinators() -> None:
    """Assert coordinator classes and intervals exist."""
    from custom_components.hospitable.coordinator import (  # type: ignore[import-not-found, import-untyped, unused-ignore]
        HospitableCalendarCoordinator,
        HospitablePropertiesCoordinator,
        HospitableReservationsCoordinator,
    )

    assert {
        HospitableReservationsCoordinator.default_minutes,
        HospitablePropertiesCoordinator.default_minutes,
        HospitableCalendarCoordinator.default_minutes,
    } == {5, 60}
    assert HospitablePropertiesCoordinator is not HospitableCalendarCoordinator
