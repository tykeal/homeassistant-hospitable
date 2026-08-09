# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Integration setup behavior tests."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from tests.helpers import load_fixture


def test_setup_wires_only_properties_coordinator() -> None:
    """Assert US1 exposes no platform forwarding target."""
    import custom_components.hospitable as integration

    assert integration.VERSION == 1 and integration.MINOR_VERSION == 1
    assert integration.PLATFORMS == []


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T040 setup loads properties devices only",
)
async def test_setup_entry_loads_properties_and_devices(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """Load the integration and assert US1 creates devices without platforms."""
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

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert set(entry.runtime_data["coordinators"]) == {"properties"}
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
    assert entry.runtime_data is None
