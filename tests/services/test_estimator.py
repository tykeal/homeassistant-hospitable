# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase request estimate tests."""

from __future__ import annotations


def test_default_request_estimate() -> None:
    """Assert default ten-property request estimate.

    The task poll is included: it fans out one request per property per
    cycle, so ten properties on the default 15-minute cadence add 960
    requests a day on top of the 1704 the other polls cost.
    """
    from custom_components.hospitable.services.estimator import (
        estimate_requests_per_day,
    )

    assert estimate_requests_per_day(10, 60, 5, 500, 15) == 2664


def test_task_polling_is_counted_in_the_estimate() -> None:
    """The estimate rises when tasks are polled more often.

    The figure sits beside the rate-limit warning, so an estimate blind
    to the task fan-out would understate the real budget by more than
    the rest of the integration costs combined.
    """
    from custom_components.hospitable.services.estimator import (
        estimate_requests_per_day,
    )

    hourly = estimate_requests_per_day(10, 60, 5, 500, 60)
    frequent = estimate_requests_per_day(10, 60, 5, 500, 5)

    assert frequent > hourly
    # Exactly one request per property per cycle, never a batch.
    assert frequent - hourly == (1440 // 5 - 1440 // 60) * 10
