# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Allowlist diagnostics helpers for Hospitable.

Two layers, because they answer different questions. The top-level
ALLOWLIST decides which sections may appear at all. The guest REDACTOR
then walks whatever survived and replaces every guest field value with a
marker.

Redacting rather than omitting is deliberate (FR-042): a dump that drops
the field cannot tell a troubleshooter "the API never sent it" from "we
hid it". The marker distinguishes the two.

The guest-contact opt-in governs the ENTITY ATTRIBUTE surface only.
Diagnostics is a different surface with its own control, and this
control admits no opt-in at all (FR-042, FR-046).
"""

from __future__ import annotations

from typing import Any

from custom_components.hospitable.const import CONF_GUEST_CONTACT_DETAILS

ALLOWED_TOP_LEVEL = {
    "version",
    "minor_version",
    "namespace_source",
    "options",
    "coordinators",
    "counts",
}

REDACTED = "**REDACTED**"

# Objects whose every member is guest data. ``sender`` is the opaque
# message author object; it carries the same fields as ``guest``.
GUEST_CONTAINER_KEYS = frozenset({"guest", "sender"})
# Attribute-style keys, as the reservation entity spells them.
GUEST_ATTRIBUTE_PREFIX = "guest_"
# Keys that share the attribute prefix but carry no guest data. The
# guest-contact option is a BOOLEAN SETTING, and whether the installer
# turned it on is precisely what a troubleshooter needs to see.
NON_GUEST_PREFIXED_KEYS = frozenset({CONF_GUEST_CONTACT_DETAILS})


def redact_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    """Return an allowlisted diagnostics payload without private values.

    Args:
        payload: Raw diagnostics payload.

    Returns:
        The allowlisted payload with every guest field redacted.
    """
    return {
        key: _redact_value(value)
        for key, value in payload.items()
        if key in ALLOWED_TOP_LEVEL
    }


def _redact_value(value: Any) -> Any:
    """Walk a value, redacting guest fields wherever they appear.

    Args:
        value: Any nested diagnostics value.

    Returns:
        The value with guest fields replaced by the redaction marker.
    """
    if isinstance(value, dict):
        return {key: _redact_member(key, member) for key, member in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def _redact_member(key: str, value: Any) -> Any:
    """Redact one mapping member by its key.

    Args:
        key: The member key.
        value: The member value.

    Returns:
        The redaction marker for a guest field, else the walked value.
    """
    if key in GUEST_CONTAINER_KEYS:
        return _redact_guest_object(value)
    if key.startswith(GUEST_ATTRIBUTE_PREFIX) and key not in NON_GUEST_PREFIXED_KEYS:
        return REDACTED
    return _redact_value(value)


def _redact_guest_object(value: Any) -> Any:
    """Redact every field of a guest-bearing object.

    Every KEY is preserved so the dump still shows which fields the API
    returned; only the values are replaced.

    Args:
        value: A guest object, or any other shape.

    Returns:
        The object with all values redacted, or the value unchanged when
        it is not a mapping. A ``null`` guest stays ``null``: that it is
        absent is not private, and hiding it would obscure exactly the
        condition FR-040 tolerates.
    """
    if not isinstance(value, dict):
        return value
    return dict.fromkeys(value, REDACTED)
