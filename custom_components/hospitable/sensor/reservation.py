# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Reservation status enum sensor for Hospitable properties."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from custom_components.hospitable.api.models import HospitableReservation
from custom_components.hospitable.coordinator import HospitableReservationsCoordinator
from custom_components.hospitable.entity import (
    HospitableEntity,
    build_device_identifier,
    build_suggested_object_id,
    build_unique_id,
)
from custom_components.hospitable.sensor.helpers import reservation_summary
from custom_components.hospitable.services.occupancy import (
    derive_occupancy_once,
    parse_scheduled_instant,
)
from custom_components.hospitable.services.selection import (
    is_forthcoming,
    select_reservation,
)
from custom_components.hospitable.services.status import StatusMapper

NO_RESERVATION = "no_reservation"

RESERVATION_STATUS_OPTIONS = [
    NO_RESERVATION,
    "awaiting_checkin",
    "occupied",
    "checked_out",
    "pending_request",
    "checkpoint",
    "cancelled",
    "not_accepted",
    "unknown",
]

_ATTRIBUTE_KEYS = (
    "reservation_id",
    "arrival_date",
    "departure_date",
    "nights",
    "scheduled_checkin",
    "scheduled_checkout",
    "guests_total",
    "guests_adults",
    "guests_children",
    "guests_infants",
    "guests_pets",
    "booking_channel",
    "channel_confirmation",
    "booking_date",
    "stay_type",
    "upcoming_reservations",
)


class HospitableReservationSensor(HospitableEntity, SensorEntity):
    """Enum sensor exposing the current reservation status per property."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "reservation_status"
    _attr_options = RESERVATION_STATUS_OPTIONS

    def __init__(
        self,
        coordinator: HospitableReservationsCoordinator,
        *,
        account_namespace: str,
        property_id: str,
        property_name: str,
    ) -> None:
        """Initialize one reservation status sensor for a property."""
        super().__init__(coordinator)
        self._property_id = property_id
        self._status_mapper = StatusMapper()
        self._occupancy_warned: set[tuple[str, str]] = set()
        self._attr_unique_id = build_unique_id(
            account_namespace, property_id, "reservation_status"
        )
        self._attr_suggested_object_id = build_suggested_object_id(
            property_name, "reservation_status"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={build_device_identifier(account_namespace, property_id)}
        )

    def _property_reservations(self) -> list[HospitableReservation]:
        """Return this property's reservations from coordinator data."""
        data = self.coordinator.data or []
        return [
            reservation
            for reservation in data
            if reservation.property_id == self._property_id
        ]

    def _compute_state(self, now: datetime) -> str:
        """Compute the enum state at instant ``now``."""
        selected, _ = select_reservation(self._property_reservations(), now)
        if selected is None:
            return NO_RESERVATION
        occupancy = derive_occupancy_once(selected, now, self._occupancy_warned)
        return self._status_mapper.map(selected.status_category, occupancy.state)

    @property
    def native_value(self) -> str:
        """Return the current enum state."""
        return self._compute_state(dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the reservation attribute set defined by the contract."""
        now = dt_util.utcnow()
        selected, upcoming = select_reservation(self._property_reservations(), now)
        if selected is None:
            return {key: None for key in _ATTRIBUTE_KEYS} | {
                "upcoming_reservations": []
            }
        guests = selected.guests
        return {
            "reservation_id": selected.reservation_id,
            "arrival_date": selected.arrival_date,
            "departure_date": selected.departure_date,
            "nights": selected.nights,
            "scheduled_checkin": parse_scheduled_instant(
                selected.scheduled_checkin_raw
            ),
            "scheduled_checkout": parse_scheduled_instant(
                selected.scheduled_checkout_raw
            ),
            "guests_total": guests.total,
            "guests_adults": guests.adults,
            "guests_children": guests.children,
            "guests_infants": guests.infants,
            "guests_pets": guests.pets,
            "booking_channel": selected.channel,
            "channel_confirmation": selected.channel_confirmation,
            "booking_date": selected.booking_date,
            "stay_type": selected.stay_type,
            "upcoming_reservations": [
                reservation_summary(reservation)
                for reservation in upcoming
                if is_forthcoming(reservation, now)
            ],
        }


def build_reservation_sensors(
    coordinator: HospitableReservationsCoordinator,
    account_namespace: str,
    property_names: dict[str, str],
) -> list[HospitableReservationSensor]:
    """Build exactly one reservation status sensor per property."""
    return [
        HospitableReservationSensor(
            coordinator,
            account_namespace=account_namespace,
            property_id=property_id,
            property_name=property_name,
        )
        for property_id, property_name in property_names.items()
    ]
