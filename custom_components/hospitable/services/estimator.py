# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Request budget estimator for Hospitable polling options."""

from __future__ import annotations

from math import ceil, floor


def estimate_requests_per_day(
    selected_property_count: int,
    property_interval_minutes: int,
    reservation_interval_minutes: int,
    last_observed_reservation_count: int,
) -> int:
    """Estimate daily upstream requests for the configured options."""
    property_polls = floor(1440 / property_interval_minutes)
    calendar_polls = property_polls * selected_property_count
    batches = ceil(selected_property_count / 50)
    pages = max(1, ceil(last_observed_reservation_count / 100))
    reservation_polls = floor(1440 / reservation_interval_minutes) * batches * pages
    return property_polls + calendar_polls + reservation_polls
