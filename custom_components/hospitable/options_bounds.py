# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Numeric bound validation for the Hospitable options flow.

Extracted from ``config_flow`` so that module stays within the project's
file-size budget; the behaviour is unchanged.
"""

from __future__ import annotations

from typing import Any, TypeGuard

from custom_components.hospitable.const import (
    CONF_LOOKAHEAD_DAYS,
    CONF_LOOKBACK_DAYS,
    CONF_PROPERTY_INTERVAL,
    CONF_RESERVATION_INTERVAL,
    CONF_TASK_INTERVAL,
    CONF_TASK_WINDOW_DAYS,
    MIN_PROPERTY_INTERVAL,
    MIN_RESERVATION_INTERVAL,
    MIN_TASK_INTERVAL,
)

LOOKBACK_MIN = 7
LOOKBACK_MAX = 365
LOOKAHEAD_MIN = 1
LOOKAHEAD_MAX = 730
TASK_WINDOW_MIN = 1
# Upstream refuses an end_date more than THREE YEARS ahead with an
# HTTP 400, so an unbounded option would let a user configure a poll
# that can never succeed. 730 matches the existing lookahead ceiling
# and leaves well over a year of headroom below the upstream limit.
TASK_WINDOW_MAX = 730


def _validate_bounds(user_input: dict[str, Any]) -> dict[str, str]:
    """Return per-field errors naming the bound each value violated."""
    errors: dict[str, str] = {}
    reservation = user_input.get(CONF_RESERVATION_INTERVAL)
    if not _is_int(reservation) or reservation < MIN_RESERVATION_INTERVAL:
        errors[CONF_RESERVATION_INTERVAL] = "reservation_interval_min"
    property_interval = user_input.get(CONF_PROPERTY_INTERVAL)
    if not _is_int(property_interval) or property_interval < MIN_PROPERTY_INTERVAL:
        errors[CONF_PROPERTY_INTERVAL] = "property_interval_min"
    lookback = user_input.get(CONF_LOOKBACK_DAYS)
    if not _is_int(lookback) or not LOOKBACK_MIN <= lookback <= LOOKBACK_MAX:
        errors[CONF_LOOKBACK_DAYS] = "lookback_range"
    lookahead = user_input.get(CONF_LOOKAHEAD_DAYS)
    if not _is_int(lookahead) or not LOOKAHEAD_MIN <= lookahead <= LOOKAHEAD_MAX:
        errors[CONF_LOOKAHEAD_DAYS] = "lookahead_range"
    task_interval = user_input.get(CONF_TASK_INTERVAL)
    if not _is_int(task_interval) or task_interval < MIN_TASK_INTERVAL:
        errors[CONF_TASK_INTERVAL] = "task_interval_min"
    task_window = user_input.get(CONF_TASK_WINDOW_DAYS)
    if (
        not _is_int(task_window)
        or not TASK_WINDOW_MIN <= task_window <= TASK_WINDOW_MAX
    ):
        errors[CONF_TASK_WINDOW_DAYS] = "task_window_range"
    return errors


def _is_int(value: Any) -> TypeGuard[int]:
    """Return whether a value is a real integer, excluding booleans."""
    return isinstance(value, int) and not isinstance(value, bool)
