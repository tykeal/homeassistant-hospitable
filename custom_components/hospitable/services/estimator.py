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
    task_interval_minutes: int,
) -> int:
    """Estimate daily upstream requests for the configured options.

    The task poll is counted because it fans out ONE request per
    property per cycle, which at thirteen properties on the default
    cadence is over a thousand requests a day. Omitting it would make
    the figure shown beside the rate-limit warning understate the real
    budget by more than the rest of the integration combined.

    Args:
        selected_property_count: Number of selected properties.
        property_interval_minutes: Property polling cadence.
        reservation_interval_minutes: Reservation polling cadence.
        last_observed_reservation_count: Reservations seen last poll,
            used to estimate reservation pagination.
        task_interval_minutes: Task polling cadence.

    Returns:
        The estimated number of upstream requests per day.
    """
    property_polls = floor(1440 / property_interval_minutes)
    calendar_polls = property_polls * selected_property_count
    batches = ceil(selected_property_count / 50)
    pages = max(1, ceil(last_observed_reservation_count / 100))
    reservation_polls = floor(1440 / reservation_interval_minutes) * batches * pages
    # One request per property per cycle: the task poll fans out rather
    # than batching, so it does not benefit from the batching the
    # reservation poll gets.
    task_polls = floor(1440 / task_interval_minutes) * selected_property_count
    return property_polls + calendar_polls + reservation_polls + task_polls
