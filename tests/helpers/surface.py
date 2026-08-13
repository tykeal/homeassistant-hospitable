# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Surface enumeration for the US6 privacy audits (T153, T153a).

**Why enumeration rather than a denylist.** Every previous privacy
defect on this project had the same shape: a control that looked
complete but was scoped to a different surface. A test that asserts
today's known-bad keys are absent proves only that somebody remembered
them. It cannot fail when a NEW key appears, which is precisely the
failure mode that has bitten repeatedly.

So these helpers enumerate a surface exhaustively — every attribute of
every entity, every mapping key at every depth of every service
response — and hand the caller a set to compare against an ALLOWLIST.
An unexpected key then fails LOUDLY and forces a human to classify it,
rather than sailing through because nobody thought to deny it.
"""

from __future__ import annotations

from typing import Any

# Attributes Home Assistant itself attaches to every state. They are
# platform metadata rather than integration payload, so an integration
# allowlist neither owns nor should enumerate them.
PLATFORM_ATTRIBUTES = frozenset(
    {
        "attribution",
        "device_class",
        "friendly_name",
        "icon",
        "options",
        "restored",
        "state_class",
        "supported_features",
        "unit_of_measurement",
    }
)


def response_keys(payload: Any) -> set[str]:
    """Return every mapping key at every depth of a payload.

    Lists are walked into, so a key that only ever appears inside an
    array element is still reported.

    Args:
        payload: Any JSON-serialisable structure.

    Returns:
        Every mapping key found, at any nesting depth.
    """
    found: set[str] = set()
    _walk(payload, found)
    return found


def _walk(node: Any, found: set[str]) -> None:
    """Accumulate mapping keys from one node of a payload.

    Args:
        node: The current node.
        found: Accumulator mutated in place.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            found.add(str(key))
            _walk(value, found)
    elif isinstance(node, list):
        for item in node:
            _walk(item, found)


def entity_attributes(
    hass: Any, *, domain_prefix: str = "sensor."
) -> dict[str, set[str]]:
    """Return every integration attribute of every matching entity.

    Platform-supplied attributes are removed, so the result is the
    surface this integration is actually responsible for.

    Args:
        hass: The Home Assistant test instance.
        domain_prefix: Entity id prefix to collect.

    Returns:
        Attribute-name sets keyed by entity id.
    """
    collected: dict[str, set[str]] = {}
    for state in hass.states.async_all():
        if not state.entity_id.startswith(domain_prefix):
            continue
        collected[state.entity_id] = set(state.attributes) - PLATFORM_ATTRIBUTES
    return collected
