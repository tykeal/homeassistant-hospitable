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

from custom_components.hospitable.const import (
    CONF_GUEST_CONTACT_DETAILS,
    CONF_NAMESPACE_SOURCE,
)

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


async def async_get_config_entry_diagnostics(hass: Any, entry: Any) -> dict[str, Any]:
    """Return the diagnostics download for one config entry (FR-063).

    This is the name Home Assistant looks up when it resolves a
    diagnostics platform, and its absence is why the redactor above sat
    unreachable: the platform registered with a null handler, so the
    integration had no diagnostics download at all despite shipping a
    complete and correct redactor for one.

    The payload is assembled to be safe BY CONSTRUCTION and then passed
    through the redactor anyway. Two independent layers, because the
    whole failure mode this file exists to prevent is a single control
    being scoped to the wrong surface:

    * the credential never enters the payload, since ``entry.data`` is
      never dumped and ``data`` is not an allowlisted section either;
    * guest identity DOES enter it, deliberately, so that FR-042's
      show-redacted requirement has something to act on.

    Args:
        hass: The Home Assistant instance. Unused, but part of the
            signature Home Assistant calls.
        entry: The config entry being dumped.

    Returns:
        The allowlisted, redacted diagnostics payload.
    """
    del hass
    coordinators = _entry_coordinators(entry)
    return redact_diagnostics(
        {
            "version": getattr(entry, "version", None),
            "minor_version": getattr(entry, "minor_version", None),
            "namespace_source": dict(getattr(entry, "data", None) or {}).get(
                CONF_NAMESPACE_SOURCE
            ),
            "options": dict(getattr(entry, "options", None) or {}),
            "coordinators": {
                name: _coordinator_section(name, coordinator)
                for name, coordinator in coordinators.items()
            },
            "counts": {
                name: _item_count(coordinator)
                for name, coordinator in coordinators.items()
            },
        }
    )


def _entry_coordinators(entry: Any) -> dict[str, Any]:
    """Return the entry's coordinators, tolerating an unloaded entry.

    Args:
        entry: The config entry being dumped.

    Returns:
        Coordinators by name, empty when the entry is not loaded. A
        diagnostics download is most wanted when something is broken,
        so failing to produce one for a half-loaded entry would with-
        hold the dump exactly when it matters.
    """
    runtime_data = getattr(entry, "runtime_data", None)
    if not isinstance(runtime_data, dict):
        return {}
    coordinators = runtime_data.get("coordinators")
    return coordinators if isinstance(coordinators, dict) else {}


def _coordinator_section(name: str, coordinator: Any) -> dict[str, Any]:
    """Summarize one coordinator for the dump.

    Args:
        name: The coordinator's key in runtime data.
        coordinator: The coordinator itself.

    Returns:
        Its health and size, plus reservation rows for the one
        coordinator that holds guest identity.
    """
    section: dict[str, Any] = {
        "last_update_success": bool(getattr(coordinator, "last_update_success", False)),
        "update_interval": str(getattr(coordinator, "update_interval", None)),
        "item_count": _item_count(coordinator),
    }
    if name == "reservations":
        section["items"] = [
            _reservation_row(reservation)
            for reservation in _coordinator_items(coordinator)
        ]
    return section


def _coordinator_items(coordinator: Any) -> list[Any]:
    """Return a coordinator's payload as a flat list.

    Args:
        coordinator: The coordinator to read.

    Returns:
        Its items. Coordinator data is a list for reservations and a
        mapping keyed by property elsewhere, so both are flattened.
    """
    data = getattr(coordinator, "data", None)
    if isinstance(data, dict):
        return list(data.values())
    if isinstance(data, list):
        return list(data)
    return []


def _item_count(coordinator: Any) -> int:
    """Return how many items a coordinator holds.

    Args:
        coordinator: The coordinator to measure.

    Returns:
        The item count, zero when it holds nothing.
    """
    return len(_coordinator_items(coordinator))


def _reservation_row(reservation: Any) -> dict[str, Any]:
    """Render one reservation for the dump.

    Only operational fields are named individually. Guest identity goes
    in whole, under the ``guest`` key, so that the redactor blanks every
    VALUE while preserving every KEY -- that is what lets a
    troubleshooter tell a field the API never sent from one this
    integration hid (FR-042).

    A null guest stays null for the same reason. That a reservation has
    no guest is not private, and it is exactly the condition FR-040
    tolerates and that support questions turn on.

    Args:
        reservation: A reservation model.

    Returns:
        The reservation's operational fields and its guest object.
    """
    guest = getattr(reservation, "guest", None)
    return {
        "reservation_id": getattr(reservation, "reservation_id", None),
        "property_id": getattr(reservation, "property_id", None),
        "status_category": getattr(reservation, "status_category", None),
        "status_sub_category": getattr(reservation, "status_sub_category", None),
        "arrival_date": str(getattr(reservation, "arrival_date", None)),
        "departure_date": str(getattr(reservation, "departure_date", None)),
        "channel": getattr(reservation, "channel", None),
        "has_last_message_at": getattr(reservation, "last_message_at", None)
        is not None,
        "guest": None
        if guest is None
        else {
            "guest_id": guest.guest_id,
            "first_name": guest.first_name,
            "last_name": guest.last_name,
            "email": guest.email,
            "phone_numbers": guest.phone_numbers,
            "location": guest.location,
            "language": guest.language,
        },
    }
