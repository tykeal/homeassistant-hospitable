# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""The single response-privacy chokepoint (FR-046 to FR-048, D-16).

EVERY service response is built here. Filtering per handler is what the
CRITICAL privacy defect looked like: a future service can forget a
per-handler filter, but it cannot forget the only function that builds
a response.

Two rules, deliberately asymmetric:

* ``profile_picture`` is dropped unconditionally, at any depth. No
  opt-in re-enables it.
* The opaque message ``sender`` object is dropped unconditionally and
  ENTIRELY. FR-047a is stricter than FR-047 here: nothing inside
  ``sender`` is a role discriminator, because the discriminators
  ``sender_type`` and ``sender_role`` are its SIBLINGS, not its
  members. Reducing it to an allowlist would therefore release guest
  identity for no benefit.
* ``email`` and ``phone_numbers`` are released only when the
  guest-contact opt-in is on.

Identity-bearing objects are filtered through an ALLOWLIST, not a
denylist. A denylist fails open: a field upstream adds tomorrow would
ship unfiltered.

Co-host objects (FR-047b) use a SEPARATE allowlist from guests.
``user_id``, ``channel_name``, and ``name`` are unconditional;
``email`` and ``phone_numbers`` are gated behind the same
guest-contact opt-in; all other keys are dropped. The co-host
container is a LIST of dicts, handled explicitly so it cannot
fall through the single-dict identity path unfiltered.
"""

from __future__ import annotations

from typing import Any

# Objects known to carry guest identity and reduced to an allowlist.
IDENTITY_KEYS = frozenset({"guest"})
# Released unconditionally: non-identifying enough to be useful.
IDENTITY_ALLOWED = ("first_name", "last_name", "location", "language")
# Released only behind the guest-contact opt-in.
IDENTITY_CONTACT = ("email", "phone_numbers")

# Co-host objects use a DIFFERENT allowlist from guests (FR-047b).
# A co-host key is the dict key under which a LIST of co-host objects
# appears. The list-of-dicts shape must be handled explicitly.
CO_HOST_KEYS = frozenset({"co_hosts"})
CO_HOST_ALLOWED = ("user_id", "channel_name", "name")
CO_HOST_CONTACT = ("email", "phone_numbers")

# Never released, under any option, at any depth. ``sender`` is the
# opaque message author object; it carries the same fields as ``guest``
# and has no returnable part (FR-047a).
ALWAYS_DROPPED = frozenset({"profile_picture", "sender"})


def serialize_response(payload: Any, *, guest_contact: bool = False) -> Any:
    """Filter a payload for return to a service caller.

    Args:
        payload: Raw payload of any shape.
        guest_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        The payload with identity fields filtered. Scalars pass through
        unchanged; dicts and lists are walked recursively.
    """
    if isinstance(payload, dict):
        return {
            key: _filter_identity(value, guest_contact=guest_contact)
            if key in IDENTITY_KEYS
            else _filter_co_hosts(value, guest_contact=guest_contact)
            if key in CO_HOST_KEYS
            else serialize_response(value, guest_contact=guest_contact)
            for key, value in payload.items()
            if key not in ALWAYS_DROPPED
        }
    if isinstance(payload, list):
        return [
            serialize_response(item, guest_contact=guest_contact) for item in payload
        ]
    return payload


def _filter_identity(value: Any, *, guest_contact: bool) -> Any:
    """Reduce an identity object to its allowlisted fields.

    Args:
        value: Candidate identity object.
        guest_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        The allowlisted subset, or the value unchanged when it is not a
        mapping.
    """
    if not isinstance(value, dict):
        return serialize_response(value, guest_contact=guest_contact)
    allowed = list(IDENTITY_ALLOWED)
    if guest_contact:
        allowed.extend(IDENTITY_CONTACT)
    return {key: value[key] for key in allowed if key in value}


def _filter_co_hosts(value: Any, *, guest_contact: bool) -> Any:
    """Reduce a co-host list to allowlisted fields per entry (FR-047b).

    ``co_hosts`` is a LIST of dicts. Each dict is reduced to the
    co-host allowlist. The list container is handled explicitly so
    that a list handed to ``_filter_identity`` (which expects a
    single dict) does not silently pass through unfiltered.

    Args:
        value: The co_hosts value (expected to be a list of dicts).
        guest_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        The filtered list, or the value recursed if not a list.
    """
    if not isinstance(value, list):
        return serialize_response(value, guest_contact=guest_contact)
    return [_filter_one_co_host(item, guest_contact=guest_contact) for item in value]


def _filter_one_co_host(value: Any, *, guest_contact: bool) -> Any:
    """Reduce a single co-host dict to its allowlisted fields.

    Args:
        value: A single co-host object.
        guest_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        The allowlisted subset, or the value unchanged when not a
        mapping.
    """
    if not isinstance(value, dict):
        return serialize_response(value, guest_contact=guest_contact)
    allowed = list(CO_HOST_ALLOWED)
    if guest_contact:
        allowed.extend(CO_HOST_CONTACT)
    return {key: value[key] for key in allowed if key in value}
