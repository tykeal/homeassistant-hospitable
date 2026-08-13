# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""A real config-entry harness carrying message presence data (US5).

Shared by every US5 test so they all drive the SAME wiring: a real
``hass``, a real ``MockConfigEntry``, real registries, and
``respx``-mocked endpoints. No request is ever made to the live host.

**Why the reservations payload is built rather than loaded.** The two
recorded reservations in ``reservations_page1.json`` both belong to
property one, and one of them is cancelled, so the recorded page cannot
by itself exercise a per-property message fan-out across two
properties. This harness therefore builds a two-property page from the
recorded reservation SHAPE, overriding only the identifiers, the
occupancy dates and ``last_message_at``. The dates are rebased on today
so "the operationally relevant reservation" keeps meaning the same
thing forever rather than only until the recorded dates pass.

**The message bodies here are deliberately distinctive.** ``PRIVATE_``
values are what makes the privacy assertions proof rather than
tautology: the harness serves a thread whose bodies really do flow
through the fetch, so an entity attribute or a log line that is clean
is clean because the control works, not because there was nothing to
leak.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from custom_components.hospitable.entity import build_unique_id
from tests.helpers import load_fixture

ACCOUNT = "acct-example-0001"
TOKEN = "hp_test_synthetic_token_000000000000000000000000"
ZONE = timezone(timedelta(hours=-7))

PROPERTY_A = "prop-example-001"
PROPERTY_B = "prop-example-002"
RESERVATION_A = "res-message-001"
RESERVATION_B = "res-message-002"

# Fixed instants, not "now" offsets: a timestamp sensor assertion has to
# name the exact value it expects, and these are never compared against
# the wall clock.
LAST_MESSAGE_AT_A = "2026-08-12T18:45:00+00:00"
LAST_MESSAGE_AT_B = "2026-08-11T09:15:00+00:00"

# Every message body the harness serves. Distinctive enough that a
# substring search over entity attributes and log records is proof
# rather than noise (T138, FR-024, FR-041).
PRIVATE_HOST_BODY = "Zephyrine quillfeather host greeting, synthetic."
PRIVATE_GUEST_BODY = "Quillfeather guest question about the synthetic gate code."
PRIVATE_BODIES = (PRIVATE_HOST_BODY, PRIVATE_GUEST_BODY)


def _reservation(
    reservation_id: str, property_id: str, last_message_at: str | None
) -> dict[str, Any]:
    """Build an accepted, mid-stay reservation for one property.

    Args:
        reservation_id: Reservation identifier to assign.
        property_id: Property the stay belongs to.
        last_message_at: Value for the ``last_message_at`` key.

    Returns:
        A reservation payload occupying the property right now, which
        makes it unambiguously the operationally relevant one.
    """
    today = datetime.now(ZONE).date()
    arrival = today - timedelta(days=1)
    departure = today + timedelta(days=2)
    payload: dict[str, Any] = copy.deepcopy(
        load_fixture("reservations_page1.json")["data"][0]
    )
    payload.update(
        {
            "id": reservation_id,
            "properties": [{"id": property_id}],
            "arrival_date": f"{arrival.isoformat()}T00:00:00-07:00",
            "departure_date": f"{departure.isoformat()}T00:00:00-07:00",
            "check_in": f"{arrival.isoformat()}T16:00:00-07:00",
            "check_out": f"{departure.isoformat()}T11:00:00-07:00",
            "last_message_at": last_message_at,
        }
    )
    return payload


def reservations_payload(
    *,
    last_message_at_a: str | None = LAST_MESSAGE_AT_A,
    last_message_at_b: str | None = LAST_MESSAGE_AT_B,
) -> dict[str, Any]:
    """Build a two-property, single-page reservations envelope.

    Args:
        last_message_at_a: Property A's reservation timestamp.
        last_message_at_b: Property B's reservation timestamp.

    Returns:
        A reservations envelope with exactly one live reservation per
        property, so the operationally relevant reservation for each is
        unambiguous.
    """
    return {
        "data": [
            _reservation(RESERVATION_A, PROPERTY_A, last_message_at_a),
            _reservation(RESERVATION_B, PROPERTY_B, last_message_at_b),
        ],
        "meta": {
            "current_page": 1,
            "last_page": 1,
            "path": "http://public.api.hospitable.com/v2/reservations",
            "per_page": 100,
            "total": 2,
        },
    }


def thread(*roles: str) -> dict[str, Any]:
    """Build a message thread whose senders follow the given roles.

    The recorded thread carries three messages authored host, guest,
    host. This re-labels a copy of it so a test can state the sender
    ORDER it needs without inventing a new message shape.

    Args:
        *roles: One ``host`` or ``guest`` per message, oldest first.

    Returns:
        A thread envelope in the recorded shape.
    """
    payload: dict[str, Any] = copy.deepcopy(load_fixture("messages_thread.json"))
    recorded = payload["data"]
    items: list[dict[str, Any]] = []
    for index, role in enumerate(roles):
        item = copy.deepcopy(recorded[index % len(recorded)])
        item["id"] = 900_100 + index
        item["sender_type"] = role
        item["sender_role"] = role
        item["created_at"] = f"2026-08-12T1{index}:00:00Z"
        item["body"] = PRIVATE_GUEST_BODY if role == "guest" else PRIVATE_HOST_BODY
        items.append(item)
    payload["data"] = items
    return payload


def empty_thread() -> Any:
    """Return the recorded empty-thread envelope.

    Returns:
        A thread envelope carrying no messages.
    """
    return load_fixture("messages_empty.json")


def _properties_side_effect(request: httpx.Request) -> httpx.Response:
    """Return the paginated properties fixture for the requested page.

    Args:
        request: The captured properties request.

    Returns:
        The fixture response for the requested page.
    """
    page = request.url.params.get("page", "1")
    fixture = "properties_page2.json" if page == "2" else "properties_page1.json"
    return httpx.Response(200, json=load_fixture(fixture))


def messages_url(reservation_uuid: str) -> str:
    """Return the thread URL for one reservation.

    Args:
        reservation_uuid: Target reservation UUID.

    Returns:
        The fully qualified messages endpoint URL.
    """
    return f"{BASE_URL}/reservations/{reservation_uuid}/messages"


def mock_base_endpoints(
    respx_router: Any, *, reservations: dict[str, Any] | None = None
) -> Any:
    """Mock every non-message GET endpoint the entry setup needs.

    ``/reservations/{uuid}/messages`` is deliberately NOT mocked here.
    A test that expects zero message traffic then fails loudly on an
    unmocked request rather than passing because a catch-all answered
    it (T133, FR-038).

    Args:
        respx_router: The active respx router.
        reservations: Reservations envelope to serve, defaulting to the
            two-property harness payload.

    Returns:
        The registered ``/reservations`` route.
    """
    respx_router.get(f"{BASE_URL}/properties").mock(side_effect=_properties_side_effect)
    route = respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(
            200,
            json=reservations if reservations is not None else reservations_payload(),
        )
    )
    for property_id, fixture in (
        (PROPERTY_A, "calendar_prop1.json"),
        (PROPERTY_B, "calendar_prop2.json"),
    ):
        respx_router.get(f"{BASE_URL}/properties/{property_id}/calendar").mock(
            return_value=httpx.Response(200, json=load_fixture(fixture))
        )
    respx_router.get(f"{BASE_URL}/tasks").mock(
        return_value=httpx.Response(200, json=load_fixture("tasks_empty.json"))
    )
    return route


# The success headers the messages endpoint returns. ``limit: 2`` is the
# CONFIRMED per-reservation budget; ``remaining: 1`` is what a first
# read in a fresh window leaves behind.
THREAD_HEADERS = {"x-ratelimit-limit": "2", "x-ratelimit-remaining": "1"}


def mock_threads(
    respx_router: Any, *, responses: dict[str, list[httpx.Response]] | None = None
) -> dict[str, Any]:
    """Mock the message thread endpoint per reservation.

    One route per reservation UUID, because the observed rate-limit
    buckets are per reservation and a shared route would hide that.

    Args:
        respx_router: The active respx router.
        responses: Per-reservation response script, consumed in order.
            The last response repeats once the script is exhausted.

    Returns:
        The registered routes keyed by reservation UUID.
    """
    script = responses
    if script is None:
        script = {
            RESERVATION_A: [
                httpx.Response(
                    200, json=thread("host", "guest"), headers=THREAD_HEADERS
                )
            ],
            RESERVATION_B: [
                httpx.Response(
                    200, json=thread("guest", "host"), headers=THREAD_HEADERS
                )
            ],
        }
    routes: dict[str, Any] = {}
    for reservation_uuid, planned in script.items():
        remaining = list(planned)

        def _side_effect(
            request: httpx.Request, _remaining: list[httpx.Response] = remaining
        ) -> httpx.Response:
            """Return the next scripted response for this reservation.

            Args:
                request: The captured request.
                _remaining: This reservation's unconsumed responses.

            Returns:
                The scripted response, repeating the last one.
            """
            _ = request
            if len(_remaining) > 1:
                return _remaining.pop(0)
            return _remaining[0]

        routes[reservation_uuid] = respx_router.get(
            messages_url(reservation_uuid)
        ).mock(side_effect=_side_effect)
    return routes


def throttled_response(*, retry_after: int = 60) -> httpx.Response:
    """Build the observed 429 response for the messages endpoint.

    Args:
        retry_after: ``retry-after`` seconds value.

    Returns:
        A 429 carrying the observed Laravel body, which has NO
        ``errors`` key, plus the observed throttling headers.
    """
    return httpx.Response(
        429,
        json=load_fixture("error_envelope_429.json"),
        headers={
            "x-ratelimit-limit": "2",
            "x-ratelimit-remaining": "0",
            "retry-after": str(retry_after),
        },
    )


def build_entry(**options: Any) -> MockConfigEntry:
    """Build an unloaded config entry selecting both example properties.

    Args:
        **options: Extra config-entry options to merge in.

    Returns:
        The config entry, not yet added to ``hass``.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: TOKEN,
            CONF_ACCOUNT_NAMESPACE: ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: [PROPERTY_A, PROPERTY_B],
            **options,
        },
        unique_id=ACCOUNT,
    )


async def setup_message_entry(hass: Any, **options: Any) -> MockConfigEntry:
    """Set up a loaded config entry against the harness routes.

    Args:
        hass: The Home Assistant test instance.
        **options: Extra config-entry options to merge in.

    Returns:
        The loaded config entry.
    """
    entry = build_entry(**options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


def message_entity_id(hass: Any, property_id: str, key: str) -> str | None:
    """Return a message sensor entity id for a property, if registered.

    Args:
        hass: The Home Assistant test instance.
        property_id: Property whose sensor is wanted.
        key: Entity key, ``last_message_at`` or ``awaiting_host_reply``.

    Returns:
        The registered entity id, or ``None`` when absent.
    """
    registry = er.async_get(hass)
    unique_id = build_unique_id(ACCOUNT, property_id, key)
    return registry.async_get_entity_id("sensor", DOMAIN, unique_id)


def thread_requests(respx_router: Any) -> list[httpx.Request]:
    """Return every recorded message-thread request.

    Args:
        respx_router: The active respx router.

    Returns:
        The captured thread requests, in order.
    """
    return [
        call.request
        for call in respx_router.calls
        if call.request.url.path.endswith("/messages")
    ]
