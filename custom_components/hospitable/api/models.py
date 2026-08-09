# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Frozen domain models for sanitized Hospitable payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from custom_components.hospitable.api.exceptions import HospitableResponseError


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

    max_guests: int | None
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
            payload.get("max", payload.get("max_guests")),
            payload.get("bedrooms"),
            payload.get("beds"),
            float(bathrooms) if bathrooms is not None else None,
        )


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
            payload.get("checkin"),
            payload.get("checkout"),
            PropertyCapacity.from_api(payload.get("capacity")),
            payload.get("currency"),
            bool(payload.get("listed", False)),
            payload.get("property_type"),
            listings,
            "listings" in payload,
        )


@dataclass(frozen=True)
class GuestBreakdown:
    """Reservation guest counts without identities."""

    total: int
    adults: int
    children: int
    infants: int
    pets: int

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> GuestBreakdown:
        """Build guest counts from API data."""
        if not isinstance(payload, dict):
            payload = {}
        return cls(
            int(payload.get("total", 0)),
            int(payload.get("adult_count", 0)),
            int(payload.get("child_count", 0)),
            int(payload.get("infant_count", 0)),
            int(payload.get("pet_count", 0)),
        )


@dataclass(frozen=True)
class HospitableReservation:
    """Sanitized reservation model."""

    reservation_id: str
    property_id: str
    status_category: str
    raw_status: str | None
    arrival_date: date
    departure_date: date
    scheduled_checkin_raw: str | None
    scheduled_checkout_raw: str | None
    guests: GuestBreakdown
    nights: int | None
    channel: str | None
    channel_confirmation: str | None
    booking_date: datetime | None
    stay_type: str | None

    @classmethod
    def from_api(cls, payload: dict[str, Any]) -> HospitableReservation:
        """Build a reservation and drop guest identity fields."""
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
        status = status_payload.get("current")
        return cls(
            str(payload.get("id", "")),
            property_id,
            str(status),
            payload.get("status"),
            arrival.date(),
            departure.date(),
            payload.get("check_in"),
            payload.get("check_out"),
            GuestBreakdown.from_api(payload.get("guests", {})),
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
