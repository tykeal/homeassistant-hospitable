# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Reservation status enum sensor for Hospitable properties."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from custom_components.hospitable.api.models import (
    HospitableGuest,
    HospitableReservation,
)
from custom_components.hospitable.const import (
    CONF_GUEST_CONTACT_DETAILS,
    DEFAULT_GUEST_CONTACT_DETAILS,
)
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

# Guest identity exposed by default (FR-039a). ``reservation_id``
# already carries the reservation UUID the service target pattern needs
# (FR-044), so no second key duplicates it.
GUEST_ATTRIBUTE_KEYS = (
    "guest_first_name",
    "guest_last_name",
    "guest_location",
    "guest_language",
)
# Exposed ONLY behind the guest-contact opt-in, which defaults OFF
# (FR-039c, FR-038b). This gate governs the ENTITY ATTRIBUTE surface
# alone; the service-response surface has its own control in
# ``actions/response.py`` (FR-046).
GUEST_CONTACT_ATTRIBUTE_KEYS = (
    "guest_email",
    "guest_phone_numbers",
)

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
    "status_sub_category",
    "upcoming_reservations",
    *GUEST_ATTRIBUTE_KEYS,
)


class HospitableReservationSensor(HospitableEntity, SensorEntity):
    """Enum sensor exposing the current reservation status per property."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "reservation_status"
    _attr_options = RESERVATION_STATUS_OPTIONS
    # EVERY guest attribute is unrecorded, opt-in ones included, so guest
    # data lives in entity state memory only and never reaches the
    # recorder database or a backup (FR-039e). This is a CLASS attribute
    # and cannot know whether the option is on, so it names all six.
    # ``reservation_id`` is deliberately absent: it is operational, not
    # personal, and automations need its history.
    _unrecorded_attributes = frozenset(
        {*GUEST_ATTRIBUTE_KEYS, *GUEST_CONTACT_ATTRIBUTE_KEYS}
    )

    def __init__(
        self,
        coordinator: HospitableReservationsCoordinator,
        *,
        properties_coordinator: HospitablePropertiesCoordinator | None = None,
        account_namespace: str,
        property_id: str,
        property_name: str,
    ) -> None:
        """Initialize one reservation status sensor for a property."""
        super().__init__(coordinator)
        self._property_id = property_id
        self._status_mapper = StatusMapper()
        self._occupancy_warned: set[tuple[str, str]] = set()
        if properties_coordinator is not None:
            self._presence_coordinator = properties_coordinator
            self._presence_property_id = property_id
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
    def _guest_contact_enabled(self) -> bool:
        """Return whether the guest-contact opt-in is enabled.

        Read from the coordinator's config entry rather than captured at
        construction, so the value can never drift from the entry. The
        default is OFF by requirement (FR-038b), which is also what an
        absent entry yields.
        """
        entry = getattr(self.coordinator, "config_entry", None)
        options = getattr(entry, "options", None) or {}
        return bool(
            options.get(CONF_GUEST_CONTACT_DETAILS, DEFAULT_GUEST_CONTACT_DETAILS)
        )

    def _guest_attributes(self, guest: HospitableGuest | None) -> dict[str, Any]:
        """Return the guest attributes for one reservation's guest.

        ``profile_picture`` is not readable here at all: the model does
        not carry it (FR-039d). The default keys are always present,
        carrying ``None`` when there is no guest, so a template never
        raises on a missing key; the OPT-IN keys are not created at all
        when the option is off (FR-038b).

        Args:
            guest: The reservation's guest, or ``None``.

        Returns:
            The guest attribute mapping.
        """
        attributes: dict[str, Any] = {
            "guest_first_name": guest.first_name if guest else None,
            "guest_last_name": guest.last_name if guest else None,
            "guest_location": guest.location if guest else None,
            "guest_language": guest.language if guest else None,
        }
        if self._guest_contact_enabled:
            attributes["guest_email"] = guest.email if guest else None
            attributes["guest_phone_numbers"] = (
                list(guest.phone_numbers) if guest and guest.phone_numbers else None
            )
        return attributes

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the reservation attribute set defined by the contract."""
        now = dt_util.utcnow()
        selected, upcoming = select_reservation(self._property_reservations(), now)
        if selected is None:
            return (
                {key: None for key in _ATTRIBUTE_KEYS}
                | {"upcoming_reservations": []}
                | self._guest_attributes(None)
            )
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
            "status_sub_category": selected.status_sub_category,
            "upcoming_reservations": [
                reservation_summary(reservation)
                for reservation in upcoming
                if is_forthcoming(reservation, now)
            ],
            **self._guest_attributes(selected.guest),
        }


def build_reservation_sensors(
    coordinator: HospitableReservationsCoordinator,
    account_namespace: str,
    property_names: dict[str, str],
    properties_coordinator: HospitablePropertiesCoordinator | None = None,
) -> list[HospitableReservationSensor]:
    """Build exactly one reservation status sensor per property."""
    return [
        HospitableReservationSensor(
            coordinator,
            properties_coordinator=properties_coordinator,
            account_namespace=account_namespace,
            property_id=property_id,
            property_name=property_name,
        )
        for property_id, property_name in property_names.items()
    ]
