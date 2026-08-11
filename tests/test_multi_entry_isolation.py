# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""One entry's failures must not disturb another entry (FR-012).

This is the isolation evidence for SC-010's "poll independently" clause.
Two accounts are set up and then account A is subjected to an
authentication failure (401), a rate-limit response (429) and a raw
connection failure in sequence. Throughout, account B's coordinators and
entities must stay exactly as they were, and the converse must hold too.

A shared coordinator instance, a shared client wrapper, a module-level
cache, or a shared failure counter would all break these assertions,
which is precisely why they are asserted directly rather than assumed
from the constructor arguments. This asserts no new production behavior;
per Principle XII Exemptions it carries no red-phase commit.
"""

from __future__ import annotations

from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from tests.helpers import load_fixture, paginator_envelope

_PROPERTY_ID = "prop-example-001"


def _properties_envelope() -> dict[str, Any]:
    """Return a single-page envelope with one property."""
    return paginator_envelope([load_fixture("properties_page1.json")["data"][0]])


def _install_api(respx_router: Any, base_url: str, state: dict[str, str]) -> None:
    """Serve good data or the failure selected by ``state['mode']``."""

    def _properties(request: httpx.Request) -> httpx.Response:
        """Return properties, or the failure currently armed in state."""
        mode = state["mode"]
        if mode == "auth":
            return httpx.Response(401, json=load_fixture("error_401.json"))
        if mode == "rate":
            return httpx.Response(429, json=load_fixture("error_429.json"))
        if mode == "poll":
            return httpx.Response(500, json=load_fixture("error_500.json"))
        return httpx.Response(200, json=_properties_envelope())

    def _reservations(request: httpx.Request) -> httpx.Response:
        """Return reservations, or the failure currently armed in state."""
        mode = state["mode"]
        if mode == "auth":
            return httpx.Response(401, json=load_fixture("error_401.json"))
        if mode == "rate":
            return httpx.Response(429, json=load_fixture("error_429.json"))
        if mode == "poll":
            return httpx.Response(500, json=load_fixture("error_500.json"))
        return httpx.Response(
            200,
            json=paginator_envelope(
                [], path="http://public.api.hospitable.com/v2/reservations"
            ),
        )

    respx_router.get(f"{base_url}/properties").mock(side_effect=_properties)
    respx_router.get(f"{base_url}/reservations").mock(side_effect=_reservations)


async def _setup_entry(hass: Any, *, namespace: str, token: str) -> MockConfigEntry:
    """Set up one healthy account entry and assert it loaded."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: token,
            CONF_ACCOUNT_NAMESPACE: namespace,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={CONF_SELECTED_PROPERTIES: [_PROPERTY_ID]},
        unique_id=namespace,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


def _entity_ids(hass: Any, entry: MockConfigEntry) -> list[str]:
    """Return every registry entity id owned by an entry."""
    registry = er.async_get(hass)
    return [
        item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    ]


def _states(hass: Any, entity_ids: list[str]) -> dict[str, str]:
    """Return the current state string for each entity id."""
    snapshot: dict[str, str] = {}
    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        assert state is not None
        snapshot[entity_id] = state.state
    return snapshot


async def test_one_entry_failures_do_not_disturb_another(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """A's auth, rate-limit and poll failures leave B untouched."""
    from custom_components.hospitable.api.const import BASE_URL

    state = {"mode": "ok"}
    _install_api(respx_router, BASE_URL, state)

    entry_a = await _setup_entry(
        hass, namespace="acct-iso-a", token=f"{synthetic_token}-a"
    )
    entry_b = await _setup_entry(
        hass, namespace="acct-iso-b", token=f"{synthetic_token}-b"
    )

    coords_a = entry_a.runtime_data["coordinators"]
    coords_b = entry_b.runtime_data["coordinators"]
    props_a = coords_a["properties"]
    props_b = coords_b["properties"]
    res_a = coords_a["reservations"]
    res_b = coords_b["reservations"]

    # No coordinator or client is shared between the two entries.
    assert props_a is not props_b
    assert res_a is not res_b
    assert entry_a.runtime_data["client"] is not entry_b.runtime_data["client"]

    b_entity_ids = _entity_ids(hass, entry_b)
    assert b_entity_ids
    b_states_before = _states(hass, b_entity_ids)
    b_data_before = props_b.data
    assert b_data_before is not None
    b_reservations_before = res_b.data

    # No B entity is unavailable before A starts failing.
    assert all(value != "unavailable" for value in b_states_before.values())

    # Drive A through 401, then 429, then a server-side poll failure (500) on
    # BOTH of A's coordinators. After each, B must be completely undisturbed.
    # A raw transport-level error (httpx.ConnectError) is deliberately NOT
    # used here: the client does not wrap transport exceptions into
    # HospitableError, which is US6's error-handling scope, not this
    # isolation test's.
    for mode in ("auth", "rate", "poll"):
        state["mode"] = mode
        await props_a.async_refresh()
        await res_a.async_refresh()
        await hass.async_block_till_done()

        assert props_a.last_update_success is False
        assert res_a.last_update_success is False
        assert props_b.consecutive_failures == 0
        assert res_b.consecutive_failures == 0
        assert props_b.last_update_success is True
        assert res_b.last_update_success is True
        assert props_b.data is b_data_before
        assert res_b.data is b_reservations_before
        assert _states(hass, b_entity_ids) == b_states_before

    # A has now failed three consecutive times on both coordinators. Force the
    # listener notification that A's own scheduled poll cycle would deliver to
    # its entities (a direct ``async_refresh`` does not re-render listeners on
    # failure) and confirm every A entity is unavailable, while every B entity
    # -- never re-polled -- keeps its prior available state.
    assert props_a.consecutive_failures == 3
    assert res_a.consecutive_failures == 3
    props_a.async_update_listeners()
    res_a.async_update_listeners()
    await hass.async_block_till_done()
    a_entity_ids = _entity_ids(hass, entry_a)
    assert all(
        hass.states.get(entity_id).state == "unavailable" for entity_id in a_entity_ids
    )
    assert all(
        hass.states.get(entity_id).state != "unavailable" for entity_id in b_entity_ids
    )

    # Converse direction: failing B must not reach into A's state. A keeps its
    # three failures and its last-known data; B's failure counter is its own.
    a_data_before = props_a.data
    assert a_data_before is not None
    state["mode"] = "auth"
    await props_b.async_refresh()
    await hass.async_block_till_done()

    assert props_b.consecutive_failures == 1
    assert props_a.consecutive_failures == 3
    assert props_a.data is a_data_before

    for entry in (entry_a, entry_b):
        assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
