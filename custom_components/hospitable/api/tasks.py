# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Task request helpers for the Hospitable API.

``properties[]`` is MANDATORY upstream: a bare ``GET /tasks`` and a
dates-only ``GET /tasks`` both return HTTP 400, so a request is only
ever built for one named property (FR-030).

The dates are ALWAYS sent. Omitting them returns an undocumented
upstream default of roughly fourteen days, which would make the meaning
of the ``task_count`` sensor change silently if Hospitable ever changed
that default. Sending the window explicitly makes it a property of this
integration's configuration instead (FR-030, as amended).
"""

from __future__ import annotations

from datetime import date

from custom_components.hospitable.api.const import PER_PAGE_MAX

QueryValue = str | int | list[str]


def build_tasks_params(
    property_id: str, start: date, end: date, *, page: int = 1
) -> dict[str, QueryValue]:
    """Build query parameters for one property's task page.

    Args:
        property_id: The single property this request names.
        start: Window start date, which is today.
        end: Window end date, today plus the configured window.
        page: One-based page number to fetch.

    Returns:
        The query parameters for exactly one property and one page.
    """
    return {
        "properties[]": [property_id],
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "page": page,
        "per_page": PER_PAGE_MAX,
    }
