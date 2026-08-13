# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""End-to-end throttling of the message poll (T155a, VS-9, FR-017).

**The trap this file was written around.** The poll has THREE
independent gates: the 60-second floor, an outstanding ``retry-after``,
and the shared per-token/per-reservation tracker. They are ordered, and
the FIRST of them silences the other two.

A naive end-to-end throttling test scripts a 429 and refreshes the
coordinator a few times. That test PASSES and proves nothing: the floor
suppresses every refresh after the first, the scripted 429 is never
requested at all, and the assertion that the entity kept its last good
value is satisfied by an HTTP call that never happened. Measured
directly while writing this file -- four refreshes produced two thread
requests.

So every test here does two things a naive one does not:

1. advances a frozen clock past the floor, so the request is actually
   attempted;
2. asserts the throttled route was CONSUMED, so a test that stopped
   reaching the server fails instead of passing quietly.

The gates are then exercised one at a time, because a test that cannot
say WHICH gate stopped a fetch cannot tell a working control from a
coincidence.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.hospitable import rate_limit
from custom_components.hospitable.const import CONF_AWAITING_HOST_REPLY
from custom_components.hospitable.coordinator_messages import (
    MESSAGE_FETCH_FLOOR_SECONDS,
)
from tests.actions.conftest import SYNTHETIC_TOKEN
from tests.helpers.message_entry import (
    RESERVATION_A,
    mock_base_endpoints,
    mock_threads,
    setup_message_entry,
    thread_requests,
    throttled_response,
)

PAST_THE_FLOOR = timedelta(seconds=MESSAGE_FETCH_FLOOR_SECONDS + 30)
# The poll is opt-in and OFF by default, so every test here must turn
# it on. A test that forgot would observe zero requests and could pass
# while proving nothing at all.
ENABLED = {CONF_AWAITING_HOST_REPLY: True}


def fetches(respx_router: Any, reservation: str = RESERVATION_A) -> int:
    """Count thread fetches for ONE reservation.

    Counted per reservation rather than globally because the harness
    serves two properties, each polling its own reservation, and the
    observed upstream rate-limit bucket is per reservation too. A global
    count would mix an unthrottled reservation's traffic into the
    throttled one's and make every assertion here ambiguous.

    Args:
        respx_router: The active respx router.
        reservation: The reservation UUID to count.

    Returns:
        How many thread requests were made for that reservation.
    """
    return len(
        [
            request
            for request in thread_requests(respx_router)
            if reservation in request.url.path
        ]
    )


async def _refresh(hass: Any, entry: Any) -> None:
    """Refresh the reservation coordinator, which drives the poll.

    Args:
        hass: The Home Assistant instance.
        entry: The loaded config entry.
    """
    coordinator = entry.runtime_data["coordinators"]["reservations"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_the_floor_alone_suppresses_a_second_fetch(
    hass: Any, respx_router: Any
) -> None:
    """Without advancing the clock, no second request is made at all.

    This is the control that makes every other test in this file
    meaningful. It pins the exact behaviour that would have made a
    naive 429 test vacuous, so if the floor is ever removed this test
    fails and the others stop being able to lie.
    """
    mock_base_endpoints(respx_router)
    mock_threads(respx_router)

    entry = await setup_message_entry(hass, **ENABLED)
    assert fetches(respx_router) == 1, "the first poll must reach the server"

    for _ in range(3):
        await _refresh(hass, entry)

    assert fetches(respx_router) == 1, (
        "the 60s floor must suppress every further fetch; if this ever "
        "reads more than 1, the floor is gone and the 429 tests below "
        "are no longer testing what they claim"
    )


async def test_a_throttled_poll_is_actually_attempted_and_refused(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """Past the floor the 429 is really served and really handled.

    The consumption assertion is the whole point: without it this test
    passes when the request is never made.
    """
    mock_base_endpoints(respx_router)
    routes = mock_threads(respx_router)
    entry = await setup_message_entry(hass, **ENABLED)
    assert fetches(respx_router) == 1

    routes[RESERVATION_A].mock(return_value=throttled_response())
    freezer.tick(PAST_THE_FLOOR)
    await _refresh(hass, entry)

    assert fetches(respx_router) == 2, (
        "the throttled route was never consumed, so this test proved "
        "nothing about 429 handling"
    )
    fetcher = entry.runtime_data["coordinators"]["reservations"]._message_fetcher
    assert fetcher is not None
    assert fetcher._blocked_until.get(RESERVATION_A, 0.0) > 0.0, (
        "a 429 must arm the retry-after gate; without it the poll would "
        "hammer a server that has just asked it to stop"
    )


async def test_the_poll_honours_retry_after_beyond_the_floor(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """A ``retry-after`` longer than the floor really does delay longer.

    This is the gate with no existing coverage anywhere in the suite.
    The floor is 60s and the header says 300s, so a poll that only
    honoured the floor would fetch again at 90s. Asserting at 90s and
    again at 400s separates "the floor expired" from "the server's
    instruction was obeyed", which a single-point assertion cannot.
    """
    mock_base_endpoints(respx_router)
    routes = mock_threads(respx_router)
    entry = await setup_message_entry(hass, **ENABLED)

    routes[RESERVATION_A].mock(return_value=throttled_response(retry_after=300))
    freezer.tick(PAST_THE_FLOOR)
    await _refresh(hass, entry)
    assert fetches(respx_router) == 2, "the 429 was never served"

    # Past the FLOOR but well inside the server's 300s instruction.
    freezer.tick(timedelta(seconds=90))
    await _refresh(hass, entry)
    assert fetches(respx_router) == 2, (
        "the poll fetched again 90s after a 429 that said 300s; it is "
        "honouring only its own floor and ignoring the server"
    )

    # Past the server's instruction: the poll must resume.
    freezer.tick(timedelta(seconds=260))
    await _refresh(hass, entry)
    assert fetches(respx_router) == 3, (
        "the poll never resumed after the retry-after elapsed; a "
        "throttle that never lifts is an outage, not a throttle"
    )


async def test_a_header_less_429_still_backs_off(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """A 429 with no ``retry-after`` falls back to the floor, not zero.

    The live-probed endpoint does send ``retry-after``, but a parser
    that only works when the server is well behaved is not a control.
    """
    mock_base_endpoints(respx_router)
    routes = mock_threads(respx_router)
    entry = await setup_message_entry(hass, **ENABLED)

    routes[RESERVATION_A].mock(
        return_value=httpx.Response(429, json={"status_code": 429})
    )
    freezer.tick(PAST_THE_FLOOR)
    await _refresh(hass, entry)
    assert fetches(respx_router) == 2

    fetcher = entry.runtime_data["coordinators"]["reservations"]._message_fetcher
    assert fetcher._blocked_until.get(RESERVATION_A, 0.0) > 0.0, (
        "a header-less 429 must still back off, or the poll retries "
        "immediately against a server that just refused it"
    )


async def test_the_shared_tracker_refuses_the_poll_independently(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """The tracker gate refuses a fetch even with the floor expired.

    Exercised on its own by exhausting the budget directly, so a pass
    means the TRACKER stopped the fetch rather than the floor. The poll
    and the send service consume the SAME budget, which is why this
    gate exists at all.
    """
    mock_base_endpoints(respx_router)
    mock_threads(respx_router)
    entry = await setup_message_entry(hass, **ENABLED)
    assert fetches(respx_router) == 1

    token = SYNTHETIC_TOKEN
    # One slot was consumed by the poll above; consume the other.
    rate_limit.TRACKER.record(token, RESERVATION_A)
    with pytest.raises(ServiceValidationError):
        rate_limit.TRACKER.check(token, RESERVATION_A)

    freezer.tick(PAST_THE_FLOOR)
    await _refresh(hass, entry)

    assert fetches(respx_router) == 1, (
        "the poll fetched despite an exhausted budget; the tracker gate "
        "is not being consulted"
    )


async def test_a_refused_poll_keeps_the_last_good_indicator(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """Throttling degrades to stale data, never to an error or a blank.

    Asserted on the entity's own value, and only after confirming the
    429 was really served, so this cannot pass on a poll that never
    happened.
    """
    mock_base_endpoints(respx_router)
    routes = mock_threads(respx_router)
    entry = await setup_message_entry(hass, **ENABLED)

    before = {
        state.entity_id: state.state
        for state in hass.states.async_all()
        if state.entity_id.endswith("_awaiting_host_reply")
    }
    assert before, "no awaiting-host-reply entity exists to observe"

    routes[RESERVATION_A].mock(return_value=throttled_response())
    freezer.tick(PAST_THE_FLOOR)
    await _refresh(hass, entry)
    assert fetches(respx_router) == 2, "the 429 was never served"

    after = {
        state.entity_id: state.state
        for state in hass.states.async_all()
        if state.entity_id.endswith("_awaiting_host_reply")
    }
    assert after == before, (
        f"throttling changed the indicator from {before} to {after}; a "
        "throttled read must retain the last good value (FR-019)"
    )
    coordinator = entry.runtime_data["coordinators"]["reservations"]
    assert coordinator.last_update_success, (
        "a throttled MESSAGE poll must not fail the RESERVATION refresh; "
        "the reservation data was fetched successfully"
    )
