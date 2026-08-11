# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Test for rename stability of property entities.

Covers T092 (FR-054, FR-055): renaming a property upstream changes the
display name but leaves the unique ID, entity registry entry, and its
recorded history intact.
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
from custom_components.hospitable.entity import build_unique_id
from tests.helpers import load_fixture, paginator_envelope


def _property_payload(name: str) -> dict[str, Any]:
    """Return a single-property payload with a given display name."""
    payload = dict(load_fixture("properties_page1.json")["data"][0])
    payload["name"] = name
    return payload


def _properties_envelope(name: str) -> dict[str, Any]:
    """Return a one-page properties envelope naming prop-example-001."""
    return paginator_envelope([_property_payload(name)])


def _empty_reservations() -> dict[str, Any]:
    """Return an empty reservations envelope."""
    return {
        "data": [],
        "meta": {
            "current_page": 1,
            "last_page": 1,
            "path": "http://public.api.hospitable.com/v2/reservations",
            "per_page": 100,
            "total": 0,
        },
    }


async def test_rename_preserves_identifiers(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """A rename updates the display name but not the unique ID or registry."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: synthetic_token,
            CONF_ACCOUNT_NAMESPACE: "acct-example-0001",
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={CONF_SELECTED_PROPERTIES: ["prop-example-001"]},
        unique_id="acct-example-0001",
    )
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(200, json=_properties_envelope("Example Beach House")),
            httpx.Response(200, json=_properties_envelope("Renamed Villa")),
        ]
    )
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=_empty_reservations())
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    entity_registry = er.async_get(hass)
    info_uid = build_unique_id("acct-example-0001", "prop-example-001", "property_info")
    info_id = entity_registry.async_get_entity_id("sensor", DOMAIN, info_uid)
    assert info_id is not None
    before_entry = entity_registry.async_get(info_id)
    assert before_entry is not None
    state_before = hass.states.get(info_id)
    assert state_before is not None
    assert state_before.state == "Example Beach House"

    runtime = entry.runtime_data
    properties_coordinator = runtime["coordinators"]["properties"]
    await properties_coordinator.async_refresh()
    await hass.async_block_till_done()

    after_id = entity_registry.async_get_entity_id("sensor", DOMAIN, info_uid)
    assert after_id == info_id
    after_entry = entity_registry.async_get(info_id)
    assert after_entry is not None
    assert after_entry.unique_id == before_entry.unique_id
    state_after = hass.states.get(info_id)
    assert state_after is not None
    assert state_after.state == "Renamed Villa"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
