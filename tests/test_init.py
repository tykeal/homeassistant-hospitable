# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Integration setup behavior tests."""

from __future__ import annotations

from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN, Platform
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from tests.helpers import load_fixture


def test_platforms_contains_sensor() -> None:
    """US2 forwards the sensor platform for reservation entities."""
    import custom_components.hospitable as integration

    assert integration.CONFIG_ENTRY_VERSION == 1
    assert integration.CONFIG_ENTRY_MINOR_VERSION == 1
    assert integration.PLATFORMS == [Platform.SENSOR]


async def test_setup_entry_loads_properties_and_devices(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """Load the integration and assert US2 wires the reservations coordinator."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: synthetic_token,
            CONF_ACCOUNT_NAMESPACE: "acct-example-0001",
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"]},
        unique_id="acct-example-0001",
    )
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(200, json=load_fixture("properties_page1.json")),
            httpx.Response(200, json=load_fixture("properties_page2.json")),
        ]
    )
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-001/calendar").mock(
        return_value=httpx.Response(200, json=load_fixture("calendar_prop1.json"))
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-002/calendar").mock(
        return_value=httpx.Response(200, json=load_fixture("calendar_prop2.json"))
    )
    respx_router.get(f"{BASE_URL}/tasks").mock(
        return_value=httpx.Response(200, json=load_fixture("tasks_empty.json"))
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert set(entry.runtime_data["coordinators"]) == {
        "properties",
        "reservations",
        "calendar",
        "tasks",
    }
    registry = dr.async_get(hass)
    devices = dr.async_entries_for_config_entry(registry, entry.entry_id)
    identifiers = {
        identifier for device in devices for identifier in device.identifiers
    }
    assert identifiers == {
        (DOMAIN, "acct-example-0001_prop-example-001"),
        (DOMAIN, "acct-example-0001_prop-example-002"),
    }

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert getattr(entry, "runtime_data", None) is None


async def test_setup_entry_instantiates_all_coordinators(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """US7 setup instantiates the properties, reservations, and calendar."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: synthetic_token,
            CONF_ACCOUNT_NAMESPACE: "acct-example-0001",
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"]},
        unique_id="acct-example-0001",
    )
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(200, json=load_fixture("properties_page1.json")),
            httpx.Response(200, json=load_fixture("properties_page2.json")),
        ]
    )
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-001/calendar").mock(
        return_value=httpx.Response(200, json=load_fixture("calendar_prop1.json"))
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-002/calendar").mock(
        return_value=httpx.Response(200, json=load_fixture("calendar_prop2.json"))
    )
    respx_router.get(f"{BASE_URL}/tasks").mock(
        return_value=httpx.Response(200, json=load_fixture("tasks_empty.json"))
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert set(entry.runtime_data["coordinators"]) == {
        "properties",
        "reservations",
        "calendar",
        "tasks",
    }

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
