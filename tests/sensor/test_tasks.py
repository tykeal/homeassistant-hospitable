# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase end-to-end tests for the task sensors (US4, T118 to T120).

Nothing here is a unit test on a parser: a real ``hass``, a real
``MockConfigEntry``, the real entity registry, and ``respx``-mocked
endpoints drive the whole platform against the recorded task fixtures.
If the request shape, the pagination, the model, the coordinator
fan-out, the platform forward, or the privacy exclusions were broken,
these would fail.

No request is ever made to the live host: every route is mocked.
"""

from __future__ import annotations

import importlib
from typing import Any

from tests.helpers.task_entry import (
    PROPERTY_A,
    PROPERTY_B,
    RESERVATION_CODE,
    TASK_NOTE,
    TEAMMATE_NAME_A,
    TEAMMATE_NAME_B,
    setup_task_entry,
    task_entity_id,
)


def _raw_page_one() -> Any:
    """Return the untouched recorded first task page.

    Returns:
        The fixture content, used to prove a value really is present
        before asserting its absence elsewhere.
    """
    from tests.helpers import load_fixture

    return load_fixture("tasks_page1.json")


def _state(hass: Any, property_id: str, key: str) -> Any:
    """Return a task sensor's state object, asserting it is registered.

    Args:
        hass: The Home Assistant test instance.
        property_id: Property whose sensor is wanted.
        key: Entity key, ``next_task`` or ``task_count``.

    Returns:
        The entity state.
    """
    entity_id = task_entity_id(hass, property_id, key)
    assert entity_id is not None, f"no {key} sensor registered for {property_id}"
    state = hass.states.get(entity_id)
    assert state is not None, f"{key} sensor for {property_id} has no state"
    return state


async def test_a_next_task_sensor_exists_per_property(
    hass: Any, respx_router: Any
) -> None:
    """Every selected property gets a next-task sensor (T118, FR-032)."""
    await setup_task_entry(hass, respx_router)

    for property_id in (PROPERTY_A, PROPERTY_B):
        assert task_entity_id(hass, property_id, "next_task") is not None, (
            f"no next_task sensor for {property_id}"
        )


async def test_the_next_task_state_is_the_soonest_task_type_label(
    hass: Any, respx_router: Any
) -> None:
    """The state is the soonest upcoming task's type label (T118, FR-032).

    The harness rebases the recorded tasks onto today+1, +2 and +3, so
    the soonest is the ``task_type: 1`` Cleaning task. The label comes
    from ``meta.task_types``, never from a hardcoded table.
    """
    await setup_task_entry(hass, respx_router)

    state = _state(hass, PROPERTY_A, "next_task")
    assert state.state == "Cleaning"
    assert state.attributes["task_type"] == 1
    assert state.attributes["service_id"] == 1
    assert state.attributes["assignment_status"] == "accepted"
    assert state.attributes["progress_status"] is None
    assert state.attributes["duration_hours"] == 5
    assert state.attributes["timezone"] == "America/Los_Angeles"
    assert state.attributes["task_id"]
    assert state.attributes["reservation_id"]
    assert state.attributes["teammate_id"]


async def test_a_property_with_no_tasks_reports_no_next_task(
    hass: Any, respx_router: Any
) -> None:
    """A property with no tasks has a next-task sensor with no value.

    The sensor must still EXIST, so an empty window is visibly empty
    rather than indistinguishable from a broken integration (T118).
    """
    await setup_task_entry(hass, respx_router)

    state = _state(hass, PROPERTY_B, "next_task")
    assert state.state in ("unknown", "None", ""), state.state


async def test_the_task_count_spans_every_page(hass: Any, respx_router: Any) -> None:
    """The count equals the combined total across ALL pages (T119, FR-031).

    This is the Phase 6 independent test: property A serves both
    recorded pages and its count must be the combined total, which is
    also the ``meta.total`` the fixture reports. A naive single-page
    fetch would report 2.
    """
    await setup_task_entry(hass, respx_router)

    state = _state(hass, PROPERTY_A, "task_count")
    assert state.state == "3", f"expected both pages combined, got {state.state}"
    empty = _state(hass, PROPERTY_B, "task_count")
    assert empty.state == "0"


async def test_the_task_count_breaks_down_by_progress(
    hass: Any, respx_router: Any
) -> None:
    """The count sensor carries progress breakdown attributes (T119).

    Two of the three tasks carry a null ``progress_status``, which the
    breakdown treats as not yet started rather than dropping.
    """
    await setup_task_entry(hass, respx_router)

    state = _state(hass, PROPERTY_A, "task_count")
    assert state.attributes["pending_count"] == 2
    assert state.attributes["in_progress_count"] == 0
    assert state.attributes["completed_count"] == 1


async def test_the_maintenance_task_is_labelled_from_the_task_type_table(
    hass: Any, respx_router: Any
) -> None:
    """Maintenance survives the vocabulary trap end to end (T114, FR-033).

    ``task_types["5"]`` is Maintenance while ``service_types["5"]`` is
    **Owner**, so a conflated lookup produces a wrong label rather than
    an error. Proving it on a real entity closes the loop the unit test
    opens.
    """
    entry = await setup_task_entry(hass, respx_router)

    coordinator = entry.runtime_data["coordinators"].get("tasks")
    assert coordinator is not None, "no tasks coordinator exists"
    maintenance = next(
        task for task in coordinator.data[PROPERTY_A] if task.task_type == 5
    )
    assert maintenance.task_type_label == "Maintenance"
    assert maintenance.task_type_label != "Owner"
    assert maintenance.service_id == 8
    assert maintenance.service_type_label == "Maintenance"


async def test_no_task_attribute_ever_carries_a_teammate_name(
    hass: Any, respx_router: Any
) -> None:
    """Teammate personal names never reach an attribute (T120, FR-042).

    The teammate IDENTIFIER may be exposed; the NAME may not, and is
    never parsed in the first place. The count assertion comes first so
    this cannot pass merely because no task data arrived.
    """
    await setup_task_entry(hass, respx_router)

    assert _state(hass, PROPERTY_A, "task_count").state == "3", (
        "no task data arrived, so the absence below would prove nothing"
    )
    state = _state(hass, PROPERTY_A, "next_task")
    assert state.attributes["teammate_id"], "the teammate identifier is exposed"
    rendered = repr(dict(state.attributes))
    for name in (TEAMMATE_NAME_A, TEAMMATE_NAME_B):
        assert name not in rendered, "a teammate personal name reached an attribute"
    assert "teammate_name" not in state.attributes


async def test_free_text_never_reaches_a_task_attribute(
    hass: Any, respx_router: Any
) -> None:
    """``note`` and ``reservation.code`` reach no attribute (FR-042).

    Neither is a model field at all, so this asserts the CONSEQUENCE of
    that decision at the surface a user can actually read. The
    reservation code is checked as a SUBSTRING because it genuinely
    belongs to the soonest task; the note is checked across every parsed
    task, since the task carrying it is not the one on display.
    """
    entry = await setup_task_entry(hass, respx_router)

    assert _state(hass, PROPERTY_A, "task_count").state == "3", (
        "no task data arrived, so the absence below would prove nothing"
    )
    state = _state(hass, PROPERTY_A, "next_task")
    assert RESERVATION_CODE in repr(_raw_page_one()), (
        "the fixture must carry the code for this to prove anything"
    )
    assert RESERVATION_CODE not in repr(dict(state.attributes))
    assert "note" not in state.attributes
    assert "reservation_code" not in state.attributes

    coordinator = entry.runtime_data["coordinators"]["tasks"]
    for task in coordinator.data[PROPERTY_A]:
        assert TASK_NOTE not in repr(task)


async def test_task_attributes_are_kept_out_of_the_recorder(
    hass: Any, respx_router: Any
) -> None:
    """Bulk task attributes are excluded from long-term storage.

    Task scheduling detail changes on every poll and has no value as
    recorder history, so it is marked unrecorded rather than written to
    the database forever.
    """
    await setup_task_entry(hass, respx_router)
    assert task_entity_id(hass, PROPERTY_A, "next_task") is not None, (
        "no next_task sensor exists to inspect"
    )

    # Imported by name rather than statically. A static import of a
    # not-yet-existing module needs a ``type: ignore`` whose required
    # error code differs between the whole-tree mypy run and the
    # file-scoped pre-commit run, so neither spelling can satisfy both.
    module = importlib.import_module("custom_components.hospitable.sensor.tasks")

    unrecorded = module.HospitableNextTaskSensor._unrecorded_attributes
    assert "teammate_id" in unrecorded
    assert "reservation_id" in unrecorded
