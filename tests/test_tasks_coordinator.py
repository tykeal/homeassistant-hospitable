# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for the tasks coordinator (US4, T116, T117, T117a).

Every test drives a REAL entry setup, so a red-phase failure is an
``AssertionError`` about behaviour the integration does not yet have
rather than an import error about a file that does not yet exist.

No request is ever made to the live host: every route is mocked.
"""

from __future__ import annotations

from typing import Any

import httpx

from tests.helpers.task_entry import (
    PROPERTY_A,
    PROPERTY_B,
    as_single_page,
    build_entry,
    empty_tasks_page,
    mock_base_endpoints,
    mock_tasks,
    setup_task_entry,
    tasks_page,
)


async def test_the_tasks_coordinator_exists_and_holds_a_base_client(
    hass: Any, respx_router: Any
) -> None:
    """The tasks coordinator exists and is read-only (T116, FR-001).

    Write isolation is not optional for a new coordinator: it MUST hold
    the base GET-only client, never the write client, so a write call
    site on it is a type error rather than a runtime surprise.
    """
    from custom_components.hospitable.api.client import HospitableApiClient
    from custom_components.hospitable.api.write_client import HospitableWriteClient

    entry = await setup_task_entry(hass, respx_router)

    coordinators = entry.runtime_data["coordinators"]
    assert "tasks" in coordinators, f"no tasks coordinator: {sorted(coordinators)}"
    coordinator = coordinators["tasks"]
    assert isinstance(coordinator.client, HospitableApiClient)
    assert not isinstance(coordinator.client, HospitableWriteClient)


async def test_the_tasks_coordinator_polls_on_its_own_cadence(
    hass: Any, respx_router: Any
) -> None:
    """The tasks cadence is separate from every other one (T116, FR-034)."""
    from datetime import timedelta

    entry = await setup_task_entry(hass, respx_router, task_interval_minutes=25)

    coordinators = entry.runtime_data["coordinators"]
    assert "tasks" in coordinators, f"no tasks coordinator: {sorted(coordinators)}"
    tasks = coordinators["tasks"]
    assert tasks.update_interval == timedelta(minutes=25)
    assert tasks.update_interval != coordinators["reservations"].update_interval
    assert tasks is not coordinators["calendar"]


async def test_the_task_interval_defaults_to_fifteen_minutes(
    hass: Any, respx_router: Any
) -> None:
    """With no option set the cadence is 15 minutes (T117, FR-034)."""
    from datetime import timedelta

    entry = await setup_task_entry(hass, respx_router)

    coordinators = entry.runtime_data["coordinators"]
    assert "tasks" in coordinators, f"no tasks coordinator: {sorted(coordinators)}"
    assert coordinators["tasks"].update_interval == timedelta(minutes=15)


async def test_the_task_interval_is_clamped_to_a_five_minute_floor(
    hass: Any, respx_router: Any
) -> None:
    """A below-floor interval is raised to 5 minutes (T117, FR-034).

    The floor protects the upstream account from a user who sets a
    one-minute cadence across thirteen properties.
    """
    from datetime import timedelta

    entry = await setup_task_entry(hass, respx_router, task_interval_minutes=1)

    coordinators = entry.runtime_data["coordinators"]
    assert "tasks" in coordinators, f"no tasks coordinator: {sorted(coordinators)}"
    assert coordinators["tasks"].update_interval == timedelta(minutes=5)


async def test_one_failing_property_keeps_its_last_good_task_data(
    hass: Any, respx_router: Any
) -> None:
    """A single property's failure is isolated (T117a, FR-034, D-15).

    This mirrors the spec 001 calendar coordinator exactly rather than
    inventing a second pattern: the failing property retains its
    previous task data instead of being cleared or dropped, the other
    properties still update, and the refresh as a whole still succeeds.
    """
    mock_base_endpoints(respx_router)
    first_a = as_single_page(tasks_page("tasks_page1.json", PROPERTY_A))
    second_b = as_single_page(tasks_page("tasks_page2.json", PROPERTY_B))
    mock_tasks(
        respx_router,
        responses={
            # Cycle one succeeds for both; cycle two fails only for A.
            PROPERTY_A: [
                httpx.Response(200, json=first_a),
                httpx.Response(500, json={"message": "upstream is unwell"}),
            ],
            PROPERTY_B: [
                httpx.Response(200, json=empty_tasks_page()),
                httpx.Response(200, json=second_b),
            ],
        },
    )
    entry = build_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinators = entry.runtime_data["coordinators"]
    assert "tasks" in coordinators, f"no tasks coordinator: {sorted(coordinators)}"
    coordinator = coordinators["tasks"]
    assert len(coordinator.data[PROPERTY_A]) == 2, "cycle one did not land"
    assert coordinator.data[PROPERTY_B] == ()

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.last_update_success, "one failing property aborted the refresh"
    # The failing property keeps its last-good data rather than emptying.
    assert len(coordinator.data[PROPERTY_A]) == 2, (
        "the failing property lost its last-good task data"
    )
    # The healthy property still updated in the same cycle.
    assert len(coordinator.data[PROPERTY_B]) == 1


async def test_a_refresh_fails_only_when_every_property_fails(
    hass: Any, respx_router: Any
) -> None:
    """Total failure is still a failure (T117a, FR-034).

    Isolation must not become silent success: when NO property returned
    data the refresh has to report failure, or the entities would report
    confident stale values through a total outage.
    """
    mock_base_endpoints(respx_router)
    mock_tasks(
        respx_router,
        responses={
            PROPERTY_A: [
                httpx.Response(200, json=empty_tasks_page()),
                httpx.Response(500, json={"message": "upstream is unwell"}),
            ],
            PROPERTY_B: [
                httpx.Response(200, json=empty_tasks_page()),
                httpx.Response(500, json={"message": "upstream is unwell"}),
            ],
        },
    )
    entry = build_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    coordinators = entry.runtime_data["coordinators"]
    assert "tasks" in coordinators, f"no tasks coordinator: {sorted(coordinators)}"
    coordinator = coordinators["tasks"]
    assert coordinator.last_update_success

    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not coordinator.last_update_success, (
        "every property failed but the refresh reported success"
    )
