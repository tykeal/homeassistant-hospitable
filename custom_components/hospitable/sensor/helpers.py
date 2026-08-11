# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for Hospitable sensor entities."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from custom_components.hospitable.api.models import HospitableReservation

_ZERO_DECIMAL_CURRENCIES = frozenset(
    {
        "BIF",
        "CLP",
        "DJF",
        "GNF",
        "ISK",
        "JPY",
        "KMF",
        "KRW",
        "PYG",
        "RWF",
        "UGX",
        "VND",
        "VUV",
        "XAF",
        "XOF",
        "XPF",
    }
)
_THREE_DECIMAL_CURRENCIES = frozenset({"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"})


def minor_units_to_float(minor_units: int | None, currency: str | None) -> float | None:
    """Convert integer minor currency units to a major-unit float.

    This is the single minor-unit conversion point for every sensor
    (US3, US4 and US7 reuse it). The exponent follows ISO 4217 for the
    zero- and three-decimal currencies, defaulting to two decimals.
    """
    if minor_units is None:
        return None
    code = (currency or "").upper()
    if code in _ZERO_DECIMAL_CURRENCIES:
        exponent = 0
    elif code in _THREE_DECIMAL_CURRENCIES:
        exponent = 3
    else:
        exponent = 2
    return float(Decimal(minor_units) / (Decimal(10) ** exponent))


def reservation_summary(reservation: HospitableReservation) -> dict[str, Any]:
    """Return a non-personal summary entry for an upcoming reservation."""
    return {
        "reservation_id": reservation.reservation_id,
        "arrival_date": reservation.arrival_date,
        "departure_date": reservation.departure_date,
        "status_category": reservation.status_category,
        "stay_type": reservation.stay_type,
    }
