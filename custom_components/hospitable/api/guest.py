# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Guest models for the Hospitable API.

Two different things share the word "guest" upstream and are kept apart
here deliberately. ``GuestBreakdown`` is the NUMERIC occupancy count on
every reservation. ``HospitableGuest`` is singular guest IDENTITY, which
arrives only with ``include=guest`` and is PII throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
class HospitableGuest:
    """Guest identity from the ``guest`` include (FR-039).

    ``profile_picture`` is deliberately NOT a field. It has no permitted
    exposure surface anywhere — not entity attributes (FR-039d), not
    service responses (FR-047), not logs or diagnostics (FR-041,
    FR-042) — so it is never read into the model at all. A field that
    does not exist cannot leak onto a surface someone forgets to guard,
    which is exactly the failure mode FR-046 names.

    Every remaining field is PII. ``email`` and ``phone_numbers`` are
    surfaced only where the guest-contact opt-in is enabled, and each
    surface enforces that for itself.
    """

    guest_id: str
    first_name: str | None
    last_name: str | None
    email: str | None
    phone_numbers: list[str]
    location: str | None
    language: str | None

    @classmethod
    def from_api(cls, payload: Any) -> HospitableGuest | None:
        """Build a guest, tolerating a missing surname and a null guest.

        A missing ``last_name`` is not hypothetical: one live
        reservation in twenty-nine had none (FR-039b). A ``null`` guest
        means no guest data is available and yields no guest rather than
        an error (FR-040).

        Args:
            payload: Raw ``guest`` value of any shape.

        Returns:
            The parsed guest, or ``None`` when there is no guest object.
        """
        if not isinstance(payload, dict):
            return None
        raw_numbers = payload.get("phone_numbers")
        numbers = (
            [str(number) for number in raw_numbers if number is not None]
            if isinstance(raw_numbers, list)
            else []
        )
        return cls(
            str(payload.get("id", "")),
            _optional_text(payload.get("first_name")),
            _optional_text(payload.get("last_name")),
            _optional_text(payload.get("email")),
            numbers,
            _optional_text(payload.get("location")),
            _optional_text(payload.get("language")),
        )


def _optional_text(value: Any) -> str | None:
    """Return a value as text, mapping absent or null to ``None``.

    Args:
        value: Raw upstream value.

    Returns:
        The value as a string, or ``None`` when it is absent or null.
    """
    return None if value is None else str(value)
