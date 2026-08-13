# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""A real config-entry harness for the US6 audits (T153, T153a).

One harness so the entity-surface audit and the service-response audit
drive the SAME wiring — a real ``hass``, a real ``MockConfigEntry``,
real registries, ``respx``-mocked endpoints — and therefore audit the
same integration rather than two differently-configured ones. No
request is ever made to the live host.

The harness deliberately runs with EVERY option ON when asked to, which
is the most permissive configuration the integration can be in. An
audit that ran only at defaults would be auditing the safe case.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_AWAITING_HOST_REPLY,
    CONF_GUEST_CONTACT_DETAILS,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from tests.helpers import load_fixture

ACCOUNT = "acct-example-0001"
TOKEN = "hp_test_synthetic_token_000000000000000000000000"
ZONE = timezone(timedelta(hours=-7))
PROPERTY_A = "prop-example-001"
PROPERTY_B = "prop-example-002"
RESERVATION_A = "res-guest-001"
RESERVATION_B = "res-guest-002"

# Distinctive enough that a substring search over logs, diagnostics and
# entity attributes is proof rather than noise. "Example" and "Guest"
# occur throughout unrelated text and would produce false hits.
GUEST_FIRST_NAME = "Zephyrine"
GUEST_LAST_NAME = "Quillfeather"
GUEST_LANGUAGE = "qx-ZZ"
GUEST_LOCATION = "Example City, Example Region"
GUEST_EMAIL = "guest@example.com"
GUEST_PHONE = "+15550101001"
PROFILE_PICTURE = "https://example.com/guest-avatar.png"

# Every guest VALUE the harness serves. Attribute KEY names such as
# ``guest_first_name`` are deliberately absent: a key name is not guest
# data and the entity publishes it by design.
GUEST_SECRETS = (
    GUEST_FIRST_NAME,
    GUEST_LAST_NAME,
    GUEST_LANGUAGE,
    GUEST_LOCATION,
    GUEST_EMAIL,
    GUEST_PHONE,
    PROFILE_PICTURE,
)

MESSAGE_BODY = "Quillfeather guest question about the synthetic gate code."


def _guest() -> dict[str, Any]:
    """Build the guest object the harness serves.

    Returns:
        A guest payload carrying every field the privacy controls act
        on, so an absence proves a control rather than a vacuum.
    """
    guest = dict(load_fixture("reservation_with_guest.json")["data"][0]["guest"])
    guest.update(
        {
            "first_name": GUEST_FIRST_NAME,
            "last_name": GUEST_LAST_NAME,
            "language": GUEST_LANGUAGE,
            "location": GUEST_LOCATION,
            "email": GUEST_EMAIL,
            "phone_numbers": [GUEST_PHONE],
            "profile_picture": PROFILE_PICTURE,
        }
    )
    return guest


def _stay(reservation_id: str, property_id: str, guest: Any) -> dict[str, Any]:
    """Build an accepted, mid-stay reservation for one property.

    Dates are rebased on today so "the operationally relevant stay"
    keeps meaning the same thing forever rather than only until the
    recorded dates pass.

    Args:
        reservation_id: Reservation identifier to assign.
        property_id: Property the stay belongs to.
        guest: Raw guest object, or ``None``.

    Returns:
        A reservation payload occupying the property right now.
    """
    today = datetime.now(ZONE).date()
    arrival = today - timedelta(days=1)
    departure = today + timedelta(days=2)
    payload = copy.deepcopy(load_fixture("reservation_accepted.json")["data"][0])
    payload.update(
        {
            "id": reservation_id,
            "properties": [{"id": property_id}],
            "arrival_date": f"{arrival.isoformat()}T00:00:00-07:00",
            "departure_date": f"{departure.isoformat()}T00:00:00-07:00",
            "check_in": f"{arrival.isoformat()}T16:00:00-07:00",
            "check_out": f"{departure.isoformat()}T11:00:00-07:00",
            "guest": guest,
        }
    )
    return dict(payload)


def reservations_payload() -> dict[str, Any]:
    """Build a two-property reservations envelope.

    Returns:
        One stay with a full guest and one with a null guest, so the
        null branch is exercised by every audit rather than assumed.
    """
    return {
        "data": [
            _stay(RESERVATION_A, PROPERTY_A, _guest()),
            _stay(RESERVATION_B, PROPERTY_B, None),
        ],
        "meta": {
            "current_page": 1,
            "last_page": 1,
            "path": "http://public.api.hospitable.com/v2/reservations",
            "per_page": 100,
            "total": 2,
        },
    }


def message_thread() -> dict[str, Any]:
    """Build a thread whose latest message is guest-authored.

    Returns:
        A thread envelope in the recorded shape, carrying a body
        distinctive enough for a leak search to be meaningful.
    """
    payload = copy.deepcopy(load_fixture("messages_thread.json"))
    for index, item in enumerate(payload["data"]):
        item["sender_type"] = "guest"
        item["sender_role"] = "guest"
        item["body"] = MESSAGE_BODY
        item["created_at"] = f"2026-08-12T1{index}:00:00Z"
    return dict(payload)


def _properties(request: httpx.Request) -> httpx.Response:
    """Return the paginated properties fixture for the requested page.

    Args:
        request: The captured request.

    Returns:
        The matching properties page.
    """
    page = request.url.params.get("page", "1")
    fixture = "properties_page2.json" if page == "2" else "properties_page1.json"
    return httpx.Response(200, json=load_fixture(fixture))


def _tasks(request: httpx.Request) -> httpx.Response:
    """Return a single tasks page rebased onto the requested property.

    Real tasks are served rather than an empty page. An audit that
    walked task sensors carrying no task would enumerate their
    attribute NAMES but never their VALUES, and a value-bearing leak
    would sail past it.

    Args:
        request: The captured request.

    Returns:
        A one-page tasks envelope for the requested property.
    """
    from tests.helpers.task_entry import as_single_page, tasks_page

    requested = request.url.params.get("properties[]", PROPERTY_A)
    return httpx.Response(
        200, json=as_single_page(tasks_page("tasks_page1.json", requested))
    )


def mock_endpoints(respx_router: Any) -> None:
    """Mock every endpoint the audits reach.

    The lookup routes are registered FIRST: ``respx`` matches in
    registration order, and the broader polling routes would otherwise
    win and serve the wrong body.

    Args:
        respx_router: The active respx router.
    """
    payload = reservations_payload()
    respx_router.get(
        f"{BASE_URL}/reservations/{RESERVATION_A}",
        params={"include": "guest,properties"},
    ).mock(return_value=httpx.Response(200, json={"data": payload["data"][0]}))
    respx_router.get(
        f"{BASE_URL}/reservations", params={"include": "guest,properties"}
    ).mock(return_value=httpx.Response(200, json=payload))
    for uuid in (RESERVATION_A, RESERVATION_B):
        respx_router.get(f"{BASE_URL}/reservations/{uuid}/messages").mock(
            return_value=httpx.Response(
                200,
                json=message_thread(),
                headers={"x-ratelimit-limit": "2", "x-ratelimit-remaining": "1"},
            )
        )
    respx_router.get(f"{BASE_URL}/properties").mock(side_effect=_properties)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=payload)
    )
    for property_id, fixture in (
        (PROPERTY_A, "calendar_prop1.json"),
        (PROPERTY_B, "calendar_prop2.json"),
    ):
        respx_router.get(f"{BASE_URL}/properties/{property_id}/calendar").mock(
            return_value=httpx.Response(200, json=load_fixture(fixture))
        )
    respx_router.get(f"{BASE_URL}/tasks").mock(side_effect=_tasks)


async def setup_audit_entry(
    hass: Any,
    respx_router: Any,
    *,
    guest_contact: bool,
    awaiting: bool = True,
    account: str = ACCOUNT,
) -> MockConfigEntry:
    """Set up a loaded entry against the audit routes.

    Args:
        hass: The Home Assistant test instance.
        respx_router: The active respx router.
        guest_contact: Whether the guest-contact opt-in is enabled.
        awaiting: Whether the awaiting-host-reply opt-in is enabled.
        account: Account namespace, so two entries can coexist.

    Returns:
        The loaded config entry.
    """
    mock_endpoints(respx_router)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: TOKEN,
            CONF_ACCOUNT_NAMESPACE: account,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: [PROPERTY_A, PROPERTY_B],
            CONF_GUEST_CONTACT_DETAILS: guest_contact,
            CONF_AWAITING_HOST_REPLY: awaiting,
        },
        unique_id=account,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def call_every_lookup(
    hass: Any,
    respx_router: Any,
    *,
    guest_contact: bool,
    calls: tuple[tuple[str, dict[str, Any]], ...],
) -> dict[str, Any]:
    """Call each named service once and return its response.

    Args:
        hass: The Home Assistant test instance.
        respx_router: The active respx router.
        guest_contact: Whether the guest-contact opt-in is enabled.
        calls: Service names paired with their call data.

    Returns:
        Each service's response, keyed by service name.
    """
    await setup_audit_entry(hass, respx_router, guest_contact=guest_contact)
    responses: dict[str, Any] = {}
    for service, data in calls:
        response = await hass.services.async_call(
            DOMAIN, service, data, blocking=True, return_response=True
        )
        assert response is not None, service
        assert response["found"] is True, (
            f"{service} reported not-found, so this audit would inspect an "
            "empty payload and prove nothing"
        )
        responses[service] = response
    return responses


async def call_send_message(
    hass: Any, respx_router: Any, *, guest_contact: bool
) -> Any:
    """Call ``send_message`` once against a mocked 202 and return it.

    Args:
        hass: The Home Assistant test instance.
        respx_router: The active respx router.
        guest_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        The service response.
    """
    respx_router.post(f"{BASE_URL}/reservations/{RESERVATION_A}/messages").mock(
        return_value=httpx.Response(
            202, json=load_fixture("send_message_202_full.json")
        )
    )
    await setup_audit_entry(hass, respx_router, guest_contact=guest_contact)
    response = await hass.services.async_call(
        DOMAIN,
        "send_message",
        {"reservation_uuid": RESERVATION_A, "body": "Synthetic acceptance check."},
        blocking=True,
        return_response=True,
    )
    assert response is not None
    return response
