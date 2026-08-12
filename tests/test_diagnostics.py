# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase diagnostics tests."""

from __future__ import annotations


def test_diagnostics_are_allowlisted(synthetic_token: str) -> None:
    """Assert diagnostics omit credentials and personal data."""
    from custom_components.hospitable.diagnostics import (
        redact_diagnostics,
    )

    data = redact_diagnostics(
        {
            "token": synthetic_token,
            "email": "guest@example.com",
            "options": {"lookback_days": 90},
        }
    )
    assert synthetic_token not in str(data) and "guest@example.com" not in str(data)


# --- US3 guest fields are redacted, not omitted (T095, FR-042, FR-043) ---
#
# FR-042 is deliberately not satisfiable by a top-level allowlist alone:
# it requires the field to be SHOWN as redacted so that troubleshooting
# can tell "absent upstream" from "present but hidden".


REDACTED = "**REDACTED**"

_GUEST_VALUES = {
    "id": "guest-example-0001",
    "first_name": "Example",
    "last_name": "Guest",
    "email": "guest@example.com",
    "phone_numbers": ["+15550101001"],
    "location": "Example City, Example Region",
    "language": "en",
    "profile_picture": "https://example.com/guest-avatar.png",
}
_LEAKABLE = (
    "guest-example-0001",
    "Example City, Example Region",
    "guest@example.com",
    "+15550101001",
    "https://example.com/guest-avatar.png",
)


def test_nested_guest_object_fields_are_shown_as_redacted() -> None:
    """Every guest field is present but redacted, never silently dropped."""
    from custom_components.hospitable.diagnostics import redact_diagnostics

    data = redact_diagnostics(
        {"coordinators": {"reservations": [{"guest": dict(_GUEST_VALUES)}]}}
    )

    guest = data["coordinators"]["reservations"][0]["guest"]
    for field in _GUEST_VALUES:
        assert field in guest, f"{field} was omitted rather than redacted"
        assert guest[field] == REDACTED, f"{field} was not redacted"


def test_opt_in_and_picture_fields_are_redacted_too() -> None:
    """The opt-in fields and ``profile_picture`` are redacted as well.

    The guest-contact opt-in governs the ENTITY ATTRIBUTE surface only.
    Diagnostics is a different surface with its own control, and that
    control admits no opt-in (FR-042, FR-046).
    """
    from custom_components.hospitable.diagnostics import redact_diagnostics

    data = redact_diagnostics(
        {
            "options": {"guest_contact_details": True},
            "coordinators": {"reservations": [{"guest": dict(_GUEST_VALUES)}]},
        }
    )

    guest = data["coordinators"]["reservations"][0]["guest"]
    assert guest["email"] == REDACTED
    assert guest["phone_numbers"] == REDACTED
    assert guest["profile_picture"] == REDACTED


def test_guest_prefixed_attribute_keys_are_redacted() -> None:
    """Attribute-style ``guest_*`` keys are redacted by name too (FR-042)."""
    from custom_components.hospitable.diagnostics import redact_diagnostics

    data = redact_diagnostics(
        {
            "coordinators": {
                "reservations": [
                    {
                        "guest_first_name": "Example",
                        "guest_email": "guest@example.com",
                        "guest_phone_numbers": ["+15550101001"],
                        "reservation_id": "res-example-guest-full",
                    }
                ]
            }
        }
    )

    item = data["coordinators"]["reservations"][0]
    assert item["guest_first_name"] == REDACTED
    assert item["guest_email"] == REDACTED
    assert item["guest_phone_numbers"] == REDACTED
    # Operational, non-personal data must survive: a diagnostics dump
    # that redacts everything is useless for troubleshooting.
    assert item["reservation_id"] == "res-example-guest-full"


def test_no_guest_value_survives_anywhere_in_the_payload() -> None:
    """No raw guest value appears anywhere in the rendered payload."""
    from custom_components.hospitable.diagnostics import redact_diagnostics

    rendered = repr(
        redact_diagnostics(
            {"coordinators": {"reservations": [{"guest": dict(_GUEST_VALUES)}]}}
        )
    )

    for value in _LEAKABLE:
        assert value not in rendered, f"{value} survived redaction"


def test_the_guest_contact_option_survives_redaction() -> None:
    """The opt-in setting is not guest data and must stay visible.

    ``guest_contact_details`` shares the ``guest_`` attribute prefix but
    is a boolean SETTING. Whether the installer enabled it is exactly
    what a troubleshooter needs in order to explain which attributes an
    entity is publishing, so redacting it would hide operational state
    while protecting nothing.
    """
    from custom_components.hospitable.diagnostics import redact_diagnostics

    for enabled in (True, False):
        data = redact_diagnostics({"options": {"guest_contact_details": enabled}})
        assert data["options"]["guest_contact_details"] is enabled
