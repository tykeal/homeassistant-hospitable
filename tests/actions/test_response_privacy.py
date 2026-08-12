# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for the response-privacy chokepoint (FR-046 to FR-048).

Every service response passes through ONE shared serialiser. Filtering
per handler is what the CRITICAL privacy defect found by the analyze
gate looked like: a future service can forget a per-handler filter, but
it cannot forget the only code path that builds a response.

Scope note, disclosed rather than smuggled: the serialiser is scheduled
in US2 as T075a, and its acceptance criterion covers EVERY registered
service. It is FRONT-LOADED here because ``send_message`` returns a
response payload in US1 and would otherwise ship unfiltered for one
release. The US2 checkboxes stay unticked because their full scope is
not discharged by this change.
"""

from __future__ import annotations

from typing import Any

import pytest


def _serialize(payload: Any, *, guest_contact: bool = False) -> Any:
    """Run a payload through the shared response serialiser.

    Args:
        payload: Raw payload to serialise.
        guest_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        The filtered payload.
    """
    from custom_components.hospitable.actions.response import (
        serialize_response,
    )

    return serialize_response(payload, guest_contact=guest_contact)


@pytest.mark.parametrize("guest_contact", [False, True])
def test_profile_picture_never_survives(guest_contact: bool) -> None:
    """``profile_picture`` is dropped unconditionally, at any depth.

    There is NO opt-in that re-enables it. It is a third-party CDN URL
    that leaks a guest's likeness to anyone who can read the response.
    """
    from tests.helpers import load_fixture

    payload = load_fixture("reservation_with_guest.json")
    assert "profile_picture" in repr(payload)

    filtered = _serialize(payload, guest_contact=guest_contact)

    assert "profile_picture" not in repr(filtered)


def test_guest_contact_details_are_withheld_by_default() -> None:
    """``email`` and ``phone_numbers`` need the explicit opt-in."""
    from tests.helpers import load_fixture

    payload = load_fixture("reservation_with_guest.json")

    filtered = _serialize(payload, guest_contact=False)

    assert "email" not in repr(filtered)
    assert "phone_numbers" not in repr(filtered)


def test_guest_contact_details_appear_only_with_the_opt_in() -> None:
    """With the opt-in on, contact details are released."""
    from tests.helpers import load_fixture

    payload = load_fixture("reservation_with_guest.json")

    filtered = _serialize(payload, guest_contact=True)
    guest = filtered["data"][0]["guest"]

    assert guest["email"] == "guest@example.com"
    assert guest["phone_numbers"] == ["+15550101001"]
    assert "profile_picture" not in guest


def test_guest_fields_are_allowlisted_not_denylisted() -> None:
    """Unknown guest fields are dropped rather than passed through.

    A denylist fails open: a field upstream adds tomorrow ships to users
    unfiltered. An allowlist fails closed.
    """
    payload = {
        "guest": {
            "first_name": "Example",
            "last_name": "Guest",
            "location": "Example City",
            "language": "en",
            "passport_number": "X0000000",
            "date_of_birth": "1990-01-01",
        }
    }

    filtered = _serialize(payload, guest_contact=True)

    assert set(filtered["guest"]) == {
        "first_name",
        "last_name",
        "location",
        "language",
    }


def test_the_message_sender_object_is_covered_too() -> None:
    """The opaque ``sender`` object on a message is filtered as well.

    The messages fixture carries email, phone and a profile picture
    inside ``sender``. Filtering only ``guest`` would leak all of it.
    """
    from tests.helpers import load_fixture

    payload = load_fixture("messages_thread.json")
    assert "profile_picture" in repr(payload)

    filtered = _serialize(payload, guest_contact=False)

    rendered = repr(filtered)
    assert "profile_picture" not in rendered
    assert "@example.com" not in rendered
    assert "+1555" not in rendered


def test_non_identifying_message_metadata_survives() -> None:
    """Filtering removes identity, not the data the response is for.

    Without this the serialiser could trivially satisfy every privacy
    assertion above by returning an empty payload.
    """
    from tests.helpers import load_fixture

    payload = load_fixture("messages_thread.json")

    filtered = _serialize(payload, guest_contact=False)

    messages = filtered["data"]
    assert len(messages) == len(payload["data"])
    for original, cleaned in zip(payload["data"], messages, strict=True):
        assert cleaned["id"] == original["id"]
        assert cleaned["body"] == original["body"]


def test_lists_and_nesting_are_walked() -> None:
    """The filter is recursive over both dicts and lists."""
    payload = {"a": [{"b": [{"guest": {"profile_picture": "https://example.com/x"}}]}]}

    filtered = _serialize(payload)

    assert "profile_picture" not in repr(filtered)


async def test_the_send_message_response_goes_through_the_chokepoint(
    hass: Any,
    loaded_config_entry_factory: Any,
    messages_routes: Any,
) -> None:
    """``send_message`` routes its response through the shared serialiser.

    Asserted by patching the single chokepoint and observing that the
    handler's output came through it. If a handler ever builds a
    response directly, this fails.
    """
    from unittest.mock import patch

    from custom_components.hospitable.const import DOMAIN
    from tests.actions.conftest import RESERVATION_A
    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "send_message"), (
        "hospitable.send_message is not registered"
    )
    messages_routes.post(
        RESERVATION_A, json_body=load_fixture("send_message_202_full.json")
    )

    with patch(
        "custom_components.hospitable.actions.response.serialize_response",
        return_value={"sentinel": True},
    ) as chokepoint:
        response = await hass.services.async_call(
            DOMAIN,
            "send_message",
            {"reservation_uuid": RESERVATION_A, "body": "Synthetic."},
            blocking=True,
            return_response=True,
        )

    assert chokepoint.called
    assert response == {"sentinel": True}


def test_every_registered_handler_is_wired_to_the_chokepoint() -> None:
    """No handler module builds a response outside the serialiser.

    A static check, because a runtime check can only cover the handlers a
    test happens to call. This is the property that makes the chokepoint
    a chokepoint rather than a convention.
    """
    from pathlib import Path

    from custom_components.hospitable.actions import (
        SERVICE_DEFINITIONS,
    )
    from tests.helpers.ast_isolation import scan_module

    actions_root = Path("custom_components/hospitable/actions")
    for definition in SERVICE_DEFINITIONS:
        module = actions_root / f"{definition.name}.py"
        assert module.is_file(), f"no handler module for {definition.name}"
        facts = scan_module(module)
        assert facts.references("serialize_response"), definition.name
