# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""A real config-entry harness carrying task data (US4).

Shared by the task API, coordinator, and sensor tests so all three drive
the SAME wiring: a real ``hass``, a real ``MockConfigEntry``, real
registries, and ``respx``-mocked endpoints. No request is ever made to
the live host.

**Why the recorded fixtures are rewritten here.** ``tasks_page1.json``
and ``tasks_page2.json`` carry the live-confirmed task SHAPE and must
not be edited: nested ``property.id``, a UUID string ``id``, a nullable
``progress_status``, and object-valued ``meta`` vocabularies. Two of
their VALUES are unusable in an end-to-end test, so this harness rewrites
them in memory and leaves the files untouched:

- the synthetic ``property.id`` values do not match the
  ``prop-example-00N`` ids every other fixture in this suite uses, so
  nothing would land on a sensor;
- the ``start_date`` / ``end_date`` values are fixed calendar dates, so a
  "soonest upcoming task" assertion would silently stop meaning anything
  once the wall clock passed them.

Rewriting here keeps the recorded shape authoritative while making the
end-to-end assertions independent of the clock.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from custom_components.hospitable.entity import build_unique_id
from tests.helpers import load_fixture

ACCOUNT = "acct-example-0001"
PROPERTY_A = "prop-example-001"
PROPERTY_B = "prop-example-002"

# The teammate personal name carried by the recorded fixtures. It is PII
# and MUST NOT reach the model, an attribute, or a diagnostic.
TEAMMATE_NAME_A = "Synthetic Teammate One"
TEAMMATE_NAME_B = "Synthetic Teammate Two"

# Free-text values the PM decision drops from the model entirely.
TASK_NOTE = "Synthetic note: check placeholder equipment only."
RESERVATION_CODE = "SYN-RES-001"


def _shift_dates(task: dict[str, Any], offset_days: int) -> None:
    """Move one task's window to a fixed offset from today.

    The recorded fixture carries absolute calendar dates. Rebasing them
    on the current date keeps "soonest upcoming task" meaningful forever
    rather than only until those dates pass.

    Args:
        task: Task object to rewrite in place.
        offset_days: Days from today the task should start.
    """
    for key in ("start_date", "end_date"):
        original = datetime.fromisoformat(str(task[key]))
        today = datetime.now(original.tzinfo).date()
        moved = today + timedelta(days=offset_days)
        task[key] = original.replace(
            year=moved.year, month=moved.month, day=moved.day
        ).isoformat()


def tasks_page(fixture: str, property_id: str, *, first_offset: int = 1) -> Any:
    """Return a task page rebased onto a property and the current date.

    Args:
        fixture: Recorded fixture filename to rewrite.
        property_id: Property id every task in the page should carry.
        first_offset: Days from today the first task should start;
            each later task in the page starts one day after it.

    Returns:
        The rewritten envelope, leaving the fixture file untouched.
    """
    payload = copy.deepcopy(load_fixture(fixture))
    for index, task in enumerate(payload["data"]):
        task["property"]["id"] = property_id
        task["property"]["name"] = property_id
        _shift_dates(task, first_offset + index)
    return payload


def as_single_page(payload: Any) -> Any:
    """Mark a page envelope as the only page of its response.

    ``tasks_page2.json`` records ``current_page: 2`` because that is
    what upstream returned for it. A test that serves it as the ONLY
    page must say so in the envelope too, or the shared page-envelope
    validator rightly rejects a response whose page number disagrees
    with the request.

    Args:
        payload: A task page envelope to rewrite in place.

    Returns:
        The same envelope, marked as page one of one.
    """
    payload["meta"]["last_page"] = 1
    payload["meta"]["current_page"] = 1
    return payload


def empty_tasks_page() -> dict[str, Any]:
    """Return a well-formed task envelope carrying no tasks.

    Returns:
        A single-page envelope with an empty ``data`` array and the
        recorded ``meta`` vocabularies preserved.
    """
    payload: dict[str, Any] = copy.deepcopy(load_fixture("tasks_page1.json"))
    payload["data"] = []
    payload["meta"]["total"] = 0
    single: dict[str, Any] = as_single_page(payload)
    return single


def _properties_side_effect(request: httpx.Request) -> httpx.Response:
    """Return the paginated properties fixture for the requested page.

    Args:
        request: The captured properties request.

    Returns:
        The fixture response for the requested page.
    """
    page = request.url.params.get("page", "1")
    fixture = "properties_page2.json" if page == "2" else "properties_page1.json"
    return httpx.Response(200, json=load_fixture(fixture))


def mock_base_endpoints(respx_router: Any) -> None:
    """Mock every non-task GET endpoint the entry setup needs.

    Args:
        respx_router: The active respx router.
    """
    respx_router.get(f"{BASE_URL}/properties").mock(side_effect=_properties_side_effect)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )
    for property_id, fixture in (
        (PROPERTY_A, "calendar_prop1.json"),
        (PROPERTY_B, "calendar_prop2.json"),
    ):
        respx_router.get(f"{BASE_URL}/properties/{property_id}/calendar").mock(
            return_value=httpx.Response(200, json=load_fixture(fixture))
        )


def mock_tasks(
    respx_router: Any,
    *,
    responses: dict[str, list[httpx.Response]] | None = None,
) -> Any:
    """Mock ``/tasks`` with a per-property, per-page response script.

    Args:
        respx_router: The active respx router.
        responses: Per-property list of responses, consumed in page
            order. A property with no script gets an empty page. The
            default script gives property A both recorded pages and
            property B a single empty page, so a per-property page count
            is genuinely exercised.

    Returns:
        The registered ``/tasks`` route.
    """
    script = responses
    if script is None:
        script = {
            PROPERTY_A: [
                httpx.Response(200, json=tasks_page("tasks_page1.json", PROPERTY_A)),
                httpx.Response(
                    200,
                    json=tasks_page("tasks_page2.json", PROPERTY_A, first_offset=3),
                ),
            ],
            PROPERTY_B: [httpx.Response(200, json=empty_tasks_page())],
        }
    served: dict[str, int] = {}

    def _side_effect(request: httpx.Request) -> httpx.Response:
        """Return the scripted response for this property and page.

        Args:
            request: The captured tasks request.

        Returns:
            The scripted response.
        """
        property_id = request.url.params.get("properties[]", "")
        index = served.get(property_id, 0)
        served[property_id] = index + 1
        pages = script.get(property_id, [])
        if index < len(pages):
            return pages[index]
        return httpx.Response(200, json=empty_tasks_page())

    return respx_router.get(f"{BASE_URL}/tasks").mock(side_effect=_side_effect)


def build_entry(**options: Any) -> MockConfigEntry:
    """Build an unloaded config entry selecting both example properties.

    Args:
        **options: Extra config-entry options to merge in.

    Returns:
        The config entry, not yet added to ``hass``.
    """
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: [PROPERTY_A, PROPERTY_B],
            **options,
        },
        unique_id=ACCOUNT,
    )


async def setup_task_entry(
    hass: Any, respx_router: Any, **options: Any
) -> MockConfigEntry:
    """Set up a loaded config entry with the default task script.

    Args:
        hass: The Home Assistant test instance.
        respx_router: The active respx router.
        **options: Extra config-entry options to merge in.

    Returns:
        The loaded config entry.
    """
    mock_base_endpoints(respx_router)
    mock_tasks(respx_router)
    entry = build_entry(**options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


def task_entity_id(hass: Any, property_id: str, key: str) -> str | None:
    """Return a task sensor entity id for a property, if registered.

    Args:
        hass: The Home Assistant test instance.
        property_id: Property whose sensor is wanted.
        key: Entity key, ``next_task`` or ``task_count``.

    Returns:
        The registered entity id, or ``None`` when absent.
    """
    registry = er.async_get(hass)
    unique_id = build_unique_id(ACCOUNT, property_id, key)
    return registry.async_get_entity_id("sensor", DOMAIN, unique_id)
