# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Task polling is an opt-in (spec 002 FR-030 amendment, 2026-11-09).

Most installs use this integration to message guests, not to track
cleaning tasks, yet the task poll costs one request per selected
property per cycle: 960 requests a day at ten properties on the default
cadence, which alone pushed the default budget past spec 001 SC-004.
These tests pin the opt-in end to end through a real ``hass``, real
registries, and ``respx``-mocked endpoints:

- a new entry starts with task polling OFF, makes no ``/tasks``
  request, and registers no task entity;
- an entry created before the option existed is migrated to ON, so an
  upgrade keeps its task sensors unchanged;
- turning the option off removes the task entities and stops the poll,
  and turning it back on restores both;
- the request estimate no longer counts tasks unless they are polled.
"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import InvalidData
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    CONF_TOKEN,
    DOMAIN,
)
from tests.helpers import load_fixture
from tests.helpers.task_entry import (
    ACCOUNT,
    PROPERTY_A,
    PROPERTY_B,
    mock_base_endpoints,
    mock_tasks,
    task_entity_id,
)

# Literals rather than imported constants: a module-level import of a
# not-yet-existing constant would break collection, which no xfail
# marker can rescue.
POLL_TASKS = "poll_tasks"
CURRENT_MINOR_VERSION = 2
TASK_KEYS = ("next_task", "task_count")
STRINGS = Path("custom_components/hospitable/strings.json")
EN = Path("custom_components/hospitable/translations/en.json")


def _entry(*, minor_version: int, **options: Any) -> MockConfigEntry:
    """Build an unloaded entry selecting both example properties.

    Args:
        minor_version: The config-entry minor version to store.
        **options: Extra options to merge in.

    Returns:
        The config entry, not yet added to ``hass``.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=minor_version,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={CONF_SELECTED_PROPERTIES: [PROPERTY_A, PROPERTY_B], **options},
        unique_id=ACCOUNT,
    )


async def _setup(hass: Any, entry: MockConfigEntry) -> None:
    """Add and load an entry, asserting it reached LOADED.

    Args:
        hass: The Home Assistant test instance.
        entry: The entry to load.
    """
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


def _task_entities(hass: Any) -> set[str | None]:
    """Return every task entity id registered for both properties.

    Args:
        hass: The Home Assistant test instance.

    Returns:
        The registered entity ids; ``None`` marks an absent entity.
    """
    return {
        task_entity_id(hass, property_id, key)
        for property_id in (PROPERTY_A, PROPERTY_B)
        for key in TASK_KEYS
    }


async def _set_poll_tasks(hass: Any, entry: MockConfigEntry, enabled: bool) -> None:
    """Toggle task polling through the real options flow.

    A schema that does not know the field rejects the submission, so
    that rejection is turned into an assertion about the missing option
    rather than surfacing as a schema error.

    Args:
        hass: The Home Assistant test instance.
        entry: The loaded entry to reconfigure.
        enabled: The new task-polling setting.
    """
    result = await hass.config_entries.options.async_init(entry.entry_id)
    submitted: dict[str, Any] | None = None
    try:
        submitted = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_SELECTED_PROPERTIES: [PROPERTY_A, PROPERTY_B], POLL_TASKS: enabled},
        )
    except InvalidData:
        submitted = None
    assert submitted is not None, "the options schema rejects the task-polling field"
    assert submitted["type"] == "create_entry"
    await hass.async_block_till_done()
    assert entry.options[POLL_TASKS] is enabled
    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: spec 002 FR-030 amendment, task polling not opt-in",
)
async def test_a_new_entry_does_not_poll_tasks(hass: Any, respx_router: Any) -> None:
    """An entry created by the config flow polls no tasks and has no sensors."""
    respx_router.get(f"{BASE_URL}/user").respond(json=load_fixture("user.json"))
    mock_base_endpoints(respx_router)
    tasks_route = mock_tasks(respx_router)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
        data={CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000"},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SELECTED_PROPERTIES: [PROPERTY_A, PROPERTY_B]}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    entry = result["result"]
    assert entry.state is ConfigEntryState.LOADED

    assert entry.options.get(POLL_TASKS) is False
    assert not tasks_route.called
    assert _task_entities(hass) == {None}
    assert "tasks" not in entry.runtime_data["coordinators"]

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=2))
    await hass.async_block_till_done()
    assert not tasks_route.called


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: spec 002 FR-030 amendment, no task-polling migration",
)
async def test_an_existing_entry_is_migrated_to_keep_polling_tasks(
    hass: Any, respx_router: Any
) -> None:
    """An entry from before the option keeps its task sensors on upgrade."""
    mock_base_endpoints(respx_router)
    tasks_route = mock_tasks(respx_router)
    entry = _entry(minor_version=1)

    await _setup(hass, entry)

    assert entry.minor_version == CURRENT_MINOR_VERSION
    assert entry.options.get(POLL_TASKS) is True
    assert tasks_route.called
    assert None not in _task_entities(hass)


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: spec 002 FR-030 amendment, task polling not opt-in",
)
async def test_turning_task_polling_off_removes_sensors_and_requests(
    hass: Any, respx_router: Any
) -> None:
    """Disabling the option drops every task entity and every task request."""
    mock_base_endpoints(respx_router)
    tasks_route = mock_tasks(respx_router)
    entry = _entry(minor_version=CURRENT_MINOR_VERSION, **{POLL_TASKS: True})
    await _setup(hass, entry)
    assert None not in _task_entities(hass)

    await _set_poll_tasks(hass, entry, False)

    assert _task_entities(hass) == {None}
    assert "tasks" not in entry.runtime_data["coordinators"]
    calls = tasks_route.call_count
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(hours=2))
    await hass.async_block_till_done()
    assert tasks_route.call_count == calls


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: spec 002 FR-030 amendment, task polling not opt-in",
)
async def test_turning_task_polling_on_restores_sensors(
    hass: Any, respx_router: Any
) -> None:
    """Enabling the option brings the task entities and the poll back."""
    mock_base_endpoints(respx_router)
    tasks_route = mock_tasks(respx_router)
    entry = _entry(minor_version=CURRENT_MINOR_VERSION, **{POLL_TASKS: False})
    await _setup(hass, entry)
    assert _task_entities(hass) == {None}
    assert not tasks_route.called

    await _set_poll_tasks(hass, entry, True)

    assert tasks_route.called
    assert None not in _task_entities(hass)


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: spec 002 FR-030 amendment, no task-polling option",
)
async def test_the_options_form_offers_task_polling_off_by_default(
    hass: Any,
) -> None:
    """The form offers the toggle, OFF, and its estimate omits tasks.

    The entry is never loaded, so the estimate sees no reservations:
    24 property polls, 48 calendar polls, and 288 reservation polls for
    two properties at the default cadences. Any task request would push
    it above 360.
    """
    entry = _entry(minor_version=CURRENT_MINOR_VERSION, **{POLL_TASKS: False})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults.get(POLL_TASKS) is False
    assert int(result["description_placeholders"]["estimate"]) == 360
    for path in (STRINGS, EN):
        step = json.loads(path.read_text())["options"]["step"]["init"]
        assert POLL_TASKS in step["data"]
        assert "request" in step["data_description"].get(POLL_TASKS, "")


@pytest.mark.xfail(
    raises=TypeError,
    strict=True,
    reason="TDD red phase: spec 002 FR-030 amendment, estimate counts tasks",
)
def test_the_default_estimate_meets_sc_004_again() -> None:
    """Ten properties at defaults, without tasks, stay under 2,000 a day."""
    from custom_components.hospitable.services.estimator import (
        estimate_requests_per_day,
    )

    # Typed Any so the red phase type-checks against the old signature.
    tasks_off: Any = None
    estimate = estimate_requests_per_day(10, 60, 5, 500, tasks_off)

    assert estimate == 1704
    assert estimate < 2000
