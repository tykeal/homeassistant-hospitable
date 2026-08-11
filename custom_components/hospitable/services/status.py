# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Mapping of upstream reservation status categories to enum states."""

from __future__ import annotations

import logging

_LOGGER = logging.getLogger(__name__)

_CATEGORY_MAP = {
    "request": "pending_request",
    "cancelled": "cancelled",
    "not accepted": "not_accepted",
    "unknown": "unknown",
    "checkpoint": "checkpoint",
}


class StatusMapper:
    """Map ``reservation_status.current`` categories to enum states.

    All six upstream categories are mapped explicitly. ``accepted`` defers
    to the derived occupancy state; every other known category maps to a
    fixed enum member. An unrecognized category maps to ``unknown`` and is
    logged exactly once per distinct value without raising.
    """

    def __init__(self) -> None:
        """Initialize the mapper's once-per-value warning memory."""
        self._seen_unknown: set[str] = set()

    def map(self, category: str, occupancy_state: str) -> str:
        """Return the enum state for ``category`` and derived occupancy."""
        if category == "accepted":
            return occupancy_state
        mapped = _CATEGORY_MAP.get(category)
        if mapped is not None:
            return mapped
        if category not in self._seen_unknown:
            self._seen_unknown.add(category)
            _LOGGER.warning(
                "Unrecognized reservation status %r; mapping to unknown",
                category,
            )
        return "unknown"
