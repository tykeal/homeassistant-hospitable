# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T107 (FR-018, FR-055): non-destructive deselection and reselection.

End-to-end proof that deselecting a property through the options flow
stops polling it and marks its entities unavailable while RETAINING its
registry entries and recorded history, and that reselecting it resumes
polling against the SAME unique identifiers so history is continuous in
both directions. Deselection reuses the FR-056 disappearance mechanism.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_LOOKAHEAD_DAYS,
    CONF_LOOKBACK_DAYS,
    CONF_NAMESPACE_SOURCE,
    CONF_PROPERTY_INTERVAL,
    CONF_RESERVATION_INTERVAL,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from custom_components.hospitable.entity import build_unique_id
from tests.helpers import load_fixture

_ACCOUNT = "acct-example-0001"
_PROP_A = "prop-example-001"
_PROP_B = "prop-example-002"


def _properties_side_effect(request: httpx.Request) -> httpx.Response:
    """Return the paginated properties fixture for the requested page."""
    page = request.url.params.get("page", "1")
    fixture = "properties_page2.json" if page == "2" else "properties_page1.json"
    return httpx.Response(200, json=load_fixture(fixture))


def _entry() -> MockConfigEntry:
    """Build a config entry selecting both example properties."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: _ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: [_PROP_A, _PROP_B],
            CONF_RESERVATION_INTERVAL: 5,
            CONF_PROPERTY_INTERVAL: 60,
            CONF_LOOKBACK_DAYS: 90,
            CONF_LOOKAHEAD_DAYS: 90,
        },
        unique_id=_ACCOUNT,
    )


def _selection_input(selection: list[str]) -> dict[str, Any]:
    """Return an options-flow input applying the given property selection."""
    return {
        CONF_SELECTED_PROPERTIES: selection,
        CONF_RESERVATION_INTERVAL: 5,
        CONF_PROPERTY_INTERVAL: 60,
        CONF_LOOKBACK_DAYS: 90,
        CONF_LOOKAHEAD_DAYS: 90,
    }


async def _apply_selection(
    hass: Any, entry: MockConfigEntry, selection: list[str]
) -> None:
    """Drive the options flow to apply a property selection and reload."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], _selection_input(selection)
    )
    await hass.async_block_till_done()


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T113 non-destructive deselection not implemented",
)
async def test_deselection_and_reselection_preserve_identity(
    hass: Any, respx_router: Any
) -> None:
    """Deselect then reselect a property; identity and history survive both."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = _entry()
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(side_effect=_properties_side_effect)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    entity_registry = er.async_get(hass)
    b_res_uid = build_unique_id(_ACCOUNT, _PROP_B, "reservation_status")
    b_info_uid = build_unique_id(_ACCOUNT, _PROP_B, "property_info")
    a_res_uid = build_unique_id(_ACCOUNT, _PROP_A, "reservation_status")

    b_res_id = entity_registry.async_get_entity_id("sensor", DOMAIN, b_res_uid)
    b_info_id = entity_registry.async_get_entity_id("sensor", DOMAIN, b_info_uid)
    a_res_id = entity_registry.async_get_entity_id("sensor", DOMAIN, a_res_uid)
    assert b_res_id is not None
    assert b_info_id is not None
    assert a_res_id is not None

    # Both properties are available at the start.
    assert hass.states.get(b_res_id).state != "unavailable"
    assert hass.states.get(a_res_id).state != "unavailable"

    # --- Deselect property B ---
    await _apply_selection(hass, entry, [_PROP_A])

    # B's entities are unavailable but retained; A is unaffected.
    b_res_state = hass.states.get(b_res_id)
    b_info_state = hass.states.get(b_info_id)
    assert b_res_state is not None and b_res_state.state == "unavailable"
    assert b_info_state is not None and b_info_state.state == "unavailable"
    assert hass.states.get(a_res_id).state != "unavailable"

    # Registry entries survive with the SAME unique identifiers.
    b_res_entry = entity_registry.async_get(b_res_id)
    assert b_res_entry is not None
    assert b_res_entry.unique_id == b_res_uid
    assert entity_registry.async_get(b_info_id) is not None
    # Reservations coordinator has stopped polling B.
    reservations = entry.runtime_data["coordinators"]["reservations"]
    assert _PROP_B not in getattr(reservations, "_property_ids", [])

    # --- Reselect property B ---
    await _apply_selection(hass, entry, [_PROP_A, _PROP_B])

    # B resumes against the SAME identifiers, so history is continuous.
    assert entity_registry.async_get_entity_id("sensor", DOMAIN, b_res_uid) == b_res_id
    b_res_state = hass.states.get(b_res_id)
    assert b_res_state is not None and b_res_state.state != "unavailable"
    reservations = entry.runtime_data["coordinators"]["reservations"]
    assert _PROP_B in getattr(reservations, "_property_ids", [])

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
