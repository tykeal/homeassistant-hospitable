# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Calendar request helpers for the Hospitable API."""

from __future__ import annotations

from datetime import date


def build_calendar_params(start: date, end: date) -> dict[str, str]:
    """Build query parameters for the property calendar endpoint.

    Only the forward window is sent. ``listing_id`` is deliberately never
    included: upstream silently discards it and the calendar is already an
    aggregate across every sales channel, so the parameter could do
    nothing useful (FR-058, FR-075).
    """
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}
