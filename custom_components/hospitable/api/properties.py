# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Property request helpers for the Hospitable API."""

from __future__ import annotations

from custom_components.hospitable.api.const import PER_PAGE_MAX


def build_properties_params(
    *, page: int, per_page: int
) -> dict[str, str | int | float | bool | None]:
    """Build query parameters for the properties endpoint."""
    return {
        "include": "listings",
        "page": page,
        "per_page": min(per_page, PER_PAGE_MAX),
    }
