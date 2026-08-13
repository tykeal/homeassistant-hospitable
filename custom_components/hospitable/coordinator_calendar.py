# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Calendar polling coordinator for the Hospitable integration.

Defined here rather than in ``coordinator`` so that module stays within
the project's file-size budget, exactly as ``coordinator_tasks`` was
split out in US4; the shared base class and error mapping are imported
from it unchanged and the behaviour is identical. ``coordinator``
re-exports ``HospitableCalendarCoordinator`` so the documented import
path still works.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.hospitable.api.client import HospitableApiClient
from custom_components.hospitable.api.exceptions import HospitableError
from custom_components.hospitable.api.models import HospitablePropertyCalendar
from custom_components.hospitable.const import DOMAIN
from custom_components.hospitable.coordinator import HospitableDataUpdateCoordinator


class HospitableCalendarCoordinator(
    HospitableDataUpdateCoordinator[dict[str, HospitablePropertyCalendar]]
):
    """Coordinator for per-property aggregate calendar data.

    Each refresh fans out one calendar fetch per selected property. A
    failure fetching a single property's calendar degrades only that
    property: its last-good calendar is retained and the surviving
    properties still deliver fresh data. The refresh raises ``UpdateFailed``
    only when every property failed (FR-061, FR-071).
    """

    default_minutes = 60
    floor_minutes = 15

    def __init__(
        self,
        hass: HomeAssistant,
        client: HospitableApiClient,
        *,
        property_ids: list[str] | None = None,
        lookahead_days: int = 90,
        config_entry: ConfigEntry | None = None,
        interval_minutes: int | None = None,
    ) -> None:
        """Initialize the calendar coordinator with its property fan-out."""
        super().__init__(
            hass,
            name=f"{DOMAIN} calendar",
            config_entry=config_entry,
            interval_minutes=interval_minutes,
        )
        self._client: HospitableApiClient = client
        self._property_ids = list(property_ids or [])
        self._lookahead_days = lookahead_days
        self._property_failures: dict[str, int] = {}

    def property_failure_count(self, property_id: str) -> int:
        """Return consecutive calendar fetch failures for one property.

        The count resets to zero on any successful fetch of that
        property. The availability sensor uses it to degrade a single
        property after ``MAX_CONSECUTIVE_FAILURES`` consecutive strikes
        while transient blips retain last-good data (FR-057, D-15).
        """
        return self._property_failures.get(property_id, 0)

    async def _fetch_data(self) -> dict[str, HospitablePropertyCalendar]:
        """Fetch each property's calendar with per-property isolation."""
        today = dt_util.utcnow().date()
        end = today + timedelta(days=self._lookahead_days)
        # Seed with the previous cycle so a property that fails this cycle
        # retains its last-good calendar rather than vanishing.
        result: dict[str, HospitablePropertyCalendar] = dict(self.data or {})
        succeeded = False
        last_error: HospitableError | None = None
        for property_id in self._property_ids:
            try:
                result[property_id] = await self._client.get_calendar(
                    property_id, today, end
                )
                # A success resets this property's strike counter so a
                # recovered property becomes available again.
                self._property_failures[property_id] = 0
                succeeded = True
            except HospitableError as exc:
                # Count strikes per property so a persistently failing
                # property degrades on its own without waiting for every
                # property to fail (D-15, FR-057).
                self._property_failures[property_id] = (
                    self._property_failures.get(property_id, 0) + 1
                )
                last_error = exc
        # Never leak a counter for a property that has left the fan-out.
        active = set(self._property_ids)
        self._property_failures = {
            property_id: count
            for property_id, count in self._property_failures.items()
            if property_id in active
        }
        if self._property_ids and not succeeded and last_error is not None:
            self._raise_for_api_error(last_error)
        return result
