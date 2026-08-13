# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase whole-lifecycle read-only tests (T140, FR-059).

FR-059 forbids any calendar modification request absolutely. This is
proved structurally, over the full entry lifecycle: setup, a refresh of
every coordinator, an options change (which triggers the reload
listener), a reload, and an unload. After all of that the ``respx``
router must have recorded zero requests whose method is anything other
than ``GET`` — covering ``POST``/``PUT``/``PATCH``/``DELETE`` alike, not
merely the absence of a ``POST``.
"""

from __future__ import annotations

from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_LOOKAHEAD_DAYS,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from tests.helpers import load_fixture

_ACCOUNT = "acct-example-0001"


def _properties_side_effect(request: httpx.Request) -> httpx.Response:
    """Return the paginated properties fixture for the requested page."""
    page = request.url.params.get("page", "1")
    fixture = "properties_page2.json" if page == "2" else "properties_page1.json"
    return httpx.Response(200, json=load_fixture(fixture))


def _mock_all_endpoints(respx_router: Any) -> None:
    """Mock every GET endpoint reused across setup and reload."""
    respx_router.get(f"{BASE_URL}/properties").mock(side_effect=_properties_side_effect)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-001/calendar").mock(
        return_value=httpx.Response(200, json=load_fixture("calendar_prop1.json"))
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-002/calendar").mock(
        return_value=httpx.Response(200, json=load_fixture("calendar_prop2.json"))
    )
    # US4 adds a tasks coordinator to the lifecycle, so the shared route
    # set has to cover /tasks or an unmocked call would abort setup.
    respx_router.get(f"{BASE_URL}/tasks").mock(
        return_value=httpx.Response(200, json=load_fixture("tasks_empty.json"))
    )


async def test_full_lifecycle_issues_only_get_requests(
    hass: Any, respx_router: Any
) -> None:
    """A full entry lifecycle records exclusively ``GET`` requests."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: _ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
            CONF_LOOKAHEAD_DAYS: 30,
        },
        unique_id=_ACCOUNT,
    )
    entry.add_to_hass(hass)
    _mock_all_endpoints(respx_router)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    # Every coordinator, calendar and tasks included, participates in
    # the lifecycle. The set is exact rather than a subset so a NEW
    # coordinator cannot join the lifecycle without being added here and
    # therefore proved GET-only by the assertion below.
    coordinators = entry.runtime_data["coordinators"]
    assert set(coordinators) == {"properties", "reservations", "calendar", "tasks"}
    for coordinator in coordinators.values():
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    # An options change fires the reload listener added in US4.
    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
            CONF_LOOKAHEAD_DAYS: 45,
        },
    )
    await hass.async_block_till_done()

    # An explicit reload and unload complete the lifecycle.
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert len(respx_router.calls) > 0
    for call in respx_router.calls:
        assert call.request.method == "GET", (
            f"Non-GET request recorded: {call.request.method} {call.request.url}"
        )


async def test_service_call_may_post_while_lifecycle_stays_read_only(
    hass: Any, respx_router: Any
) -> None:
    """A service call may POST; the polling lifecycle still may not.

    This is write-isolation gate 4 in its narrowed form. It proves the
    two halves of FR-001 at once: every request the lifecycle issues is
    a GET, and the POST that does appear is attributable to an explicit
    user-invoked service call rather than to any polling path.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: _ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
            CONF_LOOKAHEAD_DAYS: 30,
        },
        unique_id=_ACCOUNT,
    )
    entry.add_to_hass(hass)
    _mock_all_endpoints(respx_router)
    send_route = respx_router.post(
        f"{BASE_URL}/reservations/res-example-accepted/messages"
    ).mock(
        return_value=httpx.Response(
            202, json=load_fixture("send_message_202_full.json")
        )
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    for coordinator in entry.runtime_data["coordinators"].values():
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    lifecycle_calls = list(respx_router.calls)
    assert lifecycle_calls, "the polling lifecycle issued no requests"
    for call in lifecycle_calls:
        assert call.request.method == "GET", (
            f"Non-GET request from the polling lifecycle: "
            f"{call.request.method} {call.request.url}"
        )

    assert hass.services.has_service(DOMAIN, "send_message")
    response = await hass.services.async_call(
        DOMAIN,
        "send_message",
        {
            "reservation_uuid": "res-example-accepted",
            "body": "Synthetic acceptance check.",
        },
        blocking=True,
        return_response=True,
    )

    assert response is not None
    assert send_route.called
    posts = [call for call in respx_router.calls if call.request.method == "POST"]
    assert len(posts) == 1
    assert posts[0].request.url.path.endswith(
        "/reservations/res-example-accepted/messages"
    )

    # Unloading is still write-free once the service call is excluded.
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    after_unload = [
        call
        for call in respx_router.calls[len(lifecycle_calls) + 1 :]
        if call.request.method != "GET"
    ]
    assert not after_unload


async def test_the_read_services_issue_only_get_requests(
    hass: Any, respx_router: Any
) -> None:
    """Every US2 lookup service is GET-only, end to end.

    Write-isolation gate 4, widened rather than weakened: the four
    services added in US2 are READ services by contract, so exercising
    all of them on a real config entry must leave the recorded traffic
    entirely ``GET``. ``send_message`` is deliberately NOT called here —
    its POST is proved legitimate by the test above, and mixing the two
    would blunt this assertion.
    """
    from tests.actions.conftest import LookupRouteBuilder, MessagesRouteBuilder

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: _ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
            CONF_LOOKAHEAD_DAYS: 30,
        },
        unique_id=_ACCOUNT,
    )
    entry.add_to_hass(hass)
    messages = MessagesRouteBuilder(respx_router, BASE_URL)
    lookups = LookupRouteBuilder(respx_router, BASE_URL)
    messages.get("res-example-accepted", json_body=load_fixture("messages_thread.json"))
    lookups.reservation(
        "res-example-guest-full",
        json_body={"data": load_fixture("reservation_with_guest.json")["data"][0]},
    )
    lookups.reservations(json_body=load_fixture("reservation_with_guest.json"))
    _mock_all_endpoints(respx_router)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    calls: list[tuple[str, dict[str, Any]]] = [
        ("get_messages", {"reservation_uuid": "res-example-accepted"}),
        ("find_reservation", {"reservation_uuid": "res-example-guest-full"}),
        ("get_reservations", {"property_id": "prop-example-001"}),
        ("get_property_info", {"property_id": "prop-example-001"}),
    ]
    for service, data in calls:
        assert hass.services.has_service(DOMAIN, service), service
        response = await hass.services.async_call(
            DOMAIN, service, data, blocking=True, return_response=True
        )
        assert response is not None, service
        assert response["found"] is True, service

    assert respx_router.calls, "no requests were recorded"
    for call in respx_router.calls:
        assert call.request.method == "GET", (
            f"Non-GET request from a read service: "
            f"{call.request.method} {call.request.url}"
        )


# --- US5 extension of gate 4 (T146, FR-001, FR-059) ---------------------
#
# ADDS to the lifecycle gate above; nothing there is relaxed. That test
# runs with the awaiting-host-reply option OFF, which is the default, so
# it never reaches the message poll at all. Leaving it at that would
# make the gate silently vacuous for the one US5 code path that issues
# new traffic — the gate would keep reporting green over a request path
# it never executed.


async def test_the_opt_in_message_poll_stays_read_only(
    hass: Any, respx_router: Any
) -> None:
    """The message poll issues GETs and nothing else (T146, FR-059).

    The poll really is exercised rather than merely permitted: the
    message route's own call count is asserted non-zero first, so the
    GET-only assertion below is made about traffic that actually
    happened.
    """
    from custom_components.hospitable.const import CONF_AWAITING_HOST_REPLY
    from tests.helpers.message_entry import (
        RESERVATION_A,
        RESERVATION_B,
        messages_url,
        reservations_payload,
        thread,
    )

    options = {
        CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
        CONF_LOOKAHEAD_DAYS: 30,
        CONF_AWAITING_HOST_REPLY: True,
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: _ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options=options,
        unique_id=_ACCOUNT,
    )
    entry.add_to_hass(hass)
    _mock_all_endpoints(respx_router)
    # The reservations route is re-registered with the US5 harness
    # payload, whose stays are anchored to today. The recorded page
    # cannot be used here: the client filters reservations to the
    # requested window and the recorded arrivals are in 2025, so the
    # poll would see zero reservations, fetch nothing, and this gate
    # would pass while proving nothing.
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=reservations_payload())
    )
    thread_routes = [
        respx_router.get(messages_url(uuid)).mock(
            return_value=httpx.Response(
                200,
                json=thread("guest", "host"),
                headers={"x-ratelimit-limit": "2", "x-ratelimit-remaining": "1"},
            )
        )
        for uuid in (RESERVATION_A, RESERVATION_B)
    ]

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    # The coordinator set is STILL exactly these four: message presence
    # rides on the reservation coordinator rather than adding one, so no
    # new coordinator joined the lifecycle unproved.
    coordinators = entry.runtime_data["coordinators"]
    assert set(coordinators) == {"properties", "reservations", "calendar", "tasks"}
    for coordinator in coordinators.values():
        await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert all(route.call_count > 0 for route in thread_routes), (
        "the message poll never ran, so this proves nothing about its method"
    )
    for call in respx_router.calls:
        assert call.request.method == "GET", (
            f"Non-GET request recorded: {call.request.method} {call.request.url}"
        )
