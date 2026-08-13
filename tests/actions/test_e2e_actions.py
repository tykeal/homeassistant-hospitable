# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""End-to-end service behaviour on a real ``hass`` (T157, T158, T150a).

Everything here goes through ``hass.services.async_call`` against a
genuinely loaded config entry and ``respx``-mocked HTTP. No handler is
called directly and no client is stubbed, because the defects this
project keeps finding live in the wiring BETWEEN correct pieces rather
than in the pieces.

Three things are covered that unit tests structurally cannot:

* **T150a, the other half of SC-007.** SC-007 pairs a latency budget
  with "no side effects", and the latency half absorbed all the
  attention. A read-only service must leave the state machine and the
  event bus untouched, which is only observable with a real bus.
* **T158, multi-entry budget sharing.** Two config entries on the SAME
  token must share one per-reservation budget. The existing coverage
  pokes the tracker directly, which cannot see whether the SERVICE path
  reaches the shared singleton or quietly builds its own.
* **T157, the send path end to end**, including that a 202 is reported
  as ACCEPTED and never as delivered.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from homeassistant.const import MATCH_ALL
from homeassistant.core import Event
from homeassistant.exceptions import ServiceValidationError

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import DOMAIN
from tests.actions.conftest import (
    ACCOUNT_NAMESPACE,
    RESERVATION_A,
    SYNTHETIC_TOKEN,
)
from tests.helpers import load_fixture

READ_ONLY_SERVICES = ("find_reservation", "get_reservations", "get_property_info")


async def _call(hass: Any, service: str, data: dict[str, Any]) -> Any:
    """Call one Hospitable service and return its response.

    Args:
        hass: The Home Assistant instance.
        service: Service name within the integration domain.
        data: Service call data.

    Returns:
        The service response payload.
    """
    return await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=True
    )


# --- T150a: SC-007's untested half -------------------------------------


async def test_a_read_only_service_produces_no_side_effect(
    hass: Any,
    respx_router: Any,
    lookup_routes: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """A lookup changes no state and fires no integration event (SC-007).

    SC-007 has two halves and only the latency one was ever measured.
    "No side effects" is asserted here against a real event bus and a
    real state machine, because neither is observable when a handler is
    called directly.

    The bus listener deliberately ignores ``call_service`` and
    ``service_registered``: Home Assistant fires those itself for ANY
    service call, so counting them would make the assertion impossible
    to satisfy and tell us nothing about this integration.
    """
    payload = load_fixture("reservation_with_guest.json")
    lookup_routes.reservations(json_body=payload)
    lookup_routes.reservation(RESERVATION_A, json_body={"data": payload["data"][0]})
    await loaded_config_entry_factory(hass)

    platform_events = {"call_service", "service_registered", "service_removed"}
    observed: list[Event] = []

    def _capture(event: Event) -> None:
        """Record any non-platform event.

        Args:
            event: The fired event.
        """
        if event.event_type not in platform_events:
            observed.append(event)

    unsub = hass.bus.async_listen(MATCH_ALL, _capture)
    before = {state.entity_id: state.as_dict() for state in hass.states.async_all()}
    assert before, "no entities exist, so the state assertion would be vacuous"

    for service in READ_ONLY_SERVICES:
        data = (
            {"reservation_uuid": RESERVATION_A}
            if service == "find_reservation"
            else {"property_id": "prop-example-001"}
        )
        await _call(hass, service, data)
    await hass.async_block_till_done()
    unsub()

    after = {state.entity_id: state.as_dict() for state in hass.states.async_all()}
    assert set(after) == set(before), "a read-only service added or removed an entity"
    for entity_id, snapshot in before.items():
        assert after[entity_id]["state"] == snapshot["state"], (
            f"{entity_id} changed state during a read-only service call"
        )
        assert after[entity_id]["last_changed"] == snapshot["last_changed"], (
            f"{entity_id} was re-written during a read-only service call; "
            "even a same-value write is a side effect"
        )
    assert not observed, (
        f"read-only services fired {[event.event_type for event in observed]}"
    )


async def test_a_read_only_service_does_not_refresh_a_coordinator(
    hass: Any,
    respx_router: Any,
    lookup_routes: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """A lookup triggers no coordinator refresh (SC-007).

    A refresh would be a side effect the state comparison above could
    miss entirely, since a refresh returning identical data leaves every
    state untouched. Counted through a coordinator listener instead.
    """
    lookup_routes.reservations(json_body=load_fixture("reservation_with_guest.json"))
    entry = await loaded_config_entry_factory(hass)

    refreshes = {name: 0 for name in entry.runtime_data["coordinators"]}
    unsubs = []
    for name, coordinator in entry.runtime_data["coordinators"].items():

        def _bump(_name: str = name) -> None:
            """Count one refresh of this coordinator."""
            refreshes[_name] += 1

        unsubs.append(coordinator.async_add_listener(_bump))

    await _call(hass, "get_reservations", {"property_id": "prop-example-001"})
    await hass.async_block_till_done()
    for unsub in unsubs:
        unsub()

    assert refreshes == dict.fromkeys(refreshes, 0), (
        f"a read-only service refreshed coordinators: {refreshes}"
    )


# --- T158: two entries, one token, one budget --------------------------


async def test_two_entries_on_one_token_share_the_budget(
    hass: Any,
    respx_router: Any,
    messages_routes: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """The per-reservation budget is shared across config entries.

    The budget belongs to the TOKEN upstream, not to a config entry, so
    two entries authenticating with the same PAT get two requests
    between them and not two each.

    Driven through ``hass.services.async_call`` rather than through the
    tracker, which is the whole point: existing coverage pokes the
    tracker directly and so cannot see whether the SERVICE path reaches
    the shared singleton or quietly constructs its own counter. A
    per-entry counter would pass every existing rate-limit test.
    """
    # No rate-limit headers on purpose. A server hint is AUTHORITATIVE
    # in both directions, so a response repeatedly claiming
    # `remaining: 1` would top the budget up forever and this test would
    # be asserting the mock rather than the tracker.
    messages_routes.get(RESERVATION_A, json_body={"data": []}, headers={})
    first = await loaded_config_entry_factory(hass)
    second = await loaded_config_entry_factory(
        hass, account=f"{ACCOUNT_NAMESPACE}-second", token=SYNTHETIC_TOKEN
    )
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2
    assert first.data["token"] == second.data["token"], (
        "the two entries must share a token, or this test proves nothing"
    )

    # One call through EACH entry. If the budget were kept per entry,
    # both would succeed and a third would too.
    for entry in (first, second):
        await _call(
            hass,
            "get_messages",
            {"reservation_uuid": RESERVATION_A, "config_entry_id": entry.entry_id},
        )

    with pytest.raises(ServiceValidationError) as excinfo:
        await _call(
            hass,
            "get_messages",
            {"reservation_uuid": RESERVATION_A, "config_entry_id": first.entry_id},
        )
    assert "rate" in str(excinfo.value).lower() or "limit" in str(excinfo.value).lower()


async def test_the_budget_is_per_reservation_not_global(
    hass: Any,
    respx_router: Any,
    messages_routes: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """Exhausting one reservation leaves another usable (FR-017).

    Live-probed upstream: reservation A was driven into a 429 and
    reservation B immediately returned 200 with a fresh
    ``remaining: 1``. A global counter would satisfy every "we stop at
    two" test while being wrong about the thing that matters -- it
    would lock a host out of a reservation they had never touched.
    """
    from tests.actions.conftest import RESERVATION_B

    for reservation in (RESERVATION_A, RESERVATION_B):
        messages_routes.get(reservation, json_body={"data": []}, headers={})
    await loaded_config_entry_factory(hass)

    for _ in range(2):
        await _call(hass, "get_messages", {"reservation_uuid": RESERVATION_A})
    with pytest.raises(ServiceValidationError):
        await _call(hass, "get_messages", {"reservation_uuid": RESERVATION_A})

    response = await _call(hass, "get_messages", {"reservation_uuid": RESERVATION_B})
    assert response is not None, (
        "reservation B was refused while only reservation A was exhausted; "
        "the budget is being kept globally rather than per reservation"
    )


# --- T157: the send path, end to end -----------------------------------


async def test_a_202_is_reported_as_accepted_and_never_as_sent(
    hass: Any,
    respx_router: Any,
    messages_routes: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """A 202 means ACCEPTED FOR DELIVERY, and the response says so.

    Delivery is asynchronous and this integration never observes it, so
    a response claiming the message was sent or delivered would be an
    assertion about something nobody checked.
    """
    messages_routes.post(
        RESERVATION_A,
        status=202,
        json_body={"sent_reference_id": "ref-example-0001"},
        headers=messages_routes.headers(limit=2, remaining=1),
    )
    await loaded_config_entry_factory(hass)

    response = await _call(
        hass,
        "send_message",
        {"reservation_uuid": RESERVATION_A, "body": "Synthetic gate code."},
    )

    assert response["accepted"] is True
    assert response["reservation_uuid"] == RESERVATION_A
    assert set(response) == {"accepted", "reservation_uuid", "sent_reference_id"}, (
        f"the send response grew keys: {sorted(response)}"
    )
    rendered = repr(response).lower()
    for claim in ('sent"', "'sent'", "delivered", "success"):
        assert claim not in rendered, (
            f"the send response claims {claim!r}; a 202 is acceptance, not delivery"
        )


async def test_a_send_failure_surfaces_as_a_validation_error(
    hass: Any,
    respx_router: Any,
    messages_routes: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """A 422 becomes ``ServiceValidationError``, not a generic error.

    The distinction is user-facing: a validation error tells the caller
    their input was wrong, while ``HomeAssistantError`` says the
    integration broke. The Laravel envelope is shared by the 400, the
    422 and the 429, so one parser serves all three.
    """
    from homeassistant.exceptions import ServiceValidationError

    messages_routes.post(
        RESERVATION_A,
        status=422,
        json_body={
            "status_code": 422,
            "reason_phrase": "Unprocessable Entity",
            "errors": {"body": ["The body field is required."]},
        },
    )
    await loaded_config_entry_factory(hass)

    with pytest.raises(ServiceValidationError):
        await _call(
            hass,
            "send_message",
            {"reservation_uuid": RESERVATION_A, "body": "Synthetic."},
        )


async def test_a_transport_failure_surfaces_as_a_home_assistant_error(
    hass: Any,
    respx_router: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """A transport failure is ``HomeAssistantError``, not a validation error.

    The counterpart to the test above. Misclassifying a network outage
    as a validation error would tell the user to fix input that was
    never wrong.
    """
    from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

    respx_router.post(f"{BASE_URL}/reservations/{RESERVATION_A}/messages").mock(
        side_effect=httpx.ConnectError("synthetic transport failure")
    )
    await loaded_config_entry_factory(hass)

    with pytest.raises(HomeAssistantError) as excinfo:
        await _call(
            hass,
            "send_message",
            {"reservation_uuid": RESERVATION_A, "body": "Synthetic."},
        )
    assert not isinstance(excinfo.value, ServiceValidationError), (
        "a transport failure was reported as a validation error, which "
        "tells the user to fix input that was never wrong"
    )
