# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Retry helpers for bounded Hospitable API backoff."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

MAX_BACKOFF = 300.0
MAX_RETRIES = 3


def should_retry(status: int) -> bool:
    """Return whether an HTTP status is retryable."""
    return status == 429 or 500 <= status <= 599


def parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header as seconds or an HTTP date."""
    if not value:
        return None
    if value.isdigit():
        return min(float(value), MAX_BACKOFF)
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError) as exc:
        _ = exc
        return None
    return min(max((parsed - datetime.now(UTC)).total_seconds(), 0.0), MAX_BACKOFF)


def backoff_delay(attempt: int) -> float:
    """Return a capped exponential delay without blocking."""
    return float(min(0.5 * (2**attempt), MAX_BACKOFF))
