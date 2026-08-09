# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase retry tests."""

from __future__ import annotations


def test_retry_policy_bounds_backoff() -> None:
    """Assert retry policy is bounded and retry-after aware."""
    from custom_components.hospitable.api.retry import (
        MAX_BACKOFF,
        parse_retry_after,
        should_retry,
    )

    assert MAX_BACKOFF <= 300
    assert should_retry(429) and should_retry(500)
    assert not should_retry(401) and not should_retry(403)
    assert parse_retry_after("3") == 3.0
