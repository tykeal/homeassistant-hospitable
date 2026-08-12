# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for ``hospitable.get_messages`` (T061-T066).

``GET /reservations/{uuid}/messages`` is NOT paginated: the envelope
carries ``data`` only, with no ``meta`` and no ``links``, and ``page``
and ``per_page`` are silently ignored upstream. OQ-002 is closed to that
extent and no further: the busiest conversation ever observed held ten
messages, so behaviour above that volume is UNOBSERVED. These tests
therefore assert single-request consumption AND tolerance of a
``meta``/``links`` block that might appear later — the second is a
forward-compatibility guard, not an expectation of pagination.

Every test drives the REAL service bus and asserts the service is
registered first. Home Assistant's ``ServiceNotFound`` subclasses
``ServiceValidationError``, so a negative test that wrapped the call in
``pytest.raises(ServiceValidationError)`` would XPASS merely because the
service is missing. The precondition makes the red-phase failure a real
``AssertionError`` against real behaviour, which is what Principle XII
asks for once the surrounding modules exist. This is a deliberate,
disclosed deviation from the ``raises=ModuleNotFoundError`` written into
tasks.md, which was drafted before the ``actions/`` package existed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest

from tests.actions.conftest import RESERVATION_A, RESERVATION_B


async def _call(hass: Any, data: dict[str, Any]) -> Any:
    """Invoke ``hospitable.get_messages`` through the real service bus.

    Args:
        hass: Home Assistant instance.
        data: Service call data.

    Returns:
        The service response.
    """
    from custom_components.hospitable.const import DOMAIN

    assert hass.services.has_service(DOMAIN, "get_messages"), (
        "hospitable.get_messages is not registered"
    )
    return await hass.services.async_call(
        DOMAIN, "get_messages", data, blocking=True, return_response=True
    )


def _big_thread(count: int) -> dict[str, Any]:
    """Build a thread envelope holding ``count`` synthetic messages.

    Args:
        count: Number of messages to generate.

    Returns:
        A ``{data}`` envelope with no ``meta`` and no ``links``.
    """
    return {
        "data": [
            {
                "id": 800000 + index,
                "platform": "airbnb",
                "conversation_id": "conv-example-0001",
                "content_type": "text",
                "body": f"Synthetic message {index}.",
                "attachments": [],
                "sender_type": "guest" if index % 2 else "host",
                "sender_role": "guest" if index % 2 else "host",
                "sender": {"id": "user-example", "first_name": "Example"},
                "created_at": "2025-06-10T09:00:00Z",
                "source": "hospitable",
            }
            for index in range(count)
        ]
    }


async def test_thread_is_returned_in_upstream_order(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """The thread is returned with timestamps and roles preserved."""
    from tests.helpers import load_fixture

    payload = load_fixture("messages_thread.json")
    await loaded_config_entry_factory(hass)
    route = messages_routes.get(RESERVATION_A, json_body=payload)

    response = await _call(hass, {"reservation_uuid": RESERVATION_A})

    assert route.called
    assert response["found"] is True
    assert response["reservation_uuid"] == RESERVATION_A
    messages = response["messages"]
    assert [message["id"] for message in messages] == [
        item["id"] for item in payload["data"]
    ]
    assert [message["created_at"] for message in messages] == [
        item["created_at"] for item in payload["data"]
    ]
    assert [message["sender_role"] for message in messages] == [
        item["sender_role"] for item in payload["data"]
    ]
    assert [message["body"] for message in messages] == [
        item["body"] for item in payload["data"]
    ]


async def test_service_is_declared_response_only(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """The service returns structured data and fires no event."""
    from homeassistant.core import SupportsResponse

    from custom_components.hospitable.const import DOMAIN

    await loaded_config_entry_factory(hass)

    assert hass.services.has_service(DOMAIN, "get_messages"), (
        "hospitable.get_messages is not registered"
    )
    service = hass.services.async_services_for_domain(DOMAIN)["get_messages"]
    assert service.supports_response is SupportsResponse.ONLY


async def test_reservation_uuid_target_is_accepted(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """A reservation UUID may be given directly."""
    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    route = messages_routes.get(
        RESERVATION_A, json_body=load_fixture("messages_thread.json")
    )

    response = await _call(hass, {"reservation_uuid": RESERVATION_A})

    assert route.called
    assert response["reservation_uuid"] == RESERVATION_A


async def test_entity_id_target_resolves_to_a_reservation_uuid(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    seed_reservations: Callable[..., list[Any]],
    messages_routes: Any,
) -> None:
    """An entity belonging to this integration resolves to its UUID.

    The UUID is published as the ``reservation_id`` attribute; the
    service FIELD keeps the contract's ``reservation_uuid`` name.
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
    route = messages_routes.get(
        reservation_uuid, json_body=load_fixture("messages_thread.json")
    )

    response = await _call(hass, {"entity_id": entity.entity_id})

    assert route.called
    assert response["reservation_uuid"] == reservation_uuid


async def test_thread_is_consumed_in_exactly_one_request(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
    respx_router: Any,
) -> None:
    """One request, on an envelope carrying ``data`` only.

    OQ-002 is CLOSED: this endpoint is not paginated, unlike
    ``/reservations`` and ``/tasks``. No pagination loop may be written.
    """
    from tests.helpers import load_fixture

    payload = load_fixture("messages_thread.json")
    assert "meta" not in payload, "fixture must model the observed envelope"
    assert "links" not in payload, "fixture must model the observed envelope"
    await loaded_config_entry_factory(hass)
    messages_routes.get(RESERVATION_A, json_body=payload)
    before = len(respx_router.calls)

    await _call(hass, {"reservation_uuid": RESERVATION_A})

    issued = [
        call
        for call in list(respx_router.calls)[before:]
        if call.request.url.path.endswith(f"/reservations/{RESERVATION_A}/messages")
    ]
    assert len(issued) == 1, f"expected one request, got {len(issued)}"


async def test_page_and_per_page_are_never_sent(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
    respx_router: Any,
) -> None:
    """Neither pagination parameter reaches this endpoint.

    Both are SILENTLY IGNORED upstream, so sending them would create a
    false impression that the payload is bounded. It is not.
    """
    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    messages_routes.get(RESERVATION_A, json_body=load_fixture("messages_thread.json"))
    before = len(respx_router.calls)

    await _call(hass, {"reservation_uuid": RESERVATION_A})

    issued = [
        call
        for call in list(respx_router.calls)[before:]
        if call.request.url.path.endswith(f"/reservations/{RESERVATION_A}/messages")
    ]
    assert issued, "no messages request was issued"
    for call in issued:
        params = call.request.url.params
        assert "page" not in params, f"page was sent: {call.request.url}"
        assert "per_page" not in params, f"per_page was sent: {call.request.url}"


async def test_a_very_large_thread_is_returned_whole(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """A several-hundred-message thread is not truncated.

    There is no upstream mechanism to bound this response, so no code may
    assume a small list.
    """
    payload = _big_thread(500)
    await loaded_config_entry_factory(hass)
    messages_routes.get(RESERVATION_A, json_body=payload)

    response = await _call(hass, {"reservation_uuid": RESERVATION_A})

    assert len(response["messages"]) == 500
    assert response["messages"][-1]["id"] == payload["data"][-1]["id"]


async def test_an_unexpected_meta_block_is_tolerated(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
    respx_router: Any,
) -> None:
    """A ``meta``/``links`` block appearing later must not crash.

    Non-pagination was measured against a thread of only ten messages, so
    pagination above some unobserved threshold cannot be ruled out. This
    is a forward-compatibility guard: the extra block is survived, and
    the handler still issues exactly ONE request, because treating the
    block as a pagination cursor is precisely what must not happen.
    """
    from tests.helpers import load_fixture

    payload = load_fixture("messages_thread.json")
    payload["meta"] = {"current_page": 1, "last_page": 4, "per_page": 3, "total": 12}
    payload["links"] = [{"url": "https://example.invalid/?page=2", "label": "2"}]
    await loaded_config_entry_factory(hass)
    messages_routes.get(RESERVATION_A, json_body=payload)
    before = len(respx_router.calls)

    response = await _call(hass, {"reservation_uuid": RESERVATION_A})

    assert len(response["messages"]) == 3
    issued = [
        call
        for call in list(respx_router.calls)[before:]
        if call.request.url.path.endswith(f"/reservations/{RESERVATION_A}/messages")
    ]
    assert len(issued) == 1, "a meta block must not start a pagination loop"


async def test_the_per_reservation_budget_is_honoured(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """Two reads per sixty seconds per reservation, then a local refusal.

    The budget is per RESERVATION: a second reservation still has its
    own full allowance, which was proven upstream by exhausting one while
    the other returned 200.
    """
    from homeassistant.exceptions import ServiceValidationError

    from tests.helpers import load_fixture

    thread = load_fixture("messages_thread.json")
    await loaded_config_entry_factory(hass)
    messages_routes.get(RESERVATION_A, json_body=thread)
    messages_routes.get(RESERVATION_B, json_body=load_fixture("messages_empty.json"))

    await _call(hass, {"reservation_uuid": RESERVATION_A})
    await _call(hass, {"reservation_uuid": RESERVATION_A})
    with pytest.raises(ServiceValidationError):
        await _call(hass, {"reservation_uuid": RESERVATION_A})

    other = await _call(hass, {"reservation_uuid": RESERVATION_B})
    assert other["messages"] == []


async def test_an_upstream_429_is_reported_as_retryable(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """A 429 surfaces as a clear retryable error, not a crash or silence.

    An upstream refusal is distinct from a local pre-refusal: the caller
    is told to retry, and is NOT handed an empty thread that would read
    as "this reservation has no messages".
    """
    from homeassistant.exceptions import HomeAssistantError

    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    messages_routes.get(
        RESERVATION_A,
        status=429,
        json_body=load_fixture("error_envelope_429.json"),
        headers={"retry-after": "60", "x-ratelimit-reset": "1750000000"},
    )

    with pytest.raises(HomeAssistantError) as caught:
        await _call(hass, {"reservation_uuid": RESERVATION_A})

    assert "60" in str(caught.value)


async def test_message_bodies_never_reach_the_logs(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No log record at any level carries a message body.

    Message bodies are personal data. Returning them to the caller is the
    purpose of the service; writing them to a log file is not.
    """
    from tests.helpers import load_fixture

    payload = load_fixture("messages_thread.json")
    bodies = [item["body"] for item in payload["data"]]
    await loaded_config_entry_factory(hass)
    messages_routes.get(RESERVATION_A, json_body=payload)

    with caplog.at_level(logging.DEBUG):
        response = await _call(hass, {"reservation_uuid": RESERVATION_A})

    assert [message["body"] for message in response["messages"]] == bodies
    captured = "\n".join(record.getMessage() for record in caplog.records)
    for body in bodies:
        assert body not in captured, "a message body was logged"


async def test_an_empty_thread_returns_an_empty_collection(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """An empty thread is data, not an error."""
    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    messages_routes.get(RESERVATION_A, json_body=load_fixture("messages_empty.json"))

    response = await _call(hass, {"reservation_uuid": RESERVATION_A})

    assert response["found"] is True
    assert response["messages"] == []


async def test_an_unknown_reservation_is_a_return_value(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    messages_routes: Any,
) -> None:
    """A 404 is reported as ``found: false``, never as an exception."""
    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    messages_routes.get(
        RESERVATION_A, status=404, json_body=load_fixture("error_404.json")
    )

    response = await _call(hass, {"reservation_uuid": RESERVATION_A})

    assert response["found"] is False
    assert response["messages"] == []


async def test_a_transport_failure_raises_rather_than_returning_empty(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    respx_router: Any,
) -> None:
    """A network failure is an error, not an empty thread.

    Without this the not-found return value above could be satisfied by a
    handler that swallows every failure into ``found: false``.
    """
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.hospitable.api.const import BASE_URL

    await loaded_config_entry_factory(hass)
    respx_router.get(f"{BASE_URL}/reservations/{RESERVATION_A}/messages").mock(
        side_effect=httpx.ConnectError("synthetic transport failure")
    )

    with pytest.raises(HomeAssistantError):
        await _call(hass, {"reservation_uuid": RESERVATION_A})


async def test_the_read_path_never_builds_a_write_client() -> None:
    """``get_messages`` reads with the GET-only client.

    Write-isolation gate 3, extended to the new READ services: a lookup
    handler that reached for ``HospitableWriteClient`` would have a POST
    method it has no business owning.
    """
    from pathlib import Path

    from tests.helpers.ast_isolation import scan_module

    module = Path("custom_components/hospitable/actions/get_messages.py")
    assert module.is_file(), "the get_messages handler does not exist"
    facts = scan_module(module)
    assert not facts.references("HospitableWriteClient")
    assert not facts.references("_post")
