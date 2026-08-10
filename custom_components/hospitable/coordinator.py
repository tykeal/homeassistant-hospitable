# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Data coordinator classes for Hospitable polling domains."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.hospitable.api.client import HospitableApiClient
from custom_components.hospitable.api.exceptions import (
    HospitableError,
    HospitableIncludeMissingError,
)
from custom_components.hospitable.api.models import (
    HospitableProperty,
    HospitableReservation,
)
from custom_components.hospitable.const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class _HospitableCoordinator[DataT](DataUpdateCoordinator[DataT]):
    """Base ``DataUpdateCoordinator`` with a consecutive-failure counter.

    The counter backs the three-strike availability policy required by
    FR-057, which Home Assistant's stock ``CoordinatorEntity.available``
    cannot express because it reports unavailable after a single failed
    poll.
    """

    default_minutes: int
    floor_minutes: int

    def __init__(
        self,
        hass: HomeAssistant,
        *,
        name: str,
        config_entry: ConfigEntry | None = None,
        interval_minutes: int | None = None,
    ) -> None:
        """Initialize the coordinator with a bounded update interval."""
        minutes = max(self.floor_minutes, interval_minutes or self.default_minutes)
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            config_entry=config_entry,
            update_interval=timedelta(minutes=minutes),
        )
        self.consecutive_failures = 0

    async def _async_update_data(self) -> DataT:
        """Fetch fresh data and maintain the consecutive-failure counter."""
        try:
            data = await self._fetch_data()
        except Exception:
            self.consecutive_failures += 1
            raise
        self.consecutive_failures = 0
        return data

    async def _fetch_data(self) -> DataT:
        """Return fresh domain data for this coordinator."""
        raise NotImplementedError


class HospitableReservationsCoordinator(
    _HospitableCoordinator[list[HospitableReservation]]
):
    """Coordinator for reservation data across the configured window."""

    default_minutes = 5
    floor_minutes = 1

    def __init__(
        self,
        hass: HomeAssistant,
        client: HospitableApiClient,
        *,
        property_ids: list[str],
        lookback_days: int,
        lookahead_days: int,
        config_entry: ConfigEntry | None = None,
        interval_minutes: int | None = None,
    ) -> None:
        """Initialize the reservations coordinator with its query window."""
        super().__init__(
            hass,
            name=f"{DOMAIN} reservations",
            config_entry=config_entry,
            interval_minutes=interval_minutes,
        )
        self._client = client
        self._property_ids = list(property_ids)
        self._lookback_days = lookback_days
        self._lookahead_days = lookahead_days
        self._logged_include_missing = False

    async def _fetch_data(self) -> list[HospitableReservation]:
        """Fetch reservations, degrading gracefully on a missing include."""
        today = dt_util.utcnow().date()
        start = today - timedelta(days=self._lookback_days)
        end = today + timedelta(days=self._lookahead_days)
        try:
            return await self._client.get_reservations(self._property_ids, start, end)
        except HospitableIncludeMissingError:
            if not self._logged_include_missing:
                self._logged_include_missing = True
                _LOGGER.warning(
                    "Reservations include=properties was not honored; "
                    "retaining last-known reservation data"
                )
            return self.data if self.data is not None else []
        except HospitableError as exc:
            raise UpdateFailed(str(exc)) from exc


class HospitablePropertiesCoordinator(
    _HospitableCoordinator[dict[str, HospitableProperty]]
):
    """Coordinator for property data keyed by property identifier."""

    default_minutes = 60
    floor_minutes = 15

    def __init__(
        self,
        hass: HomeAssistant,
        client: HospitableApiClient,
        *,
        config_entry: ConfigEntry | None = None,
        interval_minutes: int | None = None,
    ) -> None:
        """Initialize the properties coordinator."""
        super().__init__(
            hass,
            name=f"{DOMAIN} properties",
            config_entry=config_entry,
            interval_minutes=interval_minutes,
        )
        self._client = client

    async def _fetch_data(self) -> dict[str, HospitableProperty]:
        """Fetch every property keyed by immutable identifier."""
        try:
            return await self._client.get_properties()
        except HospitableError as exc:
            raise UpdateFailed(str(exc)) from exc


class HospitableCalendarCoordinator(_HospitableCoordinator[dict[str, Any]]):
    """Coordinator for calendar data, wired by US7."""

    default_minutes = 60
    floor_minutes = 15

    def __init__(
        self,
        hass: HomeAssistant,
        client: HospitableApiClient,
        *,
        config_entry: ConfigEntry | None = None,
        interval_minutes: int | None = None,
    ) -> None:
        """Initialize the calendar coordinator."""
        super().__init__(
            hass,
            name=f"{DOMAIN} calendar",
            config_entry=config_entry,
            interval_minutes=interval_minutes,
        )
        self._client = client

    async def _fetch_data(self) -> dict[str, Any]:
        """Return calendar data once US7 wires the per-property fetch."""
        return {}
