# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Reservation request helpers for the Hospitable API."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from custom_components.hospitable.api.const import PROPERTY_BATCH_MAX


def chunk_property_ids(property_ids: list[str]) -> Iterator[list[str]]:
    """Yield property identifiers in batches of fifty or fewer."""
    for index in range(0, len(property_ids), PROPERTY_BATCH_MAX):
        yield property_ids[index : index + PROPERTY_BATCH_MAX]


# Includes stacked comma-separated inside ONE ``include`` parameter.
# ``guest`` is SINGULAR: plural ``guests`` returns HTTP 200 and is
# silently ignored, which is how spec 001 came to record the include as
# unsupported. Stacking costs no additional request — this is a query
# parameter on a request the integration already makes.
RESERVATION_INCLUDES = ("guest", "properties")
RESERVATION_INCLUDE = ",".join(RESERVATION_INCLUDES)


def build_reservation_params(
    property_ids: list[str], start: date, end: date
) -> dict[str, str | int | list[str]]:
    """Build query parameters for the reservations endpoint."""
    return {
        "properties[]": property_ids,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "date_query": "checkin",
        "include": RESERVATION_INCLUDE,
        "page": 1,
        "per_page": 100,
    }
