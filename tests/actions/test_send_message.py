# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for ``hospitable.send_message`` (T030-T036).

A 202 means ACCEPTED FOR DELIVERY, not delivered (FR-011). The send is
asynchronous and ``sent_reference_id`` is the correlation handle, so
every assertion here is about acceptance and correlation, never about
a message having reached a guest.

Unverified questions this file must NOT resolve by assertion:

* OQ-001 — the true 202 body shape is unknown. Both fixture shapes are
  exercised; neither is asserted to be the real one.
* OQ-005 — whether the PAT carries a send scope is unestablished. The
  403 test asserts the error is actionable, not that the scope is
  absent.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest
import respx

from tests.actions.conftest import RESERVATION_A

RESERVATION_AIRBNB = "res-example-guest-full"
RESERVATION_BOOKING = "res-example-guest-no-surname"
RESERVATION_NO_PLATFORM = "res-example-guest-null"

# Every service-bus test asserts the service is registered BEFORE it
# does anything else. Home Assistant's ``ServiceNotFound`` is a SUBCLASS
# of ``ServiceValidationError``, so a negative test wrapping the call in
# ``pytest.raises(ServiceValidationError)`` would otherwise swallow the
# missing-service failure and XPASS for entirely the wrong reason. The
# precondition makes the red-phase failure a real ``AssertionError``
# against real behaviour, which is also what Principle XII asks for
# wherever the surrounding modules already exist. This is a deliberate
# deviation from the ``raises=ModuleNotFoundError`` written in tasks.md.
XFAIL_RED = pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: hospitable.send_message is not registered yet",
)
XFAIL_RED_IMPORT = pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: the shared envelope parser does not exist yet",
)


async def _call(hass: Any, data: dict[str, Any]) -> Any:
    """Invoke ``hospitable.send_message`` through the real service bus.

    Args:
        hass: Home Assistant instance.
        data: Service call data.

    Returns:
        The service response.
    """
    from custom_components.hospitable.const import DOMAIN

    assert hass.services.has_service(DOMAIN, "send_message"), (
        "hospitable.send_message is not registered"
    )
    return await hass.services.async_call(
        DOMAIN, "send_message", data, blocking=True, return_response=True
    )


@XFAIL_RED
async def test_reservation_uuid_target_is_accepted(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """A reservation UUID may be given directly."""
    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    route = messages_routes.post(
        RESERVATION_A, json_body=load_fixture("send_message_202_full.json")
    )

    response = await _call(
        hass, {"reservation_uuid": RESERVATION_A, "body": "Synthetic message."}
    )

    assert route.called
    assert response["reservation_uuid"] == RESERVATION_A


@XFAIL_RED
async def test_entity_id_target_resolves_to_a_reservation_uuid(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    seed_reservations: Callable[..., list[Any]],
    messages_routes: Any,
) -> None:
    """An entity belonging to this integration resolves to its UUID.

    The reservation UUID is exposed on the sensor as the
    ``reservation_id`` attribute — NOT ``reservation_uuid`` as
    ``contracts/services.md`` and D-10 state. The service FIELD keeps the
    contract's name; only the attribute read differs.
    """
    from tests.helpers import load_fixture

    entry = await loaded_config_entry_factory(hass)
    coordinator = entry.runtime_data["coordinators"]["reservations"]
    coordinator.async_set_updated_data(seed_reservations(entry, seed_only=True))
    await hass.async_block_till_done()
    candidates = [
        state
        for state in hass.states.async_all()
        if state.entity_id.startswith("sensor.")
        and state.attributes.get("reservation_id")
    ]
    assert candidates, "no reservation-bearing entity was created"
    entity = candidates[0]
    reservation_uuid = entity.attributes["reservation_id"]
    route = messages_routes.post(
        reservation_uuid, json_body=load_fixture("send_message_202_full.json")
    )

    response = await _call(
        hass, {"entity_id": entity.entity_id, "body": "Synthetic message."}
    )

    assert route.called
    assert response["reservation_uuid"] == reservation_uuid


@XFAIL_RED
async def test_foreign_entity_id_is_rejected(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    respx_router: respx.Router,
) -> None:
    """An entity that is not ours cannot select a reservation."""
    from homeassistant.exceptions import ServiceValidationError

    await loaded_config_entry_factory(hass)
    hass.states.async_set("sensor.not_ours", "on", {"reservation_id": RESERVATION_A})
    before = len(respx_router.calls)

    with pytest.raises(ServiceValidationError):
        await _call(hass, {"entity_id": "sensor.not_ours", "body": "Synthetic."})

    assert len(respx_router.calls) == before


@XFAIL_RED
async def test_both_targets_at_once_is_rejected(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """Supplying both target forms is ambiguous, so it is refused."""
    from homeassistant.exceptions import ServiceValidationError

    await loaded_config_entry_factory(hass)

    with pytest.raises(ServiceValidationError):
        await _call(
            hass,
            {
                "entity_id": "sensor.anything",
                "reservation_uuid": RESERVATION_A,
                "body": "Synthetic.",
            },
        )


@XFAIL_RED
async def test_happy_path_reports_acceptance_not_delivery(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """A 202 is reported as accepted for delivery, never as delivered."""
    from tests.helpers import load_fixture
    from tests.helpers.language import assert_payload_has_no_delivery_language

    await loaded_config_entry_factory(hass)
    messages_routes.post(
        RESERVATION_A, json_body=load_fixture("send_message_202_full.json")
    )

    response = await _call(
        hass, {"reservation_uuid": RESERVATION_A, "body": "Synthetic message."}
    )

    assert response["accepted"] is True
    assert "delivered" not in response
    assert "sent" not in response
    assert_payload_has_no_delivery_language(response)


@XFAIL_RED
@pytest.mark.parametrize(
    ("fixture", "expected_reference"),
    [
        ("send_message_202_full.json", "sent-ref-example-0001"),
        ("send_message_202_empty.json", None),
    ],
)
async def test_correlation_handle_is_surfaced_or_absent_without_error(
    fixture: str,
    expected_reference: str | None,
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """``sent_reference_id`` is surfaced when present, else null.

    OQ-001 is UNVERIFIED. Both shapes are handled; neither is asserted
    to be the shape the live API actually returns.
    """
    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    messages_routes.post(RESERVATION_A, json_body=load_fixture(fixture))

    response = await _call(
        hass, {"reservation_uuid": RESERVATION_A, "body": "Synthetic message."}
    )

    assert response["accepted"] is True
    assert response["sent_reference_id"] == expected_reference


@XFAIL_RED
async def test_a_202_with_an_empty_body_is_not_an_error(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """A 202 carrying no body at all is still an acceptance.

    OQ-001 leaves the body shape open, including the possibility of no
    body. Acceptance is signalled by the status code.
    """
    await loaded_config_entry_factory(hass)
    messages_routes.post(RESERVATION_A, status=202, content="")

    response = await _call(
        hass, {"reservation_uuid": RESERVATION_A, "body": "Synthetic message."}
    )

    assert response["accepted"] is True
    assert response["sent_reference_id"] is None


@XFAIL_RED
async def test_body_is_required_and_must_be_non_empty(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    respx_router: respx.Router,
) -> None:
    """An absent or blank body never reaches the API."""
    import voluptuous as vol
    from homeassistant.exceptions import ServiceValidationError

    await loaded_config_entry_factory(hass)
    before = len(respx_router.calls)

    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await _call(hass, {"reservation_uuid": RESERVATION_A})
    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await _call(hass, {"reservation_uuid": RESERVATION_A, "body": "   "})

    assert len(respx_router.calls) == before


@XFAIL_RED
async def test_body_is_transmitted_verbatim(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """The body reaches the API unaltered.

    The upstream docs render "/n is parsed for line breaks". That is a
    typographical error for ``\\n``; no literal ``/n`` substitution is
    performed here, so a body containing ``/n`` must survive intact.
    """
    import json

    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    route = messages_routes.post(
        RESERVATION_A, json_body=load_fixture("send_message_202_full.json")
    )
    text = "Line one/n still line one\nline two"

    await _call(hass, {"reservation_uuid": RESERVATION_A, "body": text})

    sent = json.loads(route.calls[0].request.content)
    assert sent["body"] == text


@XFAIL_RED
async def test_images_are_optional_and_capped_at_three(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """Up to three image URIs are accepted; a fourth is refused."""
    import json

    import voluptuous as vol
    from homeassistant.exceptions import ServiceValidationError

    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    route = messages_routes.post(
        RESERVATION_A, json_body=load_fixture("send_message_202_full.json")
    )
    images = [f"https://example.com/image-{index}.png" for index in range(4)]

    await _call(
        hass,
        {
            "reservation_uuid": RESERVATION_A,
            "body": "Synthetic.",
            "images": images[:3],
        },
    )
    sent = json.loads(route.calls[0].request.content)
    assert sent["images"] == images[:3]

    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await _call(
            hass,
            {
                "reservation_uuid": RESERVATION_A,
                "body": "Synthetic.",
                "images": images,
            },
        )


@XFAIL_RED
async def test_optional_fields_are_omitted_when_not_supplied(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """An unsupplied optional field is absent from the request body."""
    import json

    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    route = messages_routes.post(
        RESERVATION_A, json_body=load_fixture("send_message_202_full.json")
    )

    await _call(hass, {"reservation_uuid": RESERVATION_A, "body": "Synthetic."})

    sent = json.loads(route.calls[0].request.content)
    assert set(sent) == {"body"}


@XFAIL_RED
async def test_sender_id_is_accepted_for_an_airbnb_reservation(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    seed_reservations: Callable[..., list[Any]],
    messages_routes: Any,
) -> None:
    """An Airbnb reservation may carry ``sender_id``.

    The upstream ``platform`` value is carried on the model under the
    field name ``channel`` (``api/models.py:173``), so the check keys off
    ``channel``; no new field is introduced.
    """
    import json

    from tests.helpers import load_fixture

    entry = await loaded_config_entry_factory(hass)
    reservations = seed_reservations(entry)
    airbnb = next(r for r in reservations if r.reservation_id == RESERVATION_AIRBNB)
    assert airbnb.channel == "airbnb"
    route = messages_routes.post(
        RESERVATION_AIRBNB, json_body=load_fixture("send_message_202_full.json")
    )

    await _call(
        hass,
        {
            "reservation_uuid": RESERVATION_AIRBNB,
            "body": "Synthetic.",
            "sender_id": "sender-example-0001",
        },
    )

    sent = json.loads(route.calls[0].request.content)
    assert sent["sender_id"] == "sender-example-0001"


@XFAIL_RED
@pytest.mark.parametrize(
    "reservation_uuid", [RESERVATION_BOOKING, RESERVATION_NO_PLATFORM]
)
async def test_sender_id_is_rejected_when_not_airbnb_or_unresolved(
    reservation_uuid: str,
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    seed_reservations: Callable[..., list[Any]],
    messages_routes: Any,
    respx_router: respx.Router,
) -> None:
    """``sender_id`` is Airbnb-only, and a null channel is UNRESOLVED.

    A ``None`` channel means the platform could not be determined. That
    is a rejection, NOT "not Airbnb, proceed anyway" — proceeding would
    send a field the channel may not accept.
    """
    from homeassistant.exceptions import ServiceValidationError

    entry = await loaded_config_entry_factory(hass)
    seed_reservations(entry)
    route = messages_routes.post(reservation_uuid, status=202, content="")
    before = len(respx_router.calls)

    with pytest.raises(ServiceValidationError):
        await _call(
            hass,
            {
                "reservation_uuid": reservation_uuid,
                "body": "Synthetic.",
                "sender_id": "sender-example-0001",
            },
        )

    assert not route.called
    assert len(respx_router.calls) == before


@XFAIL_RED
async def test_no_sender_id_performs_no_platform_lookup(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
    respx_router: respx.Router,
) -> None:
    """Without ``sender_id`` the platform is irrelevant, so it is not read.

    The reservation here is deliberately NOT cached: if the handler
    looked the platform up unconditionally it would have to issue a GET,
    and this test would see it.
    """
    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    messages_routes.post(
        RESERVATION_AIRBNB, json_body=load_fixture("send_message_202_full.json")
    )
    before = len(respx_router.calls)

    await _call(hass, {"reservation_uuid": RESERVATION_AIRBNB, "body": "Synthetic."})

    new_calls = list(respx_router.calls)[before:]
    assert len(new_calls) == 1
    assert new_calls[0].request.method == "POST"


@XFAIL_RED
async def test_cached_reservation_needs_no_platform_lookup(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    seed_reservations: Callable[..., list[Any]],
    messages_routes: Any,
    respx_router: respx.Router,
) -> None:
    """A cached reservation supplies its own channel."""
    from tests.helpers import load_fixture

    entry = await loaded_config_entry_factory(hass)
    seed_reservations(entry)
    messages_routes.post(
        RESERVATION_AIRBNB, json_body=load_fixture("send_message_202_full.json")
    )
    before = len(respx_router.calls)

    await _call(
        hass,
        {
            "reservation_uuid": RESERVATION_AIRBNB,
            "body": "Synthetic.",
            "sender_id": "sender-example-0001",
        },
    )

    new_calls = list(respx_router.calls)[before:]
    assert [call.request.method for call in new_calls] == ["POST"]


@XFAIL_RED
async def test_uncached_reservation_costs_exactly_one_lookup(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
    respx_router: respx.Router,
) -> None:
    """An uncached reservation is resolved with a single GET."""
    from custom_components.hospitable.api.const import BASE_URL
    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    payload = load_fixture("reservation_with_guest.json")
    single = {"data": payload["data"][0]}
    lookup = respx_router.get(f"{BASE_URL}/reservations/{RESERVATION_AIRBNB}").mock(
        return_value=httpx.Response(200, json=single)
    )
    messages_routes.post(
        RESERVATION_AIRBNB, json_body=load_fixture("send_message_202_full.json")
    )

    await _call(
        hass,
        {
            "reservation_uuid": RESERVATION_AIRBNB,
            "body": "Synthetic.",
            "sender_id": "sender-example-0001",
        },
    )

    assert lookup.call_count == 1


@XFAIL_RED
@pytest.mark.parametrize("status", [404, 500])
async def test_failed_platform_lookup_rejects_without_sending(
    status: int,
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
    respx_router: respx.Router,
) -> None:
    """An unresolvable platform refuses the call and issues no POST."""
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.hospitable.api.const import BASE_URL

    await loaded_config_entry_factory(hass)
    respx_router.get(f"{BASE_URL}/reservations/{RESERVATION_AIRBNB}").mock(
        return_value=httpx.Response(status, json={"message": "nope"})
    )
    route = messages_routes.post(RESERVATION_AIRBNB, status=202, content="")

    with pytest.raises(ServiceValidationError):
        await _call(
            hass,
            {
                "reservation_uuid": RESERVATION_AIRBNB,
                "body": "Synthetic.",
                "sender_id": "sender-example-0001",
            },
        )

    assert not route.called


@XFAIL_RED
async def test_422_maps_to_service_validation_error_with_field_messages(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """A Laravel 422 becomes a user-fixable error keeping field detail."""
    from homeassistant.exceptions import ServiceValidationError

    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    envelope = load_fixture("error_envelope_422.json")
    messages_routes.post(RESERVATION_A, status=422, json_body=envelope)

    with pytest.raises(ServiceValidationError) as excinfo:
        await _call(hass, {"reservation_uuid": RESERVATION_A, "body": "Synthetic."})

    rendered = str(excinfo.value)
    for messages in envelope["errors"].values():
        for message in messages:
            assert message in rendered


@XFAIL_RED_IMPORT
async def test_400_and_422_share_one_envelope_parser() -> None:
    """One parser serves the ``/tasks`` 400 and the send 422 alike."""
    from custom_components.hospitable.api.responses import (  # type: ignore[attr-defined]
        parse_error_envelope,
    )
    from tests.helpers import load_fixture

    for fixture in ("error_envelope_400.json", "error_envelope_422.json"):
        envelope = load_fixture(fixture)
        parsed = parse_error_envelope(envelope)
        assert parsed.status_code == envelope["status_code"]
        assert parsed.reason_phrase == envelope["reason_phrase"]
        assert parsed.errors == envelope["errors"]


@XFAIL_RED_IMPORT
async def test_envelope_parser_tolerates_a_missing_errors_key() -> None:
    """The observed 429 body has no ``errors`` key and must not raise."""
    from custom_components.hospitable.api.responses import (  # type: ignore[attr-defined]
        parse_error_envelope,
    )
    from tests.helpers import load_fixture

    envelope = load_fixture("error_envelope_429.json")
    assert "errors" not in envelope

    parsed = parse_error_envelope(envelope)

    assert parsed.status_code == 429
    assert parsed.reason_phrase == "Too Many Attempts."
    assert parsed.errors == {}


@XFAIL_RED
@pytest.mark.parametrize("status", [500, 502, 503])
async def test_server_errors_map_to_home_assistant_error(
    status: int,
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """A 5xx is a transient upstream failure, not a user mistake."""
    from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

    await loaded_config_entry_factory(hass)
    messages_routes.post(RESERVATION_A, status=status, json_body={"message": "boom"})

    with pytest.raises(HomeAssistantError) as excinfo:
        await _call(hass, {"reservation_uuid": RESERVATION_A, "body": "Synthetic."})

    assert not isinstance(excinfo.value, ServiceValidationError)


@XFAIL_RED
async def test_transport_failure_maps_to_home_assistant_error(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """A transport failure is a transient upstream failure."""
    from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

    await loaded_config_entry_factory(hass)
    messages_routes.post_sequence(RESERVATION_A, [httpx.ConnectError("boom")])

    with pytest.raises(HomeAssistantError) as excinfo:
        await _call(hass, {"reservation_uuid": RESERVATION_A, "body": "Synthetic."})

    assert not isinstance(excinfo.value, ServiceValidationError)


@XFAIL_RED
async def test_403_is_actionable_about_a_possible_missing_scope(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """A 403 tells the user the token MAY lack the send scope.

    OQ-005 is UNVERIFIED: no real send has been made, so this asserts
    only that the message is actionable and hedged, never that the PAT
    does or does not carry the scope.
    """
    from homeassistant.exceptions import HomeAssistantError

    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    messages_routes.post(
        RESERVATION_A, status=403, json_body=load_fixture("error_403_scope.json")
    )

    with pytest.raises(HomeAssistantError) as excinfo:
        await _call(hass, {"reservation_uuid": RESERVATION_A, "body": "Synthetic."})

    rendered = str(excinfo.value).lower()
    assert "scope" in rendered
    assert any(word in rendered for word in ("may", "might", "check"))
