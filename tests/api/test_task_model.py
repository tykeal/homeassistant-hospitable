# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for the ``HospitableTask`` model (US4, T115, T115a).

Parsing is driven through the client rather than through the model class
directly, so the red-phase failure is the absence of the BEHAVIOUR (no
``get_tasks``) rather than the absence of a file.

No request is ever made to the live host: every route is mocked.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Any

import httpx

from tests.helpers import load_fixture
from tests.helpers.task_entry import (
    PROPERTY_A,
    TEAMMATE_NAME_A,
    as_single_page,
    tasks_page,
)

WINDOW = (date(2026, 8, 12), date(2026, 8, 26))


def _single_page(**overrides: Any) -> Any:
    """Return a one-page task envelope rebased onto property A.

    Args:
        **overrides: Keys to set on the FIRST task in the page.

    Returns:
        The rewritten envelope.
    """
    payload = as_single_page(tasks_page("tasks_page1.json", PROPERTY_A))
    payload["data"][0].update(overrides)
    return payload


async def _fetch(client: Any, router: Any, payload: Any) -> Any:
    """Fetch tasks for property A against a mocked one-page response.

    Args:
        client: The API client under test.
        router: The active respx router.
        payload: Response body to serve.

    Returns:
        The parsed tasks.
    """
    from custom_components.hospitable.api.const import BASE_URL

    router.get(f"{BASE_URL}/tasks").mock(return_value=httpx.Response(200, json=payload))
    return await client.get_tasks(PROPERTY_A, *WINDOW)


async def test_the_model_parses_every_scheduling_field(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """Scheduling and assignment fields are parsed (T115, FR-035).

    There is NO ``scheduled_date`` upstream. Scheduling is ``start_date``
    and ``end_date`` (full ISO-8601 with offset), an IANA ``timezone``
    string, and an integer ``duration_hours``. Assignment status is
    nested under ``task_assignment``, not flat.
    """
    client = api_client_factory(mock_httpx_client, synthetic_token)
    tasks = await _fetch(client, respx_router, _single_page())

    task = next(item for item in tasks if item.name == "H-SYNTH-001")
    assert task.task_id == "11111111-1111-4111-8111-111111111111"
    assert isinstance(task.task_id, str), "the upstream id is a UUID string"
    assert task.timezone == "America/Los_Angeles"
    assert task.duration_hours == 5
    assert task.start_date.endswith("-07:00")
    assert task.end_date.endswith("-07:00")
    assert task.assignment_status == "accepted"
    assert task.assignment_updated_at == "2026-08-12T18:00:00+00:00"
    assert task.reservation_id == "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1"
    assert task.teammate_id == "cccccccc-cccc-4ccc-8ccc-ccccccccccc1"


async def test_a_null_progress_status_is_preserved(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """``progress_status`` is nullable and stays ``None`` (T115, FR-035).

    54 of 153 live tasks carried ``null`` here. Anything that assumes a
    string breaks on more than a third of real data.
    """
    client = api_client_factory(mock_httpx_client, synthetic_token)
    tasks = await _fetch(client, respx_router, _single_page())

    by_name = {task.name: task for task in tasks}
    assert by_name["H-SYNTH-001"].progress_status is None
    assert by_name["H-SYNTH-002"].progress_status == "completed"


async def test_the_property_association_is_read_from_nested_property_id(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """The parser reads ``property.id`` and nothing else (T115a, FR-032).

    This is the answer to the open question the live capture closed:
    tasks carry ``property`` as a nested object; there is NO flat
    ``property_id`` key on any of the 153 observed objects. The parser
    MUST NOT accept both shapes, because a permissive reader would hide
    a future upstream drift permanently.
    """
    client = api_client_factory(mock_httpx_client, synthetic_token)

    # The recorded fixture must carry only the live-confirmed shape.
    recorded = load_fixture("tasks_page1.json")["data"][0]
    assert "property_id" not in recorded, "the fixture must not invent a flat key"
    assert recorded["property"]["id"], "the fixture must carry nested property.id"

    tasks = await _fetch(client, respx_router, _single_page())
    assert tasks[0].property_id == PROPERTY_A

    # A payload carrying ONLY the flat key must not resolve. Accepting it
    # would make the parser permissive and hide drift forever.
    drifted = _single_page()
    for task in drifted["data"]:
        task.pop("property")
        task["property_id"] = "flat-key-must-not-be-read"
    tasks = await _fetch(client, respx_router, drifted)
    assert all(task.property_id != "flat-key-must-not-be-read" for task in tasks), (
        "the parser accepted a flat property_id"
    )


async def test_the_teammate_personal_name_is_never_a_model_field(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """``teammate.name`` is not parsed at all (T115, T120, FR-042).

    This follows the US3 ``profile_picture`` precedent exactly: a field
    with no permitted exposure surface is never read into the model, so
    it cannot leak onto an entity attribute, a service response, a
    diagnostic, a log, or an exception path someone forgets to guard.
    ``teammate.id`` is opaque and is retained.
    """
    client = api_client_factory(mock_httpx_client, synthetic_token)
    payload = _single_page()
    assert payload["data"][0]["teammate"]["name"] == TEAMMATE_NAME_A, (
        "the fixture must actually carry a teammate name for this to prove anything"
    )

    tasks = await _fetch(client, respx_router, payload)

    task = tasks[0]
    fields = {field.name for field in dataclasses.fields(task)}
    assert "teammate_name" not in fields
    assert "teammate" not in fields
    assert task.teammate_id
    for value in dataclasses.asdict(task).values():
        assert value != TEAMMATE_NAME_A, "a teammate personal name reached the model"


async def test_free_text_and_guest_adjacent_fields_are_not_model_fields(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """``note`` and ``reservation.code`` are dropped entirely (FR-042).

    An earlier draft of ``data-model.md`` kept both as model fields
    "protected" at the entity surface. That is the exact defect shape
    this project has hit repeatedly: a control scoped to ONE surface
    while the data sits parsed and available on another. Neither has any
    consumer in US4, ``note`` is free text and ``reservation.code`` is
    guest-adjacent, so neither is parsed at all. ``reservation.id`` is
    kept because linking a task to a reservation is genuinely useful.
    """
    client = api_client_factory(mock_httpx_client, synthetic_token)
    payload = _single_page()
    note = payload["data"][1]["note"]
    code = payload["data"][0]["reservation"]["code"]
    assert note and code, "the fixture must carry both for this to prove anything"

    tasks = await _fetch(client, respx_router, payload)

    for task in tasks:
        fields = {field.name for field in dataclasses.fields(task)}
        assert "note" not in fields
        assert "reservation_code" not in fields
        values = set(dataclasses.asdict(task).values())
        assert note not in values
        assert code not in values
    assert tasks[0].reservation_id, "reservation.id is retained deliberately"
