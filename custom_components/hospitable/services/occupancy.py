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
from datetime import UTC, datetime

from custom_components.hospitable.api.models import HospitableReservation

_LOGGER = logging.getLogger(__name__)

STATE_AWAITING_CHECKIN = "awaiting_checkin"
STATE_OCCUPIED = "occupied"
STATE_CHECKED_OUT = "checked_out"
STATE_UNKNOWN = "unknown"

_FIELD_MESSAGES = {
    "check_in": (
        "Reservation %s is missing a usable scheduled check_in time on its arrival date"
    ),
    "check_out": (
        "Reservation %s is missing a usable scheduled check_out time "
        "on its departure date"
    ),
}


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


def classify_occupancy(
    reservation: HospitableReservation, now: datetime
) -> OccupancyResult:
    """Classify occupancy for ``reservation`` at instant ``now`` without logging.

    Degradation to ``unknown`` is scoped to the two boundary dates only:
    a missing or unparsable check-in on the arrival date, or check-out on
    the departure date, yields ``unknown`` naming the offending field.
    Interior days never degrade.

    When neither scheduled time parses there is no offset to anchor the
    local day, so the day comparison falls back to UTC; interior days
    still resolve to ``occupied`` and only the boundary dates degrade,
    reporting whichever field bounds that date.
    """
    checkin = parse_scheduled_instant(reservation.scheduled_checkin_raw)
    checkout = parse_scheduled_instant(reservation.scheduled_checkout_raw)
    arrival = reservation.arrival_date
    departure = reservation.departure_date
    reference = checkin or checkout

    if reference is None:
        now_date = now.astimezone(UTC).date()
        if now_date < arrival:
            return OccupancyResult(STATE_AWAITING_CHECKIN)
        if now_date > departure:
            return OccupancyResult(STATE_CHECKED_OUT)
        if arrival < now_date < departure:
            return OccupancyResult(STATE_OCCUPIED)
        field = "check_in" if now_date == arrival else "check_out"
        return OccupancyResult(STATE_UNKNOWN, field)

    now_date = now.astimezone(reference.tzinfo).date()

    if now_date == arrival:
        if checkin is None:
            return OccupancyResult(STATE_UNKNOWN, "check_in")
        if now < checkin:
            return OccupancyResult(STATE_AWAITING_CHECKIN)
        if checkout is not None and now >= checkout:
            return OccupancyResult(STATE_CHECKED_OUT)
        return OccupancyResult(STATE_OCCUPIED)

    if now_date == departure:
        if checkout is None:
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


def _log_degradation(reservation: HospitableReservation, field: str) -> None:
    """Emit the WARNING naming the reservation and the degraded field."""
    _LOGGER.warning(_FIELD_MESSAGES[field], reservation.reservation_id)


def derive_occupancy(
    reservation: HospitableReservation, now: datetime
) -> OccupancyResult:
    """Classify occupancy and log any degradation on every call."""
    result = classify_occupancy(reservation, now)
    if result.degraded_field is not None:
        _log_degradation(reservation, result.degraded_field)
    return result


def derive_occupancy_once(
    reservation: HospitableReservation,
    now: datetime,
    warned: set[tuple[str, str]],
) -> OccupancyResult:
    """Classify occupancy, logging each degradation once per field.

    ``warned`` tracks the ``(reservation_id, field)`` pairs already
    reported so a persistently degraded reservation does not emit a fresh
    warning on every poll.
    """
    result = classify_occupancy(reservation, now)
    if result.degraded_field is not None:
        key = (reservation.reservation_id, result.degraded_field)
        if key not in warned:
            warned.add(key)
            _log_degradation(reservation, result.degraded_field)
    return result
