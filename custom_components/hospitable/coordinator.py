# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Data coordinator classes for Hospitable polling domains."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, NoReturn

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.hospitable.api.client import HospitableApiClient
from custom_components.hospitable.api.exceptions import (
    HospitableAuthError,
    HospitableError,
    HospitableForbiddenError,
    HospitableIncludeMissingError,
    HospitableScopeError,
)
from custom_components.hospitable.api.models import (
    HospitableProperty,
    HospitableReservation,
)
from custom_components.hospitable.const import CONF_ACCOUNT_NAMESPACE, DOMAIN
from custom_components.hospitable.services.lifecycle import note_disappearances

_LOGGER = logging.getLogger(__name__)

# A revoked or expired token, or a plan without Public API access, all
# surface as a rejected credential. The message names the cause and the
# concrete recovery action (FR-064).
AUTH_FAILED_MESSAGE = (
    "The Hospitable token was rejected. The token is invalid or expired, "
    "or the account lacks paid Public API access. Generate a replacement "
    "under Apps then API access and reconnect."
)
FORBIDDEN_MESSAGE = (
    "Hospitable refused access to requested data. Review the account plan "
    "and permissions, then reload the integration."
)
# Number of consecutive non-credential failures after which the entry
# escalates to a persistent-failure repair issue (FR-065).
PERSISTENT_FAILURE_THRESHOLD = 3


class HospitableDataUpdateCoordinator[DataT](DataUpdateCoordinator[DataT]):
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
        self._logged_scope_limitation = False

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

    def _account_id(self) -> str:
        """Return the account namespace backing this coordinator's entry."""
        if self.config_entry is None:
            return ""
        return str(self.config_entry.data.get(CONF_ACCOUNT_NAMESPACE, ""))

    def _log_scope_limitation_once(self, exc: HospitableError) -> None:
        """Log a scope-403 as a capability limitation exactly once (FR-038).

        A scope-403 means the credential cannot reach a capability; it is
        not an authentication failure, so it triggers neither reauth nor a
        repair issue. The affected data is simply omitted.
        """
        if self._logged_scope_limitation:
            return
        self._logged_scope_limitation = True
        _LOGGER.warning(
            "Hospitable capability is unavailable for this credential type "
            "on %s; the affected data will be omitted. No action is needed "
            "unless you expect this capability, in which case use a "
            "credential that grants it",
            exc.endpoint or self.name,
        )

    def _create_repair_issue(self, kind: str, translation_key: str) -> None:
        """Raise a persistent repair issue naming the affected account."""
        if self.config_entry is None:
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"{kind}_{self.config_entry.entry_id}",
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key=translation_key,
            translation_placeholders={"account": self._account_id()},
        )

    def _raise_for_api_error(self, exc: HospitableError) -> NoReturn:
        """Map a non-scope API error to its Home Assistant outcome.

        A 401 becomes ``ConfigEntryAuthFailed`` so Home Assistant starts a
        reauth flow; a non-scope 403 raises a repair issue; any other error
        that persists past the failure threshold also raises a repair issue.
        Every branch raises (FR-064, FR-065).
        """
        if isinstance(exc, HospitableAuthError):
            raise ConfigEntryAuthFailed(AUTH_FAILED_MESSAGE) from exc
        if isinstance(exc, HospitableForbiddenError):
            self._create_repair_issue("forbidden", "forbidden_access")
            raise UpdateFailed(FORBIDDEN_MESSAGE) from exc
        if self.consecutive_failures + 1 >= PERSISTENT_FAILURE_THRESHOLD:
            self._create_repair_issue("persistent", "persistent_failure")
        raise UpdateFailed(str(exc)) from exc


class HospitableReservationsCoordinator(
    HospitableDataUpdateCoordinator[list[HospitableReservation]]
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
        except HospitableScopeError as exc:
            self._log_scope_limitation_once(exc)
            return self.data if self.data is not None else []
        except HospitableError as exc:
            self._raise_for_api_error(exc)


class HospitablePropertiesCoordinator(
    HospitableDataUpdateCoordinator[dict[str, HospitableProperty]]
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
        self.monitored_property_ids: set[str] = set()
        self._disappeared_warned: set[str] = set()

    async def _fetch_data(self) -> dict[str, HospitableProperty]:
        """Fetch every property keyed by immutable identifier.

        A monitored property that vanishes from the account is logged
        once and left to the entity availability policy, which reports it
        unavailable without deleting its registry entry (FR-056).
        """
        try:
            properties = await self._client.get_properties()
        except HospitableScopeError as exc:
            self._log_scope_limitation_once(exc)
            return self.data if self.data is not None else {}
        except HospitableError as exc:
            self._raise_for_api_error(exc)
        current_ids = set(properties)
        self._disappeared_warned &= current_ids
        note_disappearances(
            self.monitored_property_ids,
            current_ids,
            self._disappeared_warned,
            _LOGGER,
        )
        return properties


class HospitableCalendarCoordinator(HospitableDataUpdateCoordinator[dict[str, Any]]):
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
