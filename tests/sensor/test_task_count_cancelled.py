# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the cancelled task progress bucket (D1, FR-001 to FR-008).

This module covers Deliverable 1 of spec 004: a fourth
``CANCELLED_STATUSES`` bucket on the task-count sensor so that the
four breakdown attributes sum to ``task_count`` while the upstream
vocabulary remains the known six values, plus a vocabulary drift
guard that logs unknown statuses.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

import httpx
import pytest

from tests.helpers.task_entry import (
    PROPERTY_A,
    PROPERTY_B,
    build_entry,
    empty_tasks_page,
    mock_base_endpoints,
    mock_tasks,
    task_entity_id,
)


def _synthetic_task(
    progress_status: str | None,
    *,
    assignment_status: str | None = None,
    task_id: str = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
) -> dict[str, Any]:
    """Build a SYNTHETIC task dict for testing.

    No cancelled task has been observed in live data. All fixtures
    containing ``progress_status="cancelled"`` are synthetic
    constructs created to exercise vocabulary-driven behaviour.

    Args:
        progress_status: The progress_status value (may be None).
        assignment_status: The assignment_status value (may be None).
        task_id: A unique task id.

    Returns:
        A minimal task dict matching the recorded fixture shape.
    """
    return {
        "id": task_id,
        "task_type": 1,
        "service_id": 1,
        "assignment_status": assignment_status,
        "assignment_updated_at": None,
        "progress_status": progress_status,
        "start_date": "2099-01-01T10:00:00-07:00",
        "end_date": "2099-01-01T14:00:00-07:00",
        "timezone": "America/Los_Angeles",
        "duration_hours": 4,
        "reservation_id": None,
        "teammate_id": None,
        "property": {"id": PROPERTY_A, "name": PROPERTY_A},
        "note": None,
        "reservation": None,
    }


def _build_page(
    tasks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Wrap tasks in a well-formed single-page envelope.

    Args:
        tasks: Task dicts to include.

    Returns:
        A single-page task response envelope with meta vocabularies.
    """
    base = copy.deepcopy(empty_tasks_page())
    base["data"] = tasks
    base["meta"]["total"] = len(tasks)
    return base


def _all_six_statuses_page() -> dict[str, Any]:
    """Build a SYNTHETIC page with one task per known progress status.

    Includes a null-progress task (treated as pending). All fixtures
    here are synthetic — no cancelled task has been observed in live
    data.

    Returns:
        A single-page envelope with seven tasks spanning all six
        known progress_status values plus null.
    """
    statuses = [
        "not_started",
        "on_the_way",
        "arrived",
        "in_progress",
        "completed",
        "cancelled",
        None,
    ]
    tasks = []
    for i, status in enumerate(statuses):
        c = "abcdef0"[i]
        tid = f"{c * 8}-{c * 4}-4{c * 3}-8{c * 3}-{c * 12}"
        tasks.append(_synthetic_task(status, task_id=tid))
    return _build_page(tasks)


async def _setup_with_tasks(
    hass: Any,
    respx_router: Any,
    page: dict[str, Any],
) -> Any:
    """Set up the integration with a custom task page for property A.

    Args:
        hass: The Home Assistant test instance.
        respx_router: The active respx router.
        page: The task page to serve for property A.

    Returns:
        The loaded config entry.
    """
    from homeassistant.config_entries import ConfigEntryState

    mock_base_endpoints(respx_router)
    mock_tasks(
        respx_router,
        responses={
            PROPERTY_A: [httpx.Response(200, json=page)],
            PROPERTY_B: [httpx.Response(200, json=empty_tasks_page())],
        },
    )
    entry = build_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


def _attrs(hass: Any, property_id: str) -> dict[str, Any]:
    """Return the task-count sensor's extra_state_attributes.

    Args:
        hass: The Home Assistant test instance.
        property_id: Property whose sensor is wanted.

    Returns:
        The attributes dict.
    """
    eid = task_entity_id(hass, property_id, "task_count")
    assert eid is not None
    state = hass.states.get(eid)
    assert state is not None
    return dict(state.attributes)


# ── T010: CANCELLED_STATUSES import (FR-001) ────────────────────


def test_cancelled_statuses_import() -> None:
    """``CANCELLED_STATUSES`` is importable and equals the expected set."""
    from custom_components.hospitable.sensor.tasks import (
        CANCELLED_STATUSES,
    )

    assert frozenset({"cancelled"}) == CANCELLED_STATUSES


# ── T011: Exhaustiveness / vocabulary contract (FR-007) ──────────


def test_exhaustiveness() -> None:
    """The union of all four frozensets equals the known vocabulary."""
    from custom_components.hospitable.sensor.tasks import (
        CANCELLED_STATUSES,
        COMPLETED_STATUSES,
        IN_PROGRESS_STATUSES,
        PENDING_STATUSES,
    )

    known = {
        "not_started",
        "on_the_way",
        "arrived",
        "in_progress",
        "completed",
        "cancelled",
    }
    assert (
        known
        == PENDING_STATUSES
        | IN_PROGRESS_STATUSES
        | COMPLETED_STATUSES
        | CANCELLED_STATUSES
    )


# ── T012: cancelled_count present in attributes (FR-003) ────────


async def test_cancelled_count_present(hass: Any, respx_router: Any) -> None:
    """``cancelled_count`` appears in extra_state_attributes.

    SYNTHETIC fixture — no cancelled task observed in live data.
    """
    page = _build_page(
        [
            _synthetic_task(
                "cancelled", task_id="cc000000-0000-4000-8000-000000000001"
            ),
        ]
    )
    await _setup_with_tasks(hass, respx_router, page)
    attrs = _attrs(hass, PROPERTY_A)
    assert attrs["cancelled_count"] >= 0


# ── T013: cancelled increments only cancelled_count (FR-002/003) ─


async def test_cancelled_increments_cancelled_count_only(
    hass: Any, respx_router: Any
) -> None:
    """A cancelled task increments only ``cancelled_count``.

    SYNTHETIC fixture — keyed on ``progress_status``, NOT
    ``assignment_status``. Both vocabularies contain ``cancelled``
    but they are different dimensions.
    """
    page = _build_page(
        [
            _synthetic_task(
                "cancelled",
                assignment_status=None,
                task_id="cc000000-0000-4000-8000-000000000002",
            ),
        ]
    )
    await _setup_with_tasks(hass, respx_router, page)
    attrs = _attrs(hass, PROPERTY_A)
    assert attrs["cancelled_count"] == 1
    assert attrs["pending_count"] == 0
    assert attrs["in_progress_count"] == 0
    assert attrs["completed_count"] == 0


# ── T014: four buckets sum to task_count (FR-005) ────────────────


async def test_buckets_sum_to_task_count(hass: Any, respx_router: Any) -> None:
    """The four bucket counts sum to the sensor's native_value.

    SYNTHETIC fixture spanning all six known progress_status values
    plus null (treated as pending).
    """
    page = _all_six_statuses_page()
    await _setup_with_tasks(hass, respx_router, page)
    attrs = _attrs(hass, PROPERTY_A)
    eid = task_entity_id(hass, PROPERTY_A, "task_count")
    assert eid is not None
    state = hass.states.get(eid)
    assert state is not None
    total = int(state.state)
    bucket_sum = (
        attrs["pending_count"]
        + attrs["in_progress_count"]
        + attrs["completed_count"]
        + attrs["cancelled_count"]
    )
    assert bucket_sum == total


# ── T015: vocabulary drift guard (FR-006) ────────────────────────


async def test_drift_guard_logs_unknown_status(
    hass: Any, respx_router: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """An unknown progress_status triggers a logged warning.

    SYNTHETIC fixture with a fabricated status value.
    """
    page = _build_page(
        [
            _synthetic_task(
                "teleported",
                task_id="dd000000-0000-4000-8000-000000000001",
            ),
        ]
    )
    with caplog.at_level(logging.WARNING):
        await _setup_with_tasks(hass, respx_router, page)
    assert any("teleported" in rec.message for rec in caplog.records)


# ── T016: null still pending + four buckets sum (FR-004/005) ─────


async def test_null_progress_still_pending_and_buckets_sum(
    hass: Any, respx_router: Any
) -> None:
    """Null progress_status increments pending; four buckets sum.

    SYNTHETIC fixture. Null has always been treated as not-yet-started;
    this test confirms that behaviour is unchanged after adding the
    cancelled bucket, and that the sum guarantee holds.
    """
    page = _build_page(
        [
            _synthetic_task(None, task_id="ee000000-0000-4000-8000-000000000001"),
            _synthetic_task(
                "completed", task_id="ee000000-0000-4000-8000-000000000002"
            ),
        ]
    )
    await _setup_with_tasks(hass, respx_router, page)
    attrs = _attrs(hass, PROPERTY_A)
    assert attrs["pending_count"] == 1, "null should count as pending"

    eid = task_entity_id(hass, PROPERTY_A, "task_count")
    assert eid is not None
    state = hass.states.get(eid)
    assert state is not None
    total = int(state.state)
    bucket_sum = (
        attrs["pending_count"]
        + attrs["in_progress_count"]
        + attrs["completed_count"]
        + attrs["cancelled_count"]
    )
    assert bucket_sum == total
