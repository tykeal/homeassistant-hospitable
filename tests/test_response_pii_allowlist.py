# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""VS-11 — the service-response PII audit by ALLOWLIST (T153a).

**Principle XII status: CHARACTERIZATION.** Every assertion here
describes behaviour US1 to US5 already shipped, so this file lands
green in one commit. It is not a red-phase pair and does not claim to
be one.

**Why an allowlist and not a denylist.** ``test_response_privacy.py``
already asserts that ``profile_picture`` and ``sender`` are absent.
That is a denylist: it proves the two keys somebody remembered are
gone, and it cannot fail when a THIRD key appears. Every privacy defect
on this project has had that shape — a control that looked complete but
was scoped to a surface it did not reach. So this file enumerates every
mapping key at every depth of every service response and compares the
whole set against an allowlist. A key nobody has classified fails the
build and forces a human to decide, which is the only mechanism that
catches a leak nobody predicted.

The allowlists are grouped by why each key is releasable, so a reviewer
adding to one has to say which group it belongs to.
"""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.hospitable.const import DOMAIN
from tests.helpers.surface import response_keys

# --- What every response envelope carries -------------------------------

ENVELOPE = frozenset({"found"})

# --- Reservation payload, released unconditionally ----------------------
#
# Operational booking facts. None of them identifies a person: the
# occupancy block is COUNTS, and ``code``/``platform_id`` identify the
# booking on the channel rather than the guest.
RESERVATION_OPERATIONAL = frozenset(
    {
        "adult_count",
        "arrival_date",
        "booking_date",
        "category",
        # ``changed_at`` and ``status`` belong to the reservation-status
        # history entries nested under ``reservation_status``. Both were
        # found by this allowlist rather than transcribed into it, which
        # is the whole point of enumerating instead of denying.
        "changed_at",
        "check_in",
        "check_out",
        "child_count",
        "code",
        "current",
        "departure_date",
        "guests",
        "history",
        "id",
        "infant_count",
        "nights",
        "pet_count",
        "platform",
        "platform_id",
        "properties",
        "reservation_status",
        "status",
        "stay_type",
        "sub_category",
        "total",
    }
)

# Guest identity released by default (FR-047). Names, location and
# language are the fields an automation needs to greet a guest; they are
# identity but not contact routes.
GUEST_DEFAULT = frozenset({"guest", "first_name", "last_name", "location", "language"})

# Guest CONTACT ROUTES, released only behind the opt-in (FR-047).
GUEST_CONTACT = frozenset({"email", "phone_numbers"})

# --- Message payload ----------------------------------------------------
#
# ``sender_type`` and ``sender_role`` are SIBLINGS of the dropped
# ``sender`` object, not members of it, so they survive by design: they
# are role discriminators carrying no identity (FR-047a).
MESSAGE_KEYS = frozenset(
    {
        "attachments",
        "body",
        "content_type",
        "conversation_id",
        "created_at",
        "id",
        "messages",
        "platform",
        "reservation_uuid",
        "sender_role",
        "sender_type",
        "source",
    }
)

# --- Property payload ---------------------------------------------------
#
# ``platform_email``, ``platform_name``, ``platform_picture`` and
# ``platform_user_id`` are the OPERATOR's own channel account, which is
# the caller's own data and the point of the service. That is a scope
# decision recorded in ``actions/get_property_info.py`` and named here
# so this audit does not silently ratify it.
PROPERTY_KEYS = frozenset(
    {
        "address",
        "bathrooms",
        "bedrooms",
        "beds",
        "capacity",
        "checkin",
        "checkout",
        "city",
        "co_hosts",
        "coordinates",
        "country",
        "currency",
        "display",
        "ical_imports",
        "id",
        "latitude",
        "listed",
        "listings",
        "longitude",
        "max",
        "name",
        "number",
        "platform",
        "platform_email",
        "platform_id",
        "platform_name",
        "platform_picture",
        "platform_user_id",
        "postcode",
        "property",
        "property_type",
        "public_name",
        "state",
        "street",
        "timezone",
    }
)

# Never releasable on this surface, under any option, at any depth.
FORBIDDEN = frozenset({"profile_picture", "sender"})


def allowlist(service: str, *, guest_contact: bool) -> frozenset[str]:
    """Return every key a service may return under a given option state.

    Args:
        service: Registered service name.
        guest_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        The complete set of permitted mapping keys.
    """
    contact = GUEST_CONTACT if guest_contact else frozenset()
    if service == "get_messages":
        return ENVELOPE | MESSAGE_KEYS
    if service == "get_property_info":
        return ENVELOPE | PROPERTY_KEYS
    reservation = ENVELOPE | RESERVATION_OPERATIONAL | GUEST_DEFAULT | contact
    if service == "find_reservation":
        return reservation | {"reservation"}
    if service == "get_reservations":
        return reservation | {"reservations", "property_id"}
    raise AssertionError(f"no allowlist declared for service {service}")


LOOKUP_CALLS: tuple[tuple[str, dict[str, Any]], ...] = (
    ("get_messages", {"reservation_uuid": "res-guest-001"}),
    ("find_reservation", {"reservation_uuid": "res-guest-001"}),
    ("get_reservations", {"property_id": "prop-example-001"}),
    ("get_property_info", {"property_id": "prop-example-001"}),
)


@pytest.mark.parametrize("guest_contact", [False, True])
async def test_every_service_response_key_is_allowlisted(
    hass: Any, respx_router: Any, guest_contact: bool
) -> None:
    """No service returns a key nobody has classified (T153a, FR-046).

    This is the assertion a denylist cannot make. A new upstream field,
    a new handler field, or a fixture that gains one, all fail here
    rather than shipping unnoticed.
    """
    from tests.helpers.audit_entry import call_every_lookup

    responses = await call_every_lookup(
        hass, respx_router, guest_contact=guest_contact, calls=LOOKUP_CALLS
    )
    for service, payload in responses.items():
        permitted = allowlist(service, guest_contact=guest_contact)
        unexpected = response_keys(payload) - permitted
        assert not unexpected, (
            f"{service} returned unclassified keys {sorted(unexpected)} with "
            f"guest_contact={guest_contact}. Classify each one in this "
            "file's allowlist groups before releasing it."
        )


@pytest.mark.parametrize("guest_contact", [False, True])
async def test_no_service_response_carries_a_forbidden_key(
    hass: Any, respx_router: Any, guest_contact: bool
) -> None:
    """``profile_picture`` and ``sender`` never appear (SC-003a)."""
    from tests.helpers.audit_entry import call_every_lookup

    responses = await call_every_lookup(
        hass, respx_router, guest_contact=guest_contact, calls=LOOKUP_CALLS
    )
    for service, payload in responses.items():
        leaked = response_keys(payload) & FORBIDDEN
        assert not leaked, f"{service} leaked {sorted(leaked)}"


@pytest.mark.parametrize("guest_contact", [False, True])
async def test_contact_keys_track_the_option_exactly(
    hass: Any, respx_router: Any, guest_contact: bool
) -> None:
    """``email`` and ``phone_numbers`` follow the opt-in (FR-047).

    Asserted in BOTH directions. Absence alone would also hold if the
    guest object were empty, so the ON case proves the fixture really
    carries contact details and the OFF case is therefore a control
    working rather than a vacuum.
    """
    from tests.helpers.audit_entry import call_every_lookup

    responses = await call_every_lookup(
        hass, respx_router, guest_contact=guest_contact, calls=LOOKUP_CALLS
    )
    for service in ("find_reservation", "get_reservations"):
        present = response_keys(responses[service]) & GUEST_CONTACT
        if guest_contact:
            assert present == GUEST_CONTACT, (
                f"{service} withheld contact details with the opt-in ON, so "
                "the OFF case proves nothing"
            )
        else:
            assert not present, (
                f"{service} released {sorted(present)} with the opt-in OFF"
            )


async def test_the_audited_call_set_covers_every_registered_service(
    hass: Any, respx_router: Any
) -> None:
    """The audit reaches every service the integration registers.

    Without this, adding a sixth service would leave it silently
    unaudited while every assertion above kept passing.
    """
    from custom_components.hospitable.actions import SERVICE_DEFINITIONS
    from tests.helpers.audit_entry import setup_audit_entry

    await setup_audit_entry(hass, respx_router, guest_contact=False)
    registered = {definition.name for definition in SERVICE_DEFINITIONS}
    audited = {name for name, _ in LOOKUP_CALLS} | {"send_message"}
    assert audited == registered, (
        f"services registered but not audited: {sorted(registered - audited)}"
    )
    for name in registered:
        assert hass.services.has_service(DOMAIN, name), name


@pytest.mark.parametrize("guest_contact", [False, True])
async def test_the_send_response_is_allowlisted_too(
    hass: Any, respx_router: Any, guest_contact: bool
) -> None:
    """``send_message`` returns an acceptance record and nothing else.

    Its response is built by the integration rather than echoed from
    upstream, so the allowlist here is exact rather than defensive.
    """
    from tests.helpers.audit_entry import call_send_message

    payload = await call_send_message(hass, respx_router, guest_contact=guest_contact)
    assert response_keys(payload) == {
        "accepted",
        "reservation_uuid",
        "sent_reference_id",
    }
