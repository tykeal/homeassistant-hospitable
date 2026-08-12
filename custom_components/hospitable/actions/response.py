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
"""

from __future__ import annotations

from typing import Any

# Objects known to carry guest identity and reduced to an allowlist.
IDENTITY_KEYS = frozenset({"guest"})
# Released unconditionally: non-identifying enough to be useful.
IDENTITY_ALLOWED = ("first_name", "last_name", "location", "language")
# Released only behind the guest-contact opt-in.
IDENTITY_CONTACT = ("email", "phone_numbers")
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
