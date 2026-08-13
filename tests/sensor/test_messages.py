# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for the message presence sensors (US5, T132 to T139).

Almost nothing here is a unit test on a parser. A real ``hass``, a real
``MockConfigEntry``, the real entity registry, and ``respx``-mocked
endpoints drive the whole platform, so the red-phase failure is an
``AssertionError`` about behaviour the integration does not yet have
rather than a ``ModuleNotFoundError`` about a file that does not yet
exist. A ``ModuleNotFoundError`` red phase proves only that somebody
has not created a file; it does not describe the requirement.

Two tests deliberately keep ``ModuleNotFoundError``: the two that
assert on a NEW module's own constants, where the absence of the module
genuinely IS the failure being described.

No request is ever made to the live host: every route is mocked. No
POST is issued anywhere in this file.
"""

from __future__ import annotations

import importlib
import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.helpers.message_entry import (
    LAST_MESSAGE_AT_A,
    LAST_MESSAGE_AT_B,
    PRIVATE_BODIES,
    PROPERTY_A,
    PROPERTY_B,
    RESERVATION_A,
    RESERVATION_B,
    THREAD_HEADERS,
    empty_thread,
    message_entity_id,
    mock_base_endpoints,
    mock_threads,
    reservations_payload,
    setup_message_entry,
    thread,
    thread_requests,
    throttled_response,
)

LAST_MESSAGE_KEY = "last_message_at"
AWAITING_KEY = "awaiting_host_reply"


def _state(hass: Any, property_id: str, key: str) -> Any:
    """Return a message sensor's state object, asserting it is present.

    Args:
        hass: The Home Assistant test instance.
        property_id: Property whose sensor is wanted.
        key: Entity key to look up.

    Returns:
        The entity state.
    """
    entity_id = message_entity_id(hass, property_id, key)
    assert entity_id is not None, f"no {key} sensor registered for {property_id}"
    state = hass.states.get(entity_id)
    assert state is not None, f"{key} sensor for {property_id} has no state"
    return state


def _enabled(**extra: Any) -> dict[str, Any]:
    """Return config-entry options with the awaiting-reply opt-in ON.

    Args:
        **extra: Further options to merge in.

    Returns:
        The options mapping.

    Raises:
        ImportError: The option constant does not exist yet.
    """
    from custom_components.hospitable.const import CONF_AWAITING_HOST_REPLY

    return {CONF_AWAITING_HOST_REPLY: True, **extra}


# --- T132: the last-message timestamp sensor ---------------------------


async def test_a_last_message_sensor_exists_for_every_property(
    hass: Any, respx_router: Any
) -> None:
    """Every property gets a last-message timestamp sensor (T132, FR-036).

    The sensor is NOT gated behind any option: it costs nothing, so it
    is always present. Both properties are asserted rather than one, so
    a sensor built for only the first property in the fan-out fails.
    """
    mock_base_endpoints(respx_router)
    await setup_message_entry(hass)

    for property_id, expected in (
        (PROPERTY_A, LAST_MESSAGE_AT_A),
        (PROPERTY_B, LAST_MESSAGE_AT_B),
    ):
        state = _state(hass, property_id, LAST_MESSAGE_KEY)
        assert state.state == expected, (
            f"{property_id} last_message_at reported {state.state!r}, "
            f"expected the reservation's own {expected!r}"
        )
        assert state.attributes.get("device_class") == "timestamp", (
            f"{property_id} last_message_at must be a timestamp sensor"
        )


# --- T133: zero additional HTTP requests -------------------------------


async def test_the_last_message_sensor_issues_no_extra_requests(
    hass: Any, respx_router: Any
) -> None:
    """The timestamp costs ZERO extra requests (T133, FR-036, FR-038).

    The thread endpoint is deliberately NOT mocked, so a fetch would
    raise rather than quietly succeed. That is the assertion that
    matters: the value has to come from data the reservation
    coordinator already holds.

    The state assertion is what stops this being a tautology. A sensor
    that reported nothing would also issue no requests, and would also
    pass a request-count check alone.
    """
    mock_base_endpoints(respx_router)
    entry = await setup_message_entry(hass)

    assert not thread_requests(respx_router), (
        "the last-message sensor issued a message request; it must derive "
        "from data the reservation coordinator already holds"
    )
    state = _state(hass, PROPERTY_A, LAST_MESSAGE_KEY)
    assert state.state == LAST_MESSAGE_AT_A

    # A refresh must not start costing requests either.
    await entry.runtime_data["coordinators"]["reservations"].async_refresh()
    await hass.async_block_till_done()
    assert not thread_requests(respx_router), (
        "a reservation refresh issued a message request with the "
        "awaiting-host-reply option OFF"
    )


# --- T134: degrade to unknown, not error -------------------------------


async def test_the_last_message_sensor_is_unknown_when_absent(
    hass: Any, respx_router: Any
) -> None:
    """A missing timestamp is unknown, not an error (T134, FR-036).

    Both the null-valued and the no-reservation cases are covered,
    because they reach the sensor by different routes and only one of
    them would be caught by a null check on the reservation payload.
    """
    payload = reservations_payload(last_message_at_a=None)
    payload["data"] = [payload["data"][0]]
    mock_base_endpoints(respx_router, reservations=payload)
    await setup_message_entry(hass)

    # Property A has a reservation whose last_message_at is null.
    null_state = _state(hass, PROPERTY_A, LAST_MESSAGE_KEY)
    assert null_state.state == "unknown", (
        f"a null last_message_at reported {null_state.state!r}, expected unknown"
    )

    # Property B has no reservation at all in this payload.
    missing_state = _state(hass, PROPERTY_B, LAST_MESSAGE_KEY)
    assert missing_state.state == "unknown", (
        f"a property with no reservation reported {missing_state.state!r}, "
        "expected unknown"
    )
    assert missing_state.state != "unavailable", (
        "a property with no messages must degrade to unknown, not unavailable"
    )


# --- T135: the opt-in gate ---------------------------------------------


async def test_the_awaiting_sensor_appears_only_when_opted_in(
    hass: Any, respx_router: Any
) -> None:
    """The indicator is absent when off and present when on (T135, FR-037).

    Both halves live in ONE test on purpose. "Absent when off" passes
    trivially before the feature exists, so on its own it would be a
    false green; pairing it with "present when on" makes the pair fail
    in the red phase for the right reason.
    """
    mock_base_endpoints(respx_router)
    mock_threads(respx_router)
    await setup_message_entry(hass)
    assert message_entity_id(hass, PROPERTY_A, AWAITING_KEY) is None, (
        "the awaiting-host-reply sensor exists with the option OFF"
    )
    assert message_entity_id(hass, PROPERTY_A, LAST_MESSAGE_KEY) is not None, (
        "the always-on last_message_at sensor is missing, so the check "
        "above proves nothing about gating"
    )


async def test_the_awaiting_sensor_is_created_when_opted_in(
    hass: Any, respx_router: Any
) -> None:
    """Enabling the option creates the indicator (T135, FR-037, FR-038a)."""
    mock_base_endpoints(respx_router)
    mock_threads(respx_router)
    await setup_message_entry(hass, **_enabled())

    for property_id in (PROPERTY_A, PROPERTY_B):
        assert message_entity_id(hass, property_id, AWAITING_KEY) is not None, (
            f"no awaiting-host-reply sensor for {property_id} with the option ON"
        )


async def test_the_awaiting_option_defaults_off(hass: Any, respx_router: Any) -> None:
    """The opt-in defaults OFF everywhere it is expressed (T135, FR-038a).

    Three surfaces have to agree: the constant, the options-flow default
    map, and the behaviour of an entry that never set the option. A
    constant assertion alone would pass today, so the entry behaviour is
    asserted with it.
    """
    from custom_components.hospitable.const import (
        CONF_AWAITING_HOST_REPLY,
        DEFAULT_AWAITING_HOST_REPLY,
    )
    from custom_components.hospitable.options_flow import DEFAULT_OPTIONS

    assert DEFAULT_AWAITING_HOST_REPLY is False
    # ``.get`` with a sentinel, NOT a subscript: a subscript would raise
    # KeyError in the red phase, which the marker does not name, so the
    # test would fail for a reason it never described.
    assert DEFAULT_OPTIONS.get(CONF_AWAITING_HOST_REPLY, "missing") is False, (
        "the options flow default map does not carry the opt-in as OFF"
    )

    mock_base_endpoints(respx_router)
    await setup_message_entry(hass)
    assert not thread_requests(respx_router), (
        "an entry that never set the option still fetched message threads"
    )


# --- T136: at most one fetch per property per cycle --------------------


async def test_one_message_fetch_per_property_per_cycle(
    hass: Any, respx_router: Any
) -> None:
    """Each cycle costs exactly one fetch per property (T136, FR-037).

    "At most one" is asserted as EXACTLY one. An upper bound alone is
    satisfied by zero, which is the state the red phase is already in,
    so the bound would never bite.
    """
    mock_base_endpoints(respx_router)
    mock_threads(respx_router)
    await setup_message_entry(hass, **_enabled())

    requests = thread_requests(respx_router)
    per_reservation: dict[str, int] = {}
    for request in requests:
        uuid = request.url.path.rsplit("/", 2)[-2]
        per_reservation[uuid] = per_reservation.get(uuid, 0) + 1

    assert per_reservation == {RESERVATION_A: 1, RESERVATION_B: 1}, (
        f"expected exactly one fetch for each property's operationally "
        f"relevant reservation, got {per_reservation}"
    )


# --- T136a: the deliberately conservative 60-second floor --------------


def test_the_message_fetch_floor_is_sixty_seconds() -> None:
    """The per-reservation fetch floor is 60 seconds (T136a, FR-038a).

    This is the one assertion in the file whose subject is a constant
    rather than behaviour, so its red-phase failure is the absence of
    the module that must define it.

    60 seconds is a DELIBERATELY CONSERVATIVE CHOICE, not a derivation.
    The CONFIRMED upstream limit of 2 requests per 60 seconds per
    reservation would mathematically permit 30 seconds. The second slot
    is left unused so a user-initiated send is not starved if reads and
    writes share one bucket. OQ-007 is OPEN: this test asserts the
    floor, and deliberately asserts NOTHING about whether the buckets
    are shared, because nobody knows.
    """
    # Imported dynamically, not statically. A static import of a
    # not-yet-existing module needs a ``type: ignore`` whose error code
    # differs between the local mypy run (where the package resolves)
    # and the pre-commit one (where it does not), so neither spelling
    # can satisfy both. ``import_module`` raises the same
    # ``ModuleNotFoundError`` the marker names and needs no suppression
    # to remove in the green phase.
    messages_coordinator = importlib.import_module(
        "custom_components.hospitable.coordinator_messages"
    )
    tracker = importlib.import_module("custom_components.hospitable.rate_limit")
    MESSAGE_FETCH_FLOOR_SECONDS = messages_coordinator.MESSAGE_FETCH_FLOOR_SECONDS
    RESERVATION_LIMIT = tracker.RESERVATION_LIMIT
    RESERVATION_WINDOW_SECONDS = tracker.RESERVATION_WINDOW_SECONDS

    assert MESSAGE_FETCH_FLOOR_SECONDS >= 60.0

    # The floor must leave at least one of the confirmed slots unused.
    permitted_by_limit = RESERVATION_WINDOW_SECONDS / RESERVATION_LIMIT
    assert permitted_by_limit < MESSAGE_FETCH_FLOOR_SECONDS, (
        "the floor equals the rate limit's mathematical maximum, which "
        "would leave no slot free for a user-initiated send"
    )
    slots_consumed = RESERVATION_WINDOW_SECONDS / MESSAGE_FETCH_FLOOR_SECONDS
    assert slots_consumed <= RESERVATION_LIMIT - 1, (
        f"the poll would consume {slots_consumed} of {RESERVATION_LIMIT} slots"
    )


async def test_the_floor_holds_below_the_reservation_interval(
    hass: Any, respx_router: Any
) -> None:
    """The floor is independent of the poll interval (T136a, T142a).

    The reservation poll interval floor is ONE minute, so an entry
    configured at that cadence would otherwise drive one message fetch
    per reservation per minute. Refreshing repeatedly at a cadence the
    reservation coordinator itself permits must not multiply the
    message traffic.
    """
    from custom_components.hospitable.const import CONF_RESERVATION_INTERVAL

    mock_base_endpoints(respx_router)
    mock_threads(respx_router)
    entry = await setup_message_entry(
        hass, **_enabled(**{CONF_RESERVATION_INTERVAL: 1})
    )
    first = len(thread_requests(respx_router))
    assert first == 2, f"setup should fetch once per property, got {first}"

    coordinator = entry.runtime_data["coordinators"]["reservations"]
    for _ in range(4):
        await coordinator.async_refresh()
        await hass.async_block_till_done()

    assert len(thread_requests(respx_router)) == first, (
        "four further refreshes inside the 60-second floor issued more "
        "message fetches; the floor must not follow the reservation "
        "poll interval"
    )


# --- T136b: a rapid double refresh -------------------------------------


async def test_a_rapid_double_refresh_stays_inside_the_budget(
    hass: Any, respx_router: Any
) -> None:
    """Back-to-back refreshes do not double the fetch (T136b, FR-019).

    The reservation data itself must still refresh; only the message
    fetch is skipped. Asserting both is what distinguishes "the message
    fetch was deferred" from "the whole refresh was skipped".
    """
    mock_base_endpoints(respx_router)
    mock_threads(respx_router)
    entry = await setup_message_entry(hass, **_enabled())

    baseline = len(thread_requests(respx_router))
    # An upper bound alone is satisfied by zero fetches, which is
    # exactly the red-phase state, so the bound would never bite. The
    # budget can only be proved unexceeded once it is proved USED.
    assert baseline == 2, (
        f"setup must fetch once per property before a budget assertion "
        f"means anything, got {baseline}"
    )
    reservation_calls_before = len(
        [c for c in respx_router.calls if c.request.url.path.endswith("/reservations")]
    )

    coordinator = entry.runtime_data["coordinators"]["reservations"]
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(thread_requests(respx_router)) == baseline, (
        "a rapid double refresh exceeded the per-reservation message budget"
    )
    reservation_calls_after = len(
        [c for c in respx_router.calls if c.request.url.path.endswith("/reservations")]
    )
    assert reservation_calls_after >= reservation_calls_before + 2, (
        "the reservation poll itself was skipped; only the message fetch "
        "may be deferred"
    )


# --- T136c: fanning out across different reservations is allowed -------


async def test_many_reservations_may_be_fetched_in_one_cycle(
    hass: Any, respx_router: Any
) -> None:
    """Buckets are per reservation, so a fan-out is legal (T136c, FR-017).

    Established by live probe: a reservation burned to a 429 returned
    HTTP 200 with a fresh allowance on a DIFFERENT reservation
    immediately afterwards. The constraint is per reservation, not
    global, so an implementation that serialised the fan-out behind one
    global budget would be needlessly wrong.
    """
    mock_base_endpoints(respx_router)
    mock_threads(respx_router)
    await setup_message_entry(hass, **_enabled())

    fetched = {
        request.url.path.rsplit("/", 2)[-2] for request in thread_requests(respx_router)
    }
    assert fetched == {RESERVATION_A, RESERVATION_B}, (
        f"a one-cycle fan-out across independent reservations must reach "
        f"both, reached {sorted(fetched)}"
    )


# --- T136d: a 429 is a throttle, not an outage -------------------------


async def test_a_throttled_fetch_retains_the_last_good_value(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """A 429 retains the value and stays available (T136d, FR-019).

    A throttle is not an outage. Three things must hold at once: the
    indicator keeps its last good reading, the entity is NOT marked
    unavailable, and the reservation data that WAS fetched successfully
    still updates.

    The clock is advanced past the 60-second floor so the SECOND fetch
    is genuinely attempted and genuinely throttled. Without that the
    floor would skip it and this would prove nothing about a 429.
    """
    mock_base_endpoints(respx_router)
    mock_threads(
        respx_router,
        responses={
            RESERVATION_A: [
                httpx.Response(
                    200, json=thread("host", "guest"), headers=THREAD_HEADERS
                ),
                throttled_response(retry_after=60),
            ],
            RESERVATION_B: [
                httpx.Response(
                    200, json=thread("guest", "host"), headers=THREAD_HEADERS
                )
            ],
        },
    )
    entry = await setup_message_entry(hass, **_enabled())

    before = _state(hass, PROPERTY_A, AWAITING_KEY)
    assert before.state == "on", (
        f"a guest-authored latest message must read on, got {before.state!r}"
    )

    coordinator = entry.runtime_data["coordinators"]["reservations"]
    freezer.tick(timedelta(seconds=90))
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    throttled = [
        request
        for request in thread_requests(respx_router)
        if request.url.path.rsplit("/", 2)[-2] == RESERVATION_A
    ]
    assert len(throttled) == 2, (
        f"the throttled fetch was never attempted ({len(throttled)} fetches), "
        "so no 429 was ever handled"
    )

    after = _state(hass, PROPERTY_A, AWAITING_KEY)
    assert after.state == "on", (
        f"a 429 lost the last-good indicator value, now {after.state!r}"
    )
    assert after.state != "unavailable", "a 429 marked the entity unavailable"
    assert coordinator.last_update_success, (
        "a message 429 failed the whole reservation update; the "
        "reservation data was fetched successfully and must not fail"
    )


# --- T137: derivation from the sender role, and never "unread" ---------


async def test_the_indicator_follows_the_latest_sender_role(
    hass: Any, respx_router: Any
) -> None:
    """The indicator is the latest message's sender role (T137, FR-037).

    Every branch is exercised in one setup: guest-last reads on,
    host-last reads off, and an empty thread reads unknown rather than
    guessing. The empty case matters because "no messages" is not "the
    host has replied".
    """
    mock_base_endpoints(respx_router)
    mock_threads(
        respx_router,
        responses={
            RESERVATION_A: [
                httpx.Response(
                    200,
                    json=thread("host", "guest", "guest"),
                    headers=THREAD_HEADERS,
                )
            ],
            RESERVATION_B: [
                httpx.Response(
                    200, json=thread("guest", "host"), headers=THREAD_HEADERS
                )
            ],
        },
    )
    await setup_message_entry(hass, **_enabled())

    assert _state(hass, PROPERTY_A, AWAITING_KEY).state == "on", (
        "a guest-authored latest message must read on"
    )
    assert _state(hass, PROPERTY_B, AWAITING_KEY).state == "off", (
        "a host-authored latest message must read off"
    )


async def test_an_empty_thread_reads_unknown(hass: Any, respx_router: Any) -> None:
    """An empty thread is unknown, not off (T137, FR-037).

    Reporting off would assert that the host has replied, which nothing
    in an empty thread supports.
    """
    mock_base_endpoints(respx_router)
    mock_threads(
        respx_router,
        responses={
            RESERVATION_A: [
                httpx.Response(200, json=empty_thread(), headers=THREAD_HEADERS)
            ],
            RESERVATION_B: [
                httpx.Response(200, json=empty_thread(), headers=THREAD_HEADERS)
            ],
        },
    )
    await setup_message_entry(hass, **_enabled())

    assert _state(hass, PROPERTY_A, AWAITING_KEY).state == "unknown", (
        "an empty thread must read unknown; off would claim the host replied"
    )


async def test_no_user_facing_text_ever_says_unread(
    hass: Any, respx_router: Any
) -> None:
    """Nothing anywhere calls the indicator "unread" (T137, FR-037).

    The upstream API has NO read-state field, so "unread" would be a
    claim the data cannot support. The scan runs only after the entity
    and its translated text are proved to exist, because a scan of text
    that has not been written yet finds no forbidden word for the wrong
    reason.
    """
    mock_base_endpoints(respx_router)
    mock_threads(respx_router)
    await setup_message_entry(hass, **_enabled())

    entity_id = message_entity_id(hass, PROPERTY_A, AWAITING_KEY)
    assert entity_id is not None, "no awaiting-host-reply sensor to inspect"
    state = hass.states.get(entity_id)
    assert state is not None
    friendly = str(state.attributes.get("friendly_name", ""))
    assert friendly, "the sensor has no friendly name to check"

    base = Path("custom_components/hospitable")
    strings = json.loads((base / "strings.json").read_text(encoding="utf-8"))
    english = json.loads((base / "translations/en.json").read_text(encoding="utf-8"))

    # The text must EXIST before its wording can be meaningfully checked.
    for payload, name in ((strings, "strings.json"), (english, "en.json")):
        assert AWAITING_KEY in payload["entity"]["sensor"], (
            f"{name} carries no awaiting_host_reply sensor text"
        )
        assert AWAITING_KEY in payload["options"]["step"]["init"]["data"], (
            f"{name} carries no awaiting_host_reply option label"
        )

    haystack = " ".join(
        [friendly, entity_id, json.dumps(strings), json.dumps(english)]
    ).casefold()
    assert "unread" not in haystack, (
        "user-facing text says 'unread'; the API exposes no read state"
    )


# --- T138: message bodies never reach an attribute or a log ------------


async def test_message_bodies_never_reach_an_attribute_or_a_log(
    hass: Any, respx_router: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """Bodies stay out of attributes and logs (T138, FR-024, FR-041).

    The recurring defect shape on this project is a control scoped to
    the WRONG surface: the chokepoint in ``actions/response.py`` guards
    SERVICE RESPONSES and does nothing for entity attributes. This is
    the entity-surface control, asserted independently.

    The indicator assertion is what makes the absence checks proof
    rather than tautology. It shows the thread really was fetched and
    really did drive an entity, so bodies genuinely flowed through the
    code path that is being checked for leaks.
    """
    caplog.set_level(logging.DEBUG)
    mock_base_endpoints(respx_router)
    mock_threads(respx_router)
    await setup_message_entry(hass, **_enabled())

    assert thread_requests(respx_router), "no thread was fetched, so nothing flowed"
    state = _state(hass, PROPERTY_A, AWAITING_KEY)
    assert state.state in {"on", "off"}, (
        f"the indicator did not derive a value ({state.state!r}), so the "
        "leak checks below would prove nothing"
    )

    rendered = json.dumps(dict(state.attributes), default=str)
    for body in PRIVATE_BODIES:
        assert body not in rendered, (
            f"a message body reached an entity attribute: {body!r}"
        )
    # A body fragment would leak just as badly as a whole body.
    assert "quillfeather" not in rendered.casefold(), (
        "a message body fragment reached an entity attribute"
    )

    logged = "\n".join(record.getMessage() for record in caplog.records)
    for body in PRIVATE_BODIES:
        assert body not in logged, f"a message body was logged: {body!r}"
    assert "quillfeather" not in logged.casefold(), "a message body was logged"

    # The strongest available control: a field with no permitted entity
    # surface should not be reachable from the coordinator's data at
    # all, so no future attribute can forget to guard it.
    MessagePresence = importlib.import_module(
        "custom_components.hospitable.coordinator_messages"
    ).MessagePresence

    assert not hasattr(MessagePresence, "body"), (
        "the presence record carries a message body field"
    )
    assert "body" not in getattr(MessagePresence, "__annotations__", {}), (
        "the presence record annotates a message body field"
    )


# --- T139: the options flow toggle -------------------------------------


async def test_the_options_flow_exposes_the_awaiting_toggle(
    hass: Any, respx_router: Any
) -> None:
    """The toggle is offered, defaults off, and is saved (T139, FR-038a).

    Driving the real options flow rather than reading the schema
    constant proves the option is reachable by a user, survives a
    submission, and lands in the stored options.
    """
    import voluptuous as vol

    from custom_components.hospitable.const import (
        CONF_AWAITING_HOST_REPLY,
        CONF_LOOKAHEAD_DAYS,
        CONF_LOOKBACK_DAYS,
        CONF_PROPERTY_INTERVAL,
        CONF_RESERVATION_INTERVAL,
        CONF_SELECTED_PROPERTIES,
        CONF_TASK_INTERVAL,
        CONF_TASK_WINDOW_DAYS,
    )

    mock_base_endpoints(respx_router)
    entry = await setup_message_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    schema = result["data_schema"].schema
    keys = {str(key.schema if isinstance(key, vol.Marker) else key) for key in schema}
    assert CONF_AWAITING_HOST_REPLY in keys, (
        f"the options flow offers no awaiting-host-reply toggle: {sorted(keys)}"
    )

    marker = next(
        key
        for key in schema
        if str(key.schema if isinstance(key, vol.Marker) else key)
        == CONF_AWAITING_HOST_REPLY
    )
    assert marker.default() is False, "the toggle does not default OFF"

    done = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_SELECTED_PROPERTIES: [PROPERTY_A, PROPERTY_B],
            CONF_RESERVATION_INTERVAL: 5,
            CONF_PROPERTY_INTERVAL: 60,
            CONF_LOOKBACK_DAYS: 30,
            CONF_LOOKAHEAD_DAYS: 30,
            CONF_TASK_INTERVAL: 15,
            CONF_TASK_WINDOW_DAYS: 14,
            CONF_AWAITING_HOST_REPLY: True,
        },
    )
    await hass.async_block_till_done()
    assert done["data"][CONF_AWAITING_HOST_REPLY] is True, (
        "the submitted toggle was not persisted"
    )


def test_the_toggle_description_states_the_cost_and_the_limitation() -> None:
    """The description names BOTH caveats (T139, FR-037, FR-038a).

    Two separate obligations that a single sentence often satisfies only
    one of: the additional API cost, and that this is not a read
    receipt. Both are asserted in both files, because a user reading a
    translated Home Assistant only ever sees one of them.
    """
    base = Path("custom_components/hospitable")
    for name in ("strings.json", "translations/en.json"):
        payload = json.loads((base / name).read_text(encoding="utf-8"))
        described = payload["options"]["step"]["init"]["data_description"]
        assert AWAITING_KEY in described, f"{name} has no toggle description"
        text = described[AWAITING_KEY].casefold()

        assert "off by default" in text, f"{name} does not state the default"
        assert any(word in text for word in ("request", "api call", "poll")), (
            f"{name} does not state the additional API cost"
        )
        assert "read receipt" in text, (
            f"{name} does not state that this is not a read receipt"
        )
        assert "unread" not in text, f"{name} uses the forbidden word 'unread'"


# --- Review follow-ups (PR #42) ----------------------------------------


async def test_a_naive_timestamp_is_read_as_utc_not_as_local(
    hass: Any, respx_router: Any
) -> None:
    """A naive last_message_at is UTC, not installation-local.

    ``dt_util.as_utc`` documents that it assumes a NAIVE value is in
    Home Assistant's configured zone, so handing one straight to it
    would shift the reading by the installation's offset. Every observed
    value from this endpoint carries a ``Z``, so a naive one is a
    malformed UTC value rather than a local one.

    The test sets a non-UTC HA zone deliberately. With the zone left at
    UTC the correct and incorrect implementations agree, and the test
    would pass either way.
    """
    await hass.config.async_set_time_zone("America/Los_Angeles")
    payload = reservations_payload(last_message_at_a="2026-08-12T18:45:00")
    mock_base_endpoints(respx_router, reservations=payload)
    await setup_message_entry(hass)

    state = _state(hass, PROPERTY_A, LAST_MESSAGE_KEY)
    assert state.state == "2026-08-12T18:45:00+00:00", (
        f"a naive timestamp read as {state.state!r}; it must be taken as "
        "UTC, not as the installation's local zone"
    )


async def test_an_offset_timestamp_is_normalised_to_utc(
    hass: Any, respx_router: Any
) -> None:
    """An offset-bearing last_message_at is converted, not passed through.

    Asserted on ``native_value``, NOT on the state string. Home
    Assistant renders a timestamp sensor by converting to UTC itself, so
    the state string is identical whether or not this sensor normalises,
    and a state assertion here would pass against an implementation that
    does no normalising at all. This was confirmed by deliberately
    removing the conversion: a state-based version of this test still
    passed, which is what a tautology looks like.

    So the normalisation is cosmetic as far as the state goes. It is
    still asserted because ``native_value`` is public API that templates
    and other integrations can read directly, where the offset would be
    visible.
    """
    payload = reservations_payload(last_message_at_a="2026-08-12T11:45:00-07:00")
    mock_base_endpoints(respx_router, reservations=payload)
    await setup_message_entry(hass)

    entity_id = message_entity_id(hass, PROPERTY_A, LAST_MESSAGE_KEY)
    assert entity_id is not None, "no last_message_at sensor to inspect"
    component = hass.data["entity_components"]["sensor"]
    entity = component.get_entity(entity_id)
    assert entity is not None, f"{entity_id} is registered but has no entity object"

    value = entity.native_value
    assert value is not None, "the sensor derived no value"
    assert value.utcoffset() == timedelta(0), (
        f"native_value carries offset {value.utcoffset()}, not UTC"
    )
    assert value.isoformat() == "2026-08-12T18:45:00+00:00", (
        f"an offset timestamp became {value.isoformat()!r}, not the same "
        "instant expressed in UTC"
    )


def test_the_compatibility_path_never_hands_out_a_stale_tracker() -> None:
    """``actions.rate_limit.TRACKER`` follows the canonical singleton.

    The tracker is a module-level singleton that the suite's reset
    fixture REBINDS. A compatibility module that bound the name at
    import time would keep handing out the object that existed when it
    was first imported, so callers arriving by that path would silently
    charge a different budget from everybody else — and would be exempt
    from the reset, leaking allowance between tests.
    """
    from custom_components.hospitable import rate_limit
    from custom_components.hospitable.actions import rate_limit as compat

    assert compat.TRACKER is rate_limit.TRACKER

    replacement = rate_limit.RateLimitTracker()
    original = rate_limit.TRACKER
    rate_limit.TRACKER = replacement
    try:
        assert compat.TRACKER is replacement, (
            "the compatibility path kept a stale tracker after a rebind"
        )
    finally:
        rate_limit.TRACKER = original


def test_the_message_poll_reaches_the_tracker_by_module_attribute() -> None:
    """The poll resolves TRACKER per call, so the reset reaches it.

    Asserted on the source rather than the behaviour because the failure
    this guards against is invisible in a single test: a name-bound
    import still WORKS, it just quietly stops being reset, and the
    resulting budget leak surfaces later as an unrelated flake in
    whichever test happens to run afterwards.
    """
    from tests.helpers.ast_isolation import scan_paths

    module = Path("custom_components/hospitable/coordinator_messages.py")
    scanned = scan_paths([module])
    assert scanned, "the scan did not reach the message coordinator"
    source = module.read_text(encoding="utf-8")
    bound_by_name = "from custom_components.hospitable.rate_limit import TRACKER"
    assert bound_by_name not in source, (
        "the message poll binds TRACKER by name, so the reset fixture cannot reach it"
    )
    assert "rate_limit.TRACKER" in source, (
        "the message poll does not reach the shared tracker at all"
    )
