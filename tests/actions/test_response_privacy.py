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


# --- US2: the chokepoint's scope is EVERY registered service ---------
#
# US1 front-loaded the serialiser but left T072a-T072e and T079a
# unticked, because with one service registered their scope could not be
# discharged. US2 adds four more, and these are exactly the services the
# analyze gate identified as the leak: they return reservation payloads
# fetched with ``include=guest``, whose guest object carries
# ``profile_picture``, ``email``, and ``phone_numbers``.
#
# The red-phase marker is ``AssertionError`` rather than the
# ``ModuleNotFoundError`` written into tasks.md: the ``actions`` package
# now exists, so an import error here would prove nothing. Each test
# asserts the service is registered before doing anything else.


RESERVATION_WITH_GUEST = "res-example-guest-full"
PROPERTY_A = "prop-example-001"
AUDITED_SERVICES = (
    "send_message",
    "get_messages",
    "find_reservation",
    "get_reservations",
    "get_property_info",
)


def _service_call_data(service: str) -> dict[str, Any]:
    """Return valid call data for one registered service.

    Args:
        service: Registered service name.

    Returns:
        Service call data.

    Raises:
        AssertionError: The service has no entry here. This is
            deliberate: a sixth service added later must be added to this
            table, so it cannot be omitted from the privacy audit by
            being forgotten.
    """
    from tests.actions.conftest import RESERVATION_A

    data: dict[str, dict[str, Any]] = {
        "send_message": {"reservation_uuid": RESERVATION_A, "body": "Synthetic."},
        "get_messages": {"reservation_uuid": RESERVATION_A},
        "find_reservation": {"reservation_uuid": RESERVATION_WITH_GUEST},
        "get_reservations": {"property_id": PROPERTY_A},
        "get_property_info": {"property_id": PROPERTY_A},
    }
    assert service in data, (
        f"service {service!r} has no privacy-audit call data; every "
        "registered service must be audited"
    )
    return data[service]


def _mock_every_service_endpoint(
    messages_routes: Any, lookup_routes: Any, *, guest_overrides: Any = None
) -> None:
    """Register upstream responses for every audited service.

    Args:
        messages_routes: Messages endpoint route builder.
        lookup_routes: Lookup endpoint route builder.
        guest_overrides: Extra keys merged into every guest object, used
            to simulate a new upstream field.
    """
    from tests.actions.conftest import RESERVATION_A
    from tests.helpers import load_fixture

    reservations = load_fixture("reservation_with_guest.json")
    if guest_overrides:
        for item in reservations["data"]:
            if isinstance(item.get("guest"), dict):
                item["guest"].update(guest_overrides)
    messages_routes.post(
        RESERVATION_A, json_body=load_fixture("send_message_202_full.json")
    )
    messages_routes.get(RESERVATION_A, json_body=load_fixture("messages_thread.json"))
    lookup_routes.reservation(
        RESERVATION_WITH_GUEST, json_body={"data": reservations["data"][0]}
    )
    lookup_routes.reservations(json_body=reservations)


async def _call_every_service(hass: Any) -> dict[str, Any]:
    """Call every registered service and collect the responses.

    Args:
        hass: Home Assistant instance.

    Returns:
        Each service's response, keyed by service name.
    """
    from custom_components.hospitable.actions import SERVICE_DEFINITIONS
    from custom_components.hospitable.const import DOMAIN

    responses: dict[str, Any] = {}
    for definition in SERVICE_DEFINITIONS:
        assert hass.services.has_service(DOMAIN, definition.name), (
            f"hospitable.{definition.name} is not registered"
        )
        responses[definition.name] = await hass.services.async_call(
            DOMAIN,
            definition.name,
            _service_call_data(definition.name),
            blocking=True,
            return_response=True,
        )
    return responses


@pytest.mark.parametrize("guest_contact", [False, True])
@pytest.mark.parametrize("awaiting_host_reply", [False, True])
async def test_profile_picture_is_absent_from_every_service_response(
    hass: Any,
    loaded_config_entry_factory: Any,
    messages_routes: Any,
    lookup_routes: Any,
    guest_contact: bool,
    awaiting_host_reply: bool,
) -> None:
    """No option combination lets ``profile_picture`` reach a caller.

    The services are enumerated from the registration table, not from a
    hard-coded list, so a sixth service added later is audited
    automatically. The fixtures DO carry a ``profile_picture``, on both
    the guest object and the message sender, so a pass-through fails
    here rather than silently succeeding.
    """
    from custom_components.hospitable.actions import SERVICE_DEFINITIONS
    from custom_components.hospitable.const import (
        CONF_AWAITING_HOST_REPLY,
        CONF_GUEST_CONTACT_DETAILS,
    )

    _mock_every_service_endpoint(messages_routes, lookup_routes)
    await loaded_config_entry_factory(
        hass,
        options={
            CONF_GUEST_CONTACT_DETAILS: guest_contact,
            CONF_AWAITING_HOST_REPLY: awaiting_host_reply,
        },
    )

    registered = {definition.name for definition in SERVICE_DEFINITIONS}
    assert registered == set(AUDITED_SERVICES), (
        "the registration table does not yet hold every audited service"
    )

    responses = await _call_every_service(hass)

    assert set(responses) == registered, "not every registered service was audited"
    for name, response in responses.items():
        assert "profile_picture" not in repr(response), name


@pytest.mark.parametrize("service", ["find_reservation", "get_reservations"])
async def test_contact_details_are_withheld_unless_the_option_is_on(
    hass: Any,
    loaded_config_entry_factory: Any,
    messages_routes: Any,
    lookup_routes: Any,
    service: str,
) -> None:
    """Contact details are gated; identity and locale are not.

    This is the service-response half of the control whose
    entity-attribute half is FR-039c. The positive half matters as much
    as the negative one: a serialiser that returned nothing would satisfy
    a withholding assertion and be useless.
    """
    from custom_components.hospitable.const import CONF_GUEST_CONTACT_DETAILS, DOMAIN

    _mock_every_service_endpoint(messages_routes, lookup_routes)
    await loaded_config_entry_factory(hass, options={CONF_GUEST_CONTACT_DETAILS: False})
    assert hass.services.has_service(DOMAIN, service), (
        f"hospitable.{service} is not registered"
    )

    withheld = await hass.services.async_call(
        DOMAIN,
        service,
        _service_call_data(service),
        blocking=True,
        return_response=True,
    )

    assert "email" not in repr(withheld), service
    assert "phone_numbers" not in repr(withheld), service
    assert "guest@example.com" not in repr(withheld), service
    assert "Example City" in repr(withheld), "location must survive the filter"
    assert "Example" in repr(withheld), "first_name must survive the filter"


@pytest.mark.parametrize("service", ["find_reservation", "get_reservations"])
async def test_contact_details_are_released_with_the_option_on(
    hass: Any,
    loaded_config_entry_factory: Any,
    messages_routes: Any,
    lookup_routes: Any,
    service: str,
) -> None:
    """With the opt-in on, contact details join the identity fields."""
    from custom_components.hospitable.const import CONF_GUEST_CONTACT_DETAILS, DOMAIN

    _mock_every_service_endpoint(messages_routes, lookup_routes)
    await loaded_config_entry_factory(hass, options={CONF_GUEST_CONTACT_DETAILS: True})
    assert hass.services.has_service(DOMAIN, service), (
        f"hospitable.{service} is not registered"
    )

    released = await hass.services.async_call(
        DOMAIN,
        service,
        _service_call_data(service),
        blocking=True,
        return_response=True,
    )

    rendered = repr(released)
    assert "guest@example.com" in rendered, service
    assert "+15550101001" in rendered, service
    assert "Example City" in rendered, service
    assert "profile_picture" not in rendered, "the opt-in never releases this"


async def test_a_new_upstream_guest_key_is_dropped(
    hass: Any,
    loaded_config_entry_factory: Any,
    messages_routes: Any,
    lookup_routes: Any,
) -> None:
    """An unrecognised guest key never reaches a service caller.

    The serialiser is an allowlist. A denylist would ship the next PII
    field Hospitable adds, by default, to every automation trace.
    """
    from custom_components.hospitable.const import CONF_GUEST_CONTACT_DETAILS, DOMAIN

    _mock_every_service_endpoint(
        messages_routes,
        lookup_routes,
        guest_overrides={"passport_number": "X0000000", "date_of_birth": "1990-01-01"},
    )
    await loaded_config_entry_factory(hass, options={CONF_GUEST_CONTACT_DETAILS: True})
    assert hass.services.has_service(DOMAIN, "find_reservation"), (
        "hospitable.find_reservation is not registered"
    )

    response = await hass.services.async_call(
        DOMAIN,
        "find_reservation",
        _service_call_data("find_reservation"),
        blocking=True,
        return_response=True,
    )

    rendered = repr(response)
    assert "passport_number" not in rendered
    assert "X0000000" not in rendered
    assert "date_of_birth" not in rendered


async def test_get_messages_returns_roles_but_never_the_sender_object(
    hass: Any,
    loaded_config_entry_factory: Any,
    messages_routes: Any,
    lookup_routes: Any,
) -> None:
    """``sender`` is opaque and is dropped; the role discriminators stay.

    ``sender`` may carry guest identity and contact fields, so it is
    subject to FR-047 on the same terms. ``sender_type`` and
    ``sender_role`` are roles, not identity.
    """
    from custom_components.hospitable.const import DOMAIN

    _mock_every_service_endpoint(messages_routes, lookup_routes)
    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "get_messages"), (
        "hospitable.get_messages is not registered"
    )

    response = await hass.services.async_call(
        DOMAIN,
        "get_messages",
        _service_call_data("get_messages"),
        blocking=True,
        return_response=True,
    )

    messages = response["messages"]
    assert messages, "no messages were returned"
    for message in messages:
        assert "sender" not in message, "the opaque sender object must be dropped"
        assert message["sender_type"] in {"host", "guest", "system"}
        assert "sender_role" in message


def test_the_serialiser_drops_sender_outright() -> None:
    """``sender`` is DROPPED, not reduced to an allowlist.

    FR-047a is stricter than FR-047: no part of the sender object is
    returnable, because nothing in it is a role discriminator — the
    discriminators are siblings of it, not members.
    """
    payload = {
        "sender": {"first_name": "Example", "last_name": "Host", "id": "user-example"},
        "sender_type": "host",
        "sender_role": "host",
    }

    filtered = _serialize(payload, guest_contact=True)

    assert "sender" not in filtered
    assert filtered["sender_type"] == "host"
    assert filtered["sender_role"] == "host"


@pytest.mark.parametrize(
    "service",
    [
        "send_message",
        "get_messages",
        "find_reservation",
        "get_reservations",
        "get_property_info",
    ],
)
async def test_every_service_response_comes_out_of_the_chokepoint(
    hass: Any,
    loaded_config_entry_factory: Any,
    messages_routes: Any,
    lookup_routes: Any,
    service: str,
) -> None:
    """Each service's returned payload is the serialiser's output.

    Patching the single chokepoint and observing the sentinel come back
    is the runtime half of the guarantee; the AST scan below is the
    static half that covers handlers no test happens to call.
    """
    from unittest.mock import patch

    from custom_components.hospitable.const import DOMAIN

    _mock_every_service_endpoint(messages_routes, lookup_routes)
    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, service), (
        f"hospitable.{service} is not registered"
    )

    with patch(
        "custom_components.hospitable.actions.response.serialize_response",
        return_value={"sentinel": service},
    ) as chokepoint:
        response = await hass.services.async_call(
            DOMAIN,
            service,
            _service_call_data(service),
            blocking=True,
            return_response=True,
        )

    assert chokepoint.called, service
    assert response == {"sentinel": service}, service


def test_the_audited_service_set_matches_the_registration_table() -> None:
    """The privacy audit covers every service the table declares.

    Without this, a sixth service could be registered and silently escape
    every assertion in this file.
    """
    from custom_components.hospitable.actions import SERVICE_DEFINITIONS

    names = {definition.name for definition in SERVICE_DEFINITIONS}

    assert names == set(AUDITED_SERVICES)
    for name in names:
        assert _service_call_data(name)
