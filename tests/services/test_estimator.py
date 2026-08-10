# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase request estimate tests."""

from __future__ import annotations


def test_default_request_estimate() -> None:
    """Assert default ten-property request estimate."""
    from custom_components.hospitable.services.estimator import (
        estimate_requests_per_day,
    )

    assert estimate_requests_per_day(10, 60, 5, 500) == 1704
