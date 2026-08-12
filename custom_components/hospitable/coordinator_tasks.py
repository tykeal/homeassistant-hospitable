# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Task polling coordinator for the Hospitable integration.

Defined here rather than in ``coordinator`` so that module stays within
the project's file-size budget; the shared base class and error mapping
are imported from it unchanged.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.hospitable.api.client import HospitableApiClient
from custom_components.hospitable.api.exceptions import HospitableError
from custom_components.hospitable.api.models import HospitableTask
from custom_components.hospitable.const import (
    DEFAULT_TASK_INTERVAL,
    DEFAULT_TASK_WINDOW_DAYS,
    DOMAIN,
    MIN_TASK_INTERVAL,
)
from custom_components.hospitable.coordinator import HospitableDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class HospitableTasksCoordinator(
    HospitableDataUpdateCoordinator[dict[str, tuple[HospitableTask, ...]]]
):
    """Coordinator for per-property task data.

    Each refresh fans out ONE request per selected property. That is a
    deliberate failure-isolation choice, not a workaround: a batched
    multi-property request is accepted upstream, but it has a single
    outcome for every property, so one property's failure would blank
    them all.

    Failure handling mirrors the calendar coordinator exactly (research
    D-15) rather than inventing a second pattern: a property that fails
    retains its last-good tasks, the surviving properties still deliver
    fresh data, and ``UpdateFailed`` is raised only when EVERY property
    failed. Isolation must not become silent success, so a total outage
    is still reported as a failure (FR-034).
    """

    default_minutes = DEFAULT_TASK_INTERVAL
    floor_minutes = MIN_TASK_INTERVAL

    def __init__(
        self,
        hass: HomeAssistant,
        client: HospitableApiClient,
        *,
        property_ids: list[str] | None = None,
        window_days: int = DEFAULT_TASK_WINDOW_DAYS,
        config_entry: ConfigEntry | None = None,
        interval_minutes: int | None = None,
    ) -> None:
        """Initialize the tasks coordinator with its property fan-out.

        Args:
            hass: The Home Assistant instance.
            client: The GET-only API client. Annotated as the base
                client so a write call site here is a type error rather
                than a runtime surprise (research D-01 gate 1).
            property_ids: Properties to fan out across.
            window_days: Forward window in days, applied from today.
            config_entry: The owning config entry.
            interval_minutes: Requested cadence, clamped to the floor.
        """
        super().__init__(
            hass,
            name=f"{DOMAIN} tasks",
            config_entry=config_entry,
            interval_minutes=interval_minutes,
        )
        self._client: HospitableApiClient = client
        self._property_ids = list(property_ids or [])
        self._window_days = window_days
        self._property_failures: dict[str, int] = {}

    def property_failure_count(self, property_id: str) -> int:
        """Return consecutive task fetch failures for one property.

        The count resets to zero on any successful fetch of that
        property, so a transient blip retains last-good data while a
        persistently failing property degrades on its own (D-15,
        FR-057).

        Args:
            property_id: The property to report on.

        Returns:
            The consecutive failure count.
        """
        return self._property_failures.get(property_id, 0)

    async def _fetch_data(self) -> dict[str, tuple[HospitableTask, ...]]:
        """Fetch each property's tasks with per-property isolation.

        Returns:
            Each property's tasks, keyed by property id.
        """
        today = dt_util.utcnow().date()
        end = today + timedelta(days=self._window_days)
        # Seed with the previous cycle so a property that fails this
        # cycle retains its last-good tasks rather than emptying.
        result: dict[str, tuple[HospitableTask, ...]] = dict(self.data or {})
        succeeded = False
        last_error: HospitableError | None = None
        for property_id in self._property_ids:
            try:
                tasks = await self._client.get_tasks(property_id, today, end)
            except HospitableError as exc:
                strikes = self._property_failures.get(property_id, 0) + 1
                self._property_failures[property_id] = strikes
                # Retaining last-good data must not make the failure
                # invisible: without this, a property whose sensors went
                # stale while its neighbours kept updating would leave no
                # trace to diagnose from.
                _LOGGER.debug(
                    "Hospitable task fetch failed for property %s "
                    "(%s consecutive); retaining last-known tasks: %s",
                    property_id,
                    strikes,
                    exc,
                )
                last_error = exc
                continue
            result[property_id] = tuple(tasks)
            self._property_failures[property_id] = 0
            succeeded = True
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
