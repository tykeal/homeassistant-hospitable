# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Frozen domain models for sanitized Hospitable payloads."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from custom_components.hospitable.api.exceptions import HospitableResponseError
from custom_components.hospitable.api.guest import GuestBreakdown, HospitableGuest
from custom_components.hospitable.api.task_model import (
    HospitableTask,
    TaskTypeEntry,
    TaskVocabularies,
)


@dataclass(frozen=True)
class PropertyAddress:
    """Sanitized property address."""

    city: str | None
    state: str | None
    country: str | None
    display: str | None

    @classmethod
    def from_api(cls, payload: dict[str, Any] | None) -> PropertyAddress:
        """Build an address from API data."""
        if not isinstance(payload, dict):
            payload = {}
        return cls(
            payload.get("city"),
            payload.get("state"),
            payload.get("country"),
            payload.get("display"),
        )


@dataclass(frozen=True)
class PropertyCapacity:
    """Optional property capacity details."""

    max: int | None
    bedrooms: int | None
    beds: int | None
    bathrooms: float | None

    @classmethod
    def from_api(cls, payload: dict[str, Any] | None) -> PropertyCapacity | None:
        """Build capacity from API data, degrading absent keys to None."""
        if not isinstance(payload, dict):
            return None
        bathrooms = payload.get("bathrooms")
        return cls(
            payload.get("max"),
            payload.get("bedrooms"),
            payload.get("beds"),
            float(bathrooms) if bathrooms is not None else None,
        )


PROPERTY_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _property_time(value: Any) -> str | None:
    """Return a property wall-clock HH:MM string, or None if malformed."""
    if isinstance(value, str) and PROPERTY_TIME_RE.fullmatch(value):
        return value
    return None


@dataclass(frozen=True)
class HospitableListing:
    """Non-personal sales-channel listing reference."""

    platform: str
    platform_id: str

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> HospitableListing:
        """Build a listing from API data."""
        return cls(
            str(payload.get("platform", "")), str(payload.get("platform_id", ""))
        )


@dataclass(frozen=True)
class HospitableProperty:
    """Sanitized Hospitable property model without fixed-offset timezone."""

    property_id: str
    name: str
    public_name: str | None
    address: PropertyAddress
    checkin: str | None
    checkout: str | None
    capacity: PropertyCapacity | None
    currency: str | None
    listed: bool
    property_type: str | None
    listings: tuple[HospitableListing, ...]
    listings_available: bool

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> HospitableProperty:
        """Build a property from API data."""
        try:
            property_id = str(payload["id"])
            name = str(payload["name"])
        except KeyError as exc:
            raise HospitableResponseError("Property missing required key") from exc
        raw_listings = payload.get("listings", [])
        if not isinstance(raw_listings, list):
            raw_listings = []
        listings = tuple(
            HospitableListing.from_api(item)
            for item in raw_listings
            if isinstance(item, dict)
        )
        return cls(
            property_id,
            name,
            payload.get("public_name"),
            PropertyAddress.from_api(payload.get("address")),
            _property_time(payload.get("checkin")),
            _property_time(payload.get("checkout")),
            PropertyCapacity.from_api(payload.get("capacity")),
            payload.get("currency"),
            bool(payload.get("listed", False)),
            payload.get("property_type"),
            listings,
            "listings" in payload,
        )


@dataclass(frozen=True)
class HospitableReservation:
    """Sanitized reservation model."""

    reservation_id: str
    property_id: str
    status_category: str
    status_sub_category: str | None
    raw_status: str | None
    arrival_date: date
    departure_date: date
    scheduled_checkin_raw: str | None
    scheduled_checkout_raw: str | None
    guests: GuestBreakdown
    # NOT the same thing as ``guests`` above: that is the NUMERIC
    # occupancy breakdown, this is singular guest IDENTITY (FR-039).
    guest: HospitableGuest | None
    nights: int | None
    channel: str | None
    channel_confirmation: str | None
    booking_date: datetime | None
    stay_type: str | None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> HospitableReservation:
        """Build a reservation, parsing guest identity when present."""
        try:
            properties = payload["properties"]
            property_id = str(properties[0]["id"])
            arrival = datetime.fromisoformat(str(payload["arrival_date"]))
            departure = datetime.fromisoformat(str(payload["departure_date"]))
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise HospitableResponseError("Reservation missing required key") from exc
        booking_raw = payload.get("booking_date")
        booking = (
            datetime.fromisoformat(booking_raw.replace("Z", "+00:00"))
            if isinstance(booking_raw, str)
            else None
        )
        status_payload = payload.get("reservation_status")
        if not isinstance(status_payload, dict):
            raise HospitableResponseError("Reservation status is malformed")
        current = status_payload.get("current")
        if not isinstance(current, dict):
            raise HospitableResponseError("Reservation status current is malformed")
        category = current.get("category")
        if not isinstance(category, str) or not category:
            raise HospitableResponseError("Reservation status category is malformed")
        status_category = category
        sub_category = current.get("sub_category")
        status_sub_category = str(sub_category) if sub_category is not None else None
        return cls(
            str(payload.get("id", "")),
            property_id,
            status_category,
            status_sub_category,
            payload.get("status"),
            arrival.date(),
            departure.date(),
            payload.get("check_in"),
            payload.get("check_out"),
            GuestBreakdown.from_api(payload.get("guests", {})),
            HospitableGuest.from_api(payload.get("guest")),
            payload.get("nights"),
            payload.get("platform"),
            payload.get("platform_id"),
            booking,
            payload.get("stay_type"),
        )


@dataclass(frozen=True)
class HospitableAccount:
    """Account identifier model with personal fields omitted."""

    account_id: str

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> HospitableAccount:
        """Build an account from a /user response."""
        return cls(str(payload["data"]["id"]))


AVAILABILITY_AVAILABLE = "available"
AVAILABILITY_BOOKED = "booked"
AVAILABILITY_UNKNOWN = "unknown"


def _map_availability(status: dict[str, Any]) -> str:
    """Map a calendar day's status object to an availability state.

    ``status.available`` is the authoritative signal. ``available: true``
    is ``available``. ``available: false`` only claims ``booked`` when the
    reason is the confirmed ``RESERVED`` value; any other unavailable
    reason (for example a host block) maps to the honest ``unknown``
    rather than asserting a guest booking that may not exist (FR-058).
    """
    available = status.get("available")
    reason = str(status.get("reason") or "")
    if available is True:
        return AVAILABILITY_AVAILABLE
    if available is False and reason.upper() == "RESERVED":
        return AVAILABILITY_BOOKED
    return AVAILABILITY_UNKNOWN


def _coerce_int(value: Any) -> int | None:
    """Return an integer only for an int or an integral float.

    The calendar model never carries floats, and the confirmed API sends
    integer-valued minor units. A non-integral float would be a contract
    violation, so it degrades to ``None`` rather than silently truncating
    to a wrong value (FR-060). ``bool`` is rejected because it is an int
    subclass that never represents a currency amount or a stay length.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


@dataclass(frozen=True)
class HospitableCalendarDay:
    """One aggregate calendar day for a property.

    Monetary values are held only as integer minor currency units
    accompanied by a currency code; the model never carries a float. The
    single minor-unit-to-float conversion happens later, in the sensor
    layer (FR-060).
    """

    date: str
    availability: str
    price_minor_units: int | None
    currency: str | None
    min_stay: int | None
    closed_for_checkin: bool | None
    closed_for_checkout: bool | None
    note: str | None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> HospitableCalendarDay:
        """Build a calendar day, degrading absent fields to ``None``."""
        status = payload.get("status")
        if not isinstance(status, dict):
            status = {}
        price = payload.get("price")
        if isinstance(price, dict):
            price_minor_units = _coerce_int(price.get("amount"))
            raw_currency = price.get("currency")
            currency = raw_currency if isinstance(raw_currency, str) else None
        else:
            price_minor_units = None
            currency = None
        note = payload.get("note")
        return cls(
            str(payload.get("date", "")),
            _map_availability(status),
            price_minor_units,
            currency,
            _coerce_int(payload.get("min_stay")),
            payload.get("closed_for_checkin")
            if isinstance(payload.get("closed_for_checkin"), bool)
            else None,
            payload.get("closed_for_checkout")
            if isinstance(payload.get("closed_for_checkout"), bool)
            else None,
            note if isinstance(note, str) else None,
        )


@dataclass(frozen=True)
class HospitablePropertyCalendar:
    """A property's aggregate forward calendar across all sales channels.

    The response ``listing_id`` and ``provider`` are cosmetic metadata
    describing an aggregate across every channel, not a scope selector, so
    they are intentionally not carried on this model (FR-058).
    """

    property_id: str
    start_date: str
    end_date: str
    days: tuple[HospitableCalendarDay, ...]

    @classmethod
    def from_api(
        cls, property_id: str, payload: dict[str, Any]
    ) -> HospitablePropertyCalendar:
        """Build a calendar from the response ``data`` object."""
        if not isinstance(payload, dict):
            payload = {}
        raw_days = payload.get("days", [])
        if not isinstance(raw_days, list):
            raw_days = []
        days = tuple(
            HospitableCalendarDay.from_api(item)
            for item in raw_days
            if isinstance(item, dict)
        )
        return cls(
            str(property_id),
            str(payload.get("start_date", "")),
            str(payload.get("end_date", "")),
            days,
        )


@dataclass(frozen=True)
class HospitableMessage:
    """One message in a reservation's conversation thread.

    ``sender`` is retained as the OPAQUE upstream object because the
    reply-state derivation needs to see whatever upstream sends. It is
    never logged, never written to diagnostics, and never returned in a
    service response: the response chokepoint in
    ``actions/response.py`` drops it and keeps only ``sender_type`` and
    ``sender_role`` (FR-047a).
    """

    message_id: int | None
    platform: str | None
    conversation_id: str | None
    body: str | None
    content_type: str | None
    sender_type: str | None
    sender_role: str | None
    sender: dict[str, Any] | None
    created_at: str | None
    attachments: tuple[dict[str, Any], ...]
    source: str | None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> HospitableMessage:
        """Build a message from one item of the thread ``data`` array.

        Nothing here is required. A thread is read-only reference data,
        so a single odd item must not turn the whole call into an error.

        Args:
            payload: One message object.

        Returns:
            The parsed message.
        """
        raw_id = payload.get("id")
        raw_sender = payload.get("sender")
        raw_attachments = payload.get("attachments")
        return cls(
            message_id=raw_id if isinstance(raw_id, int) else None,
            platform=_optional_str(payload.get("platform")),
            conversation_id=_optional_str(payload.get("conversation_id")),
            body=_optional_str(payload.get("body")),
            content_type=_optional_str(payload.get("content_type")),
            sender_type=_optional_str(payload.get("sender_type")),
            sender_role=_optional_str(payload.get("sender_role")),
            sender=raw_sender if isinstance(raw_sender, dict) else None,
            created_at=_optional_str(payload.get("created_at")),
            attachments=tuple(
                item for item in raw_attachments or () if isinstance(item, dict)
            )
            if isinstance(raw_attachments, list)
            else (),
            source=_optional_str(payload.get("source")),
        )


def _optional_str(value: Any) -> str | None:
    """Return a string value, or None when absent.

    Args:
        value: Raw value of any type.

    Returns:
        The value as a string, or None when it is None.
    """
    return None if value is None else str(value)


# ``HospitableTask`` and its vocabularies live in ``api.task_model``
# rather than here because this module is already at the project's
# file-size limit. They are re-exported so the documented
# ``api.models`` import path resolves for every model alike.
__all__ = [
    "GuestBreakdown",
    "HospitableGuest",
    "HospitableTask",
    "TaskTypeEntry",
    "TaskVocabularies",
]
