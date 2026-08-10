# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Occupancy derivation from scheduled reservation instants.

Occupancy compares the reservation's own offset-aware ``check_in`` and
``check_out`` instants as pure moments in time. It deliberately consults
no timezone configuration (FR-074 narrowing): the offsets embedded in the
data are DST-aware and sufficient. There is no midnight fallback.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from custom_components.hospitable.api.models import HospitableReservation

_LOGGER = logging.getLogger(__name__)

STATE_AWAITING_CHECKIN = "awaiting_checkin"
STATE_OCCUPIED = "occupied"
STATE_CHECKED_OUT = "checked_out"
STATE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class OccupancyResult:
    """Occupancy outcome plus the degraded field when unknown."""

    state: str
    degraded_field: str | None = None


def parse_scheduled_instant(raw: str | None) -> datetime | None:
    """Parse an offset-aware scheduled instant, or return ``None``."""
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def derive_occupancy(
    reservation: HospitableReservation, now: datetime
) -> OccupancyResult:
    """Derive occupancy for ``reservation`` at instant ``now``.

    Degradation to ``unknown`` is scoped to the two boundary dates only:
    a missing or unparsable check-in on the arrival date, or check-out on
    the departure date, yields ``unknown`` with a warning naming the
    reservation and the field. Interior days never degrade.
    """
    checkin = parse_scheduled_instant(reservation.scheduled_checkin_raw)
    checkout = parse_scheduled_instant(reservation.scheduled_checkout_raw)
    reference = checkin or checkout
    if reference is None:
        _LOGGER.warning(
            "Reservation %s has no usable scheduled check_in or check_out time",
            reservation.reservation_id,
        )
        return OccupancyResult(STATE_UNKNOWN, "check_in")

    now_date = now.astimezone(reference.tzinfo).date()
    arrival = reservation.arrival_date
    departure = reservation.departure_date

    if now_date == arrival:
        if checkin is None:
            _LOGGER.warning(
                "Reservation %s is missing a usable scheduled check_in time "
                "on its arrival date",
                reservation.reservation_id,
            )
            return OccupancyResult(STATE_UNKNOWN, "check_in")
        if now < checkin:
            return OccupancyResult(STATE_AWAITING_CHECKIN)
        if checkout is not None and now >= checkout:
            return OccupancyResult(STATE_CHECKED_OUT)
        return OccupancyResult(STATE_OCCUPIED)

    if now_date == departure:
        if checkout is None:
            _LOGGER.warning(
                "Reservation %s is missing a usable scheduled check_out time "
                "on its departure date",
                reservation.reservation_id,
            )
            return OccupancyResult(STATE_UNKNOWN, "check_out")
        if now >= checkout:
            return OccupancyResult(STATE_CHECKED_OUT)
        if checkin is not None and now < checkin:
            return OccupancyResult(STATE_AWAITING_CHECKIN)
        return OccupancyResult(STATE_OCCUPIED)

    if now_date < arrival:
        return OccupancyResult(STATE_AWAITING_CHECKIN)
    if now_date > departure:
        return OccupancyResult(STATE_CHECKED_OUT)
    return OccupancyResult(STATE_OCCUPIED)
