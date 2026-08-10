# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Data coordinator classes for Hospitable polling domains."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from custom_components.hospitable.api.models import (
    HospitableProperty,
    HospitableReservation,
)

DataT = TypeVar("DataT")


class _HospitableCoordinator[DataT]:
    """Small coordinator facade used until entities need DataUpdateCoordinator."""

    default_minutes: int
    floor_minutes: int

    def __init__(
        self, update_method: Callable[[], Awaitable[DataT]] | None = None
    ) -> None:
        """Initialize the coordinator with an optional refresh callable."""
        self._update_method = update_method
        self.data: DataT | None = None
        self.last_update_success = True
        self.last_exception: Exception | None = None

    async def async_refresh(self) -> None:
        """Refresh coordinator data without affecting other coordinators."""
        if self._update_method is None:
            self.data = None
            return
        try:
            self.data = await self._update_method()
        except Exception as exc:
            self.last_update_success = False
            self.last_exception = exc
            raise
        self.last_update_success = True
        self.last_exception = None


class HospitableReservationsCoordinator(
    _HospitableCoordinator[list[HospitableReservation]]
):
    """Coordinator for reservation data keyed by property identifier."""

    default_minutes = 5
    floor_minutes = 1


class HospitablePropertiesCoordinator(
    _HospitableCoordinator[dict[str, HospitableProperty]]
):
    """Coordinator for property data keyed by property identifier."""

    default_minutes = 60
    floor_minutes = 15


class HospitableCalendarCoordinator(_HospitableCoordinator[object]):
    """Coordinator for calendar data keyed by property identifier."""

    default_minutes = 60
    floor_minutes = 15
