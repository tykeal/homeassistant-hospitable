# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase request estimate tests."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T037 estimator"
)
def test_default_request_estimate() -> None:
    """Assert default ten-property request estimate."""
    from custom_components.hospitable.services.estimator import (
        estimate_requests_per_day,  # type: ignore[import-not-found, import-untyped, unused-ignore]
    )

    assert estimate_requests_per_day(10, 60, 5, 500) == 1704
