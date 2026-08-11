# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Property detail sensors for Hospitable properties.

These are the User Story 3 entities: the next-arrival and next-departure
timestamp sensors, the upcoming-reservation count, and the property_info
diagnostic sensor. The timestamp sensors preserve each reservation's own
offset-aware instant and report ``None`` rather than a stale value once
that instant is in the past, because a stale timestamp would make an
automation comparing against ``now()`` fire on a departure that already
happened (US3 acceptance scenario 2, FR-051).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from custom_components.hospitable.api.models import HospitableProperty
from custom_components.hospitable.coordinator import (
    HospitablePropertiesCoordinator,
    HospitableReservationsCoordinator,
)
from custom_components.hospitable.entity import (
    HospitableEntity,
    build_device_identifier,
    build_suggested_object_id,
    build_unique_id,
)
from custom_components.hospitable.services.occupancy import parse_scheduled_instant
from custom_components.hospitable.services.selection import is_active, is_forthcoming

PROPERTY_INFO_ATTRIBUTES = (
    "address",
    "checkin_time",
    "checkout_time",
    "max_guests",
    "effective_timezone",
    "timezone_source",
    "listings",
    "listings_available",
)


def _soonest_future_instant(
    raw_values: list[str | None], now: datetime
) -> datetime | None:
    """Return the soonest offset-aware instant strictly after ``now``.

    Each raw value is parsed with :func:`parse_scheduled_instant`. A
    value that is missing, unparsable, or naive (lacking a UTC offset)
    is skipped rather than compared, because comparing a naive instant to
    the aware ``now`` would raise ``TypeError`` and the contract requires
    offset-aware scheduled instants.
    """
    future = []
    for raw in raw_values:
        instant = parse_scheduled_instant(raw)
        if instant is None or instant.tzinfo is None:
            continue
        if instant > now:
            future.append(instant)
    return min(future) if future else None


class _HospitablePropertyReservationEntity(HospitableEntity, SensorEntity):
    """Base for property sensors driven by reservation coordinator data."""

    _entity_key: str

    def __init__(
        self,
        coordinator: HospitableReservationsCoordinator,
        *,
        properties_coordinator: HospitablePropertiesCoordinator,
        account_namespace: str,
        property_id: str,
        property_name: str,
    ) -> None:
        """Initialize one reservation-derived property sensor."""
        super().__init__(coordinator)
        self._property_id = property_id
        self._presence_coordinator = properties_coordinator
        self._presence_property_id = property_id
        self._attr_unique_id = build_unique_id(
            account_namespace, property_id, self._entity_key
        )
        self._attr_suggested_object_id = build_suggested_object_id(
            property_name, self._entity_key
        )
        self._attr_device_info = DeviceInfo(
            identifiers={build_device_identifier(account_namespace, property_id)}
        )

    def _property_reservations(self) -> list[Any]:
        """Return this property's reservations from coordinator data."""
        data = self.coordinator.data or []
        return [
            reservation
            for reservation in data
            if reservation.property_id == self._property_id
        ]


class HospitableNextArrivalSensor(_HospitablePropertyReservationEntity):
    """Timestamp sensor for the next forthcoming arrival instant."""

    _entity_key = "next_arrival"
    _attr_translation_key = "next_arrival"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Return the soonest future check-in instant, or ``None``."""
        now = dt_util.utcnow()
        return _soonest_future_instant(
            [
                reservation.scheduled_checkin_raw
                for reservation in self._property_reservations()
                if is_active(reservation)
            ],
            now,
        )


class HospitableNextDepartureSensor(_HospitablePropertyReservationEntity):
    """Timestamp sensor for the next forthcoming departure instant."""

    _entity_key = "next_departure"
    _attr_translation_key = "next_departure"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Return the soonest future check-out instant, or ``None``."""
        now = dt_util.utcnow()
        return _soonest_future_instant(
            [
                reservation.scheduled_checkout_raw
                for reservation in self._property_reservations()
                if is_active(reservation)
            ],
            now,
        )


class HospitableUpcomingReservationsSensor(_HospitablePropertyReservationEntity):
    """Measurement sensor counting forthcoming reservations."""

    _entity_key = "upcoming_reservations"
    _attr_translation_key = "upcoming_reservations"
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> int:
        """Return the count of forthcoming reservations for this property."""
        now = dt_util.utcnow()
        return sum(
            1
            for reservation in self._property_reservations()
            if is_forthcoming(reservation, now)
        )


class HospitablePropertyInfoSensor(HospitableEntity, SensorEntity):
    """Diagnostic sensor exposing sanitized property information."""

    _attr_translation_key = "property_info"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: HospitablePropertiesCoordinator,
        *,
        account_namespace: str,
        property_id: str,
        property_name: str,
        effective_timezone: str,
        timezone_source: str,
    ) -> None:
        """Initialize one property_info sensor bound to a property."""
        super().__init__(coordinator)
        self._property_id = property_id
        self._effective_timezone = effective_timezone
        self._timezone_source = timezone_source
        self._presence_coordinator = coordinator
        self._presence_property_id = property_id
        self._attr_unique_id = build_unique_id(
            account_namespace, property_id, "property_info"
        )
        self._attr_suggested_object_id = build_suggested_object_id(
            property_name, "property_info"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={build_device_identifier(account_namespace, property_id)}
        )

    def _property(self) -> HospitableProperty | None:
        """Return this property's current model, or ``None`` if gone."""
        data = self.coordinator.data or {}
        return data.get(self._property_id)

    @property
    def native_value(self) -> str | None:
        """Return the property's current display name."""
        property_model = self._property()
        return property_model.name if property_model is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return exactly the eight property_info contract attributes."""
        property_model = self._property()
        if property_model is None:
            return {
                "address": None,
                "checkin_time": None,
                "checkout_time": None,
                "max_guests": None,
                "effective_timezone": self._effective_timezone,
                "timezone_source": self._timezone_source,
                "listings": [],
                "listings_available": False,
            }
        capacity = property_model.capacity
        return {
            "address": property_model.address.display,
            "checkin_time": property_model.checkin,
            "checkout_time": property_model.checkout,
            "max_guests": capacity.max if capacity is not None else None,
            "effective_timezone": self._effective_timezone,
            "timezone_source": self._timezone_source,
            "listings": [
                {"platform": listing.platform, "platform_id": listing.platform_id}
                for listing in property_model.listings
            ],
            "listings_available": property_model.listings_available,
        }


def build_property_sensors(
    reservations_coordinator: HospitableReservationsCoordinator,
    properties_coordinator: HospitablePropertiesCoordinator,
    account_namespace: str,
    property_names: dict[str, str],
    property_timezones: dict[str, tuple[str, str]],
) -> list[HospitableEntity]:
    """Build the four detail sensors for each configured property."""
    sensors: list[HospitableEntity] = []
    for property_id, property_name in property_names.items():
        sensors.append(
            HospitableNextArrivalSensor(
                reservations_coordinator,
                properties_coordinator=properties_coordinator,
                account_namespace=account_namespace,
                property_id=property_id,
                property_name=property_name,
            )
        )
        sensors.append(
            HospitableNextDepartureSensor(
                reservations_coordinator,
                properties_coordinator=properties_coordinator,
                account_namespace=account_namespace,
                property_id=property_id,
                property_name=property_name,
            )
        )
        sensors.append(
            HospitableUpcomingReservationsSensor(
                reservations_coordinator,
                properties_coordinator=properties_coordinator,
                account_namespace=account_namespace,
                property_id=property_id,
                property_name=property_name,
            )
        )
        effective_timezone, timezone_source = property_timezones[property_id]
        sensors.append(
            HospitablePropertyInfoSensor(
                properties_coordinator,
                account_namespace=account_namespace,
                property_id=property_id,
                property_name=property_name,
                effective_timezone=effective_timezone,
                timezone_source=timezone_source,
            )
        )
    return sensors
