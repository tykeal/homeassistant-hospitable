# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for the ``GET /tasks`` request and model (US4).

Every request-shape test here runs over a REAL entry setup rather than
against a request builder in isolation. That choice is deliberate: a
builder test would fail in the red phase with ``ModuleNotFoundError``,
which proves only that a file is absent. Driving the real setup makes
the red-phase failure an ``AssertionError`` about traffic that the
integration does not yet produce, which is the behaviour the requirement
actually names.

The model and vocabulary tests go through the client method, so their
red-phase failure is the absence of that method rather than the absence
of a file.

No request is ever made to the live host: every route is mocked.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx
import pytest

from tests.helpers import load_fixture
from tests.helpers.task_entry import (
    PROPERTY_A,
    PROPERTY_B,
    empty_tasks_page,
    mock_base_endpoints,
    mock_tasks,
    setup_task_entry,
    tasks_page,
)

# The recorded fixture's own synthetic property id, used only where a
# test reads the RAW fixture rather than the rebased harness payload.
FIXTURE_PROPERTY_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"


def _task_requests(route: Any) -> list[httpx.Request]:
    """Return every recorded ``/tasks`` request.

    Args:
        route: The mocked ``/tasks`` route.

    Returns:
        The captured requests, in order.
    """
    return [call.request for call in route.calls]


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T109 no tasks poll exists, so no request carries "
    "properties[]",
)
async def test_every_tasks_request_carries_a_single_property(
    hass: Any, respx_router: Any
) -> None:
    """Each ``/tasks`` request names exactly one property (T109, FR-030).

    ``properties[]`` is mandatory upstream: a bare request is a 400.
    """
    mock_base_endpoints(respx_router)
    route = mock_tasks(respx_router)
    from tests.helpers.task_entry import build_entry

    entry = build_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    requests = _task_requests(route)
    assert requests, "the polling lifecycle issued no /tasks request"
    for request in requests:
        values = request.url.params.get_list("properties[]")
        assert len(values) == 1, f"expected one property, got {values}"
        assert values[0], "properties[] must never be empty"


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T109a the tasks poll does not fan out yet",
)
async def test_the_poll_fans_out_to_one_request_per_property(
    hass: Any, respx_router: Any
) -> None:
    """N selected properties produce N separate requests (T109a, FR-030).

    Fan-out is what makes per-property failure isolation possible at
    all: a batched request has ONE outcome for every property.
    """
    mock_base_endpoints(respx_router)
    route = mock_tasks(
        respx_router,
        responses={
            PROPERTY_A: [httpx.Response(200, json=empty_tasks_page())],
            PROPERTY_B: [httpx.Response(200, json=empty_tasks_page())],
        },
    )
    from tests.helpers.task_entry import build_entry

    entry = build_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    requests = _task_requests(route)
    assert len(requests) == 2, f"expected one request per property, got {len(requests)}"
    named = [request.url.params.get_list("properties[]") for request in requests]
    for values in named:
        assert len(values) == 1, f"a request named two properties: {values}"
    assert {values[0] for values in named} == {PROPERTY_A, PROPERTY_B}


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T110 no request carries the configured window",
)
async def test_the_request_carries_the_configured_forward_window(
    hass: Any, respx_router: Any
) -> None:
    """Dates are explicit and derived from the option (T110, FR-030).

    FR-030 was amended to REQUIRE explicit dates rather than relying on
    Hospitable's undocumented roughly 14-day default: an undocumented
    default makes the meaning of ``task_count`` unstable. ``start_date``
    is today and ``end_date`` is today plus ``task_window_days``.
    """
    mock_base_endpoints(respx_router)
    route = mock_tasks(respx_router)
    from tests.helpers.task_entry import build_entry

    entry = build_entry(task_window_days=21)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    requests = _task_requests(route)
    assert requests, "the polling lifecycle issued no /tasks request"
    today = date.today()
    for request in requests:
        params = request.url.params
        start = params.get("start_date")
        end = params.get("end_date")
        assert start is not None, "start_date must always be sent"
        assert end is not None, "end_date must always be sent"
        assert date.fromisoformat(start) == today
        assert date.fromisoformat(end) == today + timedelta(days=21)
        # A dates-only request is a 400 upstream, so one must never
        # be constructed: every dated request also names a property.
        assert params.get_list("properties[]"), (
            "a dates-only request was constructed, which is a 400 upstream"
        )


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T110 the default window is not applied yet",
)
async def test_the_window_defaults_to_fourteen_days(
    hass: Any, respx_router: Any
) -> None:
    """With no option set the window is 14 days forward (T110, FR-030).

    14 matches the upstream default measured on 2026-08-12, so an
    existing user's task counts do not change when the explicit dates
    start being sent.
    """
    mock_base_endpoints(respx_router)
    route = mock_tasks(respx_router)
    from tests.helpers.task_entry import build_entry

    entry = build_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    requests = _task_requests(route)
    assert requests, "the polling lifecycle issued no /tasks request"
    params = requests[0].url.params
    start = params.get("start_date")
    end = params.get("end_date")
    assert start is not None and end is not None
    assert date.fromisoformat(end) - date.fromisoformat(start) == timedelta(days=14)


@pytest.mark.xfail(
    raises=AttributeError,
    strict=True,
    reason="TDD red phase: T111 the client has no get_tasks method",
)
async def test_a_tasks_400_is_parsed_by_the_shared_envelope_parser(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """A ``/tasks`` 400 surfaces the Laravel envelope (T111, FR-045).

    The SAME parser already serves the message-send 422. Proving it also
    serves this 400 is what stops a second, divergent parser appearing.
    """
    from custom_components.hospitable.api.const import BASE_URL
    from custom_components.hospitable.api.exceptions import (
        HospitableRequestValidationError,
    )

    client = api_client_factory(mock_httpx_client, synthetic_token)
    respx_router.get(f"{BASE_URL}/tasks").mock(
        return_value=httpx.Response(400, json=load_fixture("error_envelope_400.json"))
    )

    with pytest.raises(HospitableRequestValidationError) as caught:
        await client.get_tasks(PROPERTY_A, date(2026, 8, 12), date(2026, 8, 26))

    assert caught.value.status == 400
    assert "properties field is required" in str(caught.value)
    assert caught.value.field_messages == ["The properties field is required."]


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T112 nothing paginates /tasks yet",
)
async def test_pagination_is_followed_from_day_one(
    hass: Any, respx_router: Any
) -> None:
    """Both recorded pages are fetched and combined (T112, FR-031).

    A naive single-page fetch silently loses tasks, so paging is proved
    by the COMBINED result rather than by the request count alone.
    """
    entry = await setup_task_entry(hass, respx_router)

    coordinator = entry.runtime_data["coordinators"].get("tasks")
    assert coordinator is not None, "no tasks coordinator exists"
    tasks = coordinator.data[PROPERTY_A]
    assert len(tasks) == 3, f"expected both pages combined, got {len(tasks)}"
    names = {task.name for task in tasks}
    assert names == {"H-SYNTH-001", "H-SYNTH-002", "H-SYNTH-003"}


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T112a no per-property page count is followed",
)
async def test_pagination_is_followed_per_property(
    hass: Any, respx_router: Any
) -> None:
    """Each property's own ``meta.last_page`` is followed (T112a, FR-031).

    Property A reports two pages, property B reports one. A shared page
    count taken from whichever property answered first would either lose
    a task or issue a pointless request.
    """
    mock_base_endpoints(respx_router)
    route = mock_tasks(respx_router)
    from tests.helpers.task_entry import build_entry

    entry = build_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    per_property: dict[str, int] = {}
    for request in _task_requests(route):
        property_id = request.url.params.get("properties[]", "")
        per_property[property_id] = per_property.get(property_id, 0) + 1

    assert per_property.get(PROPERTY_A) == 2, (
        f"property A reports last_page 2 and must be fetched twice, "
        f"got {per_property.get(PROPERTY_A)}"
    )
    assert per_property.get(PROPERTY_B) == 1, (
        f"property B reports last_page 1 and must be fetched once, "
        f"got {per_property.get(PROPERTY_B)}"
    )


@pytest.mark.xfail(
    raises=AttributeError,
    strict=True,
    reason="TDD red phase: T113 the client has no get_tasks method",
)
async def test_enum_labels_come_from_the_response_meta_block(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """Labels are read from ``meta``, never hardcoded (T113, FR-033).

    The response's vocabulary is edited to a value no hardcoded table
    could contain. If the label still comes back as the real one, the
    table was baked into the integration.
    """
    from custom_components.hospitable.api.const import BASE_URL

    payload = tasks_page("tasks_page1.json", PROPERTY_A)
    payload["meta"]["last_page"] = 1
    payload["meta"]["task_types"]["1"]["label"] = "Vocabulary From Meta"
    client = api_client_factory(mock_httpx_client, synthetic_token)
    respx_router.get(f"{BASE_URL}/tasks").mock(
        return_value=httpx.Response(200, json=payload)
    )

    tasks = await client.get_tasks(PROPERTY_A, date(2026, 8, 12), date(2026, 8, 26))

    by_name = {task.name: task for task in tasks}
    assert by_name["H-SYNTH-001"].task_type_label == "Vocabulary From Meta"


@pytest.mark.xfail(
    raises=AttributeError,
    strict=True,
    reason="TDD red phase: T114 the client has no get_tasks method",
)
async def test_task_types_and_service_types_are_never_interchanged(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """The Maintenance trap is not fallen into (T114, FR-033).

    ``meta.task_types["5"]`` is Maintenance with ``service_id`` 8, while
    ``meta.service_types["5"]`` is **Owner**. Looking a task_type up in
    the service-type table therefore produces a WRONG LABEL rather than
    an error, which is exactly why it must be proved impossible.

    Stated honestly: all 153 live tasks were ``task_type: 1`` with
    ``service_id: 1``, so a divergent task was never observed live. The
    evidence for the trap is the meta vocabulary itself, and the fixture
    carries a clearly-marked synthetic task so it can be exercised.
    """
    from custom_components.hospitable.api.const import BASE_URL

    payload = tasks_page("tasks_page1.json", PROPERTY_A)
    payload["meta"]["last_page"] = 1
    assert payload["meta"]["task_types"]["5"]["label"] == "Maintenance"
    assert payload["meta"]["task_types"]["5"]["service_id"] == 8
    assert payload["meta"]["service_types"]["5"]["label"] == "Owner"
    assert payload["meta"]["service_types"]["8"]["label"] == "Maintenance"

    client = api_client_factory(mock_httpx_client, synthetic_token)
    respx_router.get(f"{BASE_URL}/tasks").mock(
        return_value=httpx.Response(200, json=payload)
    )

    tasks = await client.get_tasks(PROPERTY_A, date(2026, 8, 12), date(2026, 8, 26))

    maintenance = next(task for task in tasks if task.task_type == 5)
    assert maintenance.service_id == 8
    assert maintenance.task_type_label == "Maintenance"
    assert maintenance.task_type_label != "Owner", (
        "task_type 5 was labelled from the service-type table"
    )
    # The service label comes from service_id 8, not from task_type 5.
    assert maintenance.service_type_label == "Maintenance"
