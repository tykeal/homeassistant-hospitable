# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Reservation window validation helpers."""

LOOKBACK_DEFAULT = 90
LOOKAHEAD_DEFAULT = 90


def validate_window(lookback: int, lookahead: int) -> tuple[int, int]:
    """Validate configured lookback and lookahead bounds."""
    if not 7 <= lookback <= 365:
        raise ValueError("lookback must be between 7 and 365 days")
    if not 1 <= lookahead <= 730:
        raise ValueError("lookahead must be between 1 and 730 days")
    return lookback, lookahead
