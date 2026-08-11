# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Shared non-destructive property lifecycle helpers.

A property can leave the monitored set two ways: it disappears from the
account upstream (FR-056) or a user deselects it (FR-018). Both are
non-destructive — the entity goes unavailable but its registry entry and
recorder history are retained — so both consume the single presence
predicate defined here. US3 wires the disappearance path; US4 reuses the
same predicate for deselection without copying it.
"""

from __future__ import annotations

from collections.abc import Iterable, Set
from logging import Logger
from typing import Any


def property_active(coordinator: Any, property_id: str) -> bool:
    """Return whether a property is still present and monitored.

    The property is inactive when the properties coordinator no longer
    reports it (an upstream disappearance) or when it has been dropped
    from the coordinator's ``monitored_property_ids`` (a deselection).
    Either condition makes every entity for that property unavailable
    while leaving its registry entry intact.
    """
    data = getattr(coordinator, "data", None)
    if not data or property_id not in data:
        return False
    monitored = getattr(coordinator, "monitored_property_ids", None)
    return monitored is None or property_id in monitored


def note_disappearances(
    monitored: Iterable[str],
    current_ids: Set[str],
    warned: set[str],
    logger: Logger,
) -> None:
    """Log exactly one warning per monitored property that has vanished.

    ``warned`` tracks the property identifiers already reported so a
    persistently absent property does not warn on every poll. Callers
    prune reappeared identifiers from ``warned`` before invoking this so
    a property that returns and later disappears again warns afresh.
    """
    for property_id in monitored:
        if property_id not in current_ids and property_id not in warned:
            warned.add(property_id)
            logger.warning(
                "Monitored property %s is no longer present in the Hospitable "
                "account; its entities are now unavailable but their history is "
                "retained",
                property_id,
            )
