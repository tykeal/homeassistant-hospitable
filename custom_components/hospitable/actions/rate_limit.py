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

``TRACKER`` is forwarded through a module ``__getattr__`` rather than
bound at import time, and that difference is the whole point. It is a
module-level singleton that the test suite's reset fixture REBINDS on
the canonical module. A plain ``from ... import TRACKER`` here would
capture whichever object existed when this module was first imported
and keep handing that one out forever, so callers reaching it through
this path would silently be using a different tracker — and a different
budget — from everybody else. Resolving it on each attribute access
means this path can never drift from the canonical one.
"""

from __future__ import annotations

from typing import Any

from custom_components.hospitable import rate_limit
from custom_components.hospitable.rate_limit import (
    RESERVATION_LIMIT,
    RESERVATION_WINDOW_SECONDS,
    TOKEN_LIMIT,
    TOKEN_WINDOW_SECONDS,
    RateLimitTracker,
    ServerHint,
    token_key,
)


def __getattr__(name: str) -> Any:
    """Forward ``TRACKER`` to the canonical module on every access.

    Args:
        name: Attribute being looked up on this module.

    Returns:
        The canonical module's current attribute value.

    Raises:
        AttributeError: The name is not exported by the canonical
            module either, so this path must not invent it.
    """
    if name == "TRACKER":
        return rate_limit.TRACKER
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "RESERVATION_LIMIT",
    "RESERVATION_WINDOW_SECONDS",
    "TOKEN_LIMIT",
    "TOKEN_WINDOW_SECONDS",
    # Resolved by ``__getattr__`` above rather than bound here, so
    # ruff cannot see it statically.
    "TRACKER",  # noqa: F822
    "RateLimitTracker",
    "ServerHint",
    "token_key",
]
