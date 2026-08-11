# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase retry tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime


def test_retry_policy_bounds_backoff() -> None:
    """Assert retry policy is bounded and retry-after aware."""
    from custom_components.hospitable.api.retry import (
        MAX_BACKOFF,
        backoff_delay,
        parse_retry_after,
        should_retry,
    )

    assert MAX_BACKOFF <= 300
    assert should_retry(429) and should_retry(500)
    assert not should_retry(401) and not should_retry(403)
    assert parse_retry_after("3") == 3.0
    assert parse_retry_after("999999") == MAX_BACKOFF
    assert parse_retry_after("not a date") is None
    assert parse_retry_after(None) is None
    future = format_datetime(datetime.now(UTC) + timedelta(seconds=30))
    parsed = parse_retry_after(future)
    assert parsed is not None
    assert 0 <= parsed <= 30
    assert backoff_delay(20) == MAX_BACKOFF
