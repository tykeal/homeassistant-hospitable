# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Compatibility re-export of the shared rate-limit tracker.

The tracker moved to ``custom_components.hospitable.rate_limit`` in
US5. It was never write-specific — it models the UPSTREAM
per-reservation and per-token budgets, which the opt-in
awaiting-host-reply poll consumes exactly as a send does, and OQ-007
leaves open whether reads and writes even share one bucket. Keeping it
under ``actions`` would have forced the polling path to import from the
write-service package, which write-isolation gate 3 forbids outright
(research D-01). Weakening that gate to fit the tracker's old address
was never an option, so the tracker moved instead.

Everything here is the SAME object as in the canonical module, not a
copy. This module exists so the documented ``actions.rate_limit``
import path keeps resolving.
"""

from __future__ import annotations

from custom_components.hospitable.rate_limit import (
    RESERVATION_LIMIT,
    RESERVATION_WINDOW_SECONDS,
    TOKEN_LIMIT,
    TOKEN_WINDOW_SECONDS,
    RateLimitTracker,
    ServerHint,
    token_key,
)

__all__ = [
    "RESERVATION_LIMIT",
    "RESERVATION_WINDOW_SECONDS",
    "TOKEN_LIMIT",
    "TOKEN_WINDOW_SECONDS",
    "RateLimitTracker",
    "ServerHint",
    "token_key",
]
