# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Deterministic selection of the representative reservation."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

from custom_components.hospitable.api.models import HospitableReservation
from custom_components.hospitable.services.occupancy import (
    STATE_OCCUPIED,
    classify_occupancy,
    parse_scheduled_instant,
)

_INACTIVE_CATEGORIES = {"cancelled", "not accepted"}

_TIER_OCCUPIED = 0
_TIER_FUTURE = 1
_TIER_PAST = 2


def _reservation_zone(reservation: HospitableReservation) -> timezone:
    """Return the reservation's own offset, defaulting to UTC."""
    for raw in (
        reservation.scheduled_checkin_raw,
        reservation.scheduled_checkout_raw,
    ):
        instant = parse_scheduled_instant(raw)
        if instant is not None and instant.tzinfo is not None:
            offset = instant.utcoffset()
            if offset is not None:
                return timezone(offset)
    return UTC


def _epoch(raw: str | None, default: float) -> float:
    """Return an instant's POSIX timestamp, or ``default`` when unparsable."""
    instant = parse_scheduled_instant(raw)
    return instant.timestamp() if instant is not None else default


def _sort_key(
    reservation: HospitableReservation, now: datetime
) -> tuple[int, int, float, float, str]:
    """Build the total-order sort key for one reservation.

    Active reservations always outrank inactive (cancelled or not
    accepted) ones. Within an activity class, an in-progress stay wins,
    then the soonest future arrival, then the most recent past departure.
    A reservation whose scheduled time is missing or unparsable sorts
    after its dated peers within the tier. Ties break on ascending
    reservation identifier.
    """
    active_rank = 0 if reservation.status_category not in _INACTIVE_CATEGORIES else 1
    state = classify_occupancy(reservation, now).state
    now_date = now.astimezone(_reservation_zone(reservation)).date()

    if state == STATE_OCCUPIED:
        tier, primary, secondary = _TIER_OCCUPIED, 0.0, 0.0
    elif reservation.arrival_date >= now_date:
        tier = _TIER_FUTURE
        primary = float(reservation.arrival_date.toordinal())
        secondary = _epoch(reservation.scheduled_checkin_raw, float("inf"))
    else:
        tier = _TIER_PAST
        primary = -float(reservation.departure_date.toordinal())
        checkout = parse_scheduled_instant(reservation.scheduled_checkout_raw)
        secondary = -checkout.timestamp() if checkout is not None else float("inf")

    return (active_rank, tier, primary, secondary, reservation.reservation_id)


def select_reservation(
    reservations: list[HospitableReservation], now: datetime
) -> tuple[HospitableReservation | None, list[HospitableReservation]]:
    """Return the representative reservation and the ordered remainder.

    The result is deterministic across repeated refreshes and across
    input ordering because the sort key is a total order.
    """
    if not reservations:
        return None, []
    ranked = sorted(reservations, key=lambda reservation: _sort_key(reservation, now))
    return ranked[0], list(ranked[1:])


def is_forthcoming(reservation: HospitableReservation, now: datetime) -> bool:
    """Return whether a reservation is a real forthcoming stay.

    A forthcoming stay is one that has not been cancelled or declined and
    whose arrival date is strictly in the future relative to ``now`` in
    the reservation's own offset. US3's upcoming_reservations sensor
    (T090) consumes this identical predicate so the sensor count and the
    reservation_status upcoming_reservations attribute never disagree.
    """
    if reservation.status_category in _INACTIVE_CATEGORIES:
        return False
    now_date = now.astimezone(_reservation_zone(reservation)).date()
    return reservation.arrival_date > now_date
