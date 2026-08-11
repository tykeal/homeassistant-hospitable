# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""End-to-end sensor platform test exercising the real state machine.

Unlike the fast unit tests, this drives a full config-entry setup through
``hass`` with ``respx``-mocked endpoints so nothing here would pass if the
platform forward, the entity's options, the translation key, or the device
link were broken. The platform wiring already exists, so this is a
characterization test, not a red-phase test.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from custom_components.hospitable.entity import build_unique_id
from custom_components.hospitable.sensor.reservation import (
    RESERVATION_STATUS_OPTIONS,
)
from tests.helpers import load_fixture

_ZONE = timezone(timedelta(hours=-7))


def _occupied_reservation(reservation_id: str, property_id: str) -> dict[str, Any]:
    """Build an accepted reservation that is mid-stay right now."""
    today = datetime.now(_ZONE).date()
    arrival = today - timedelta(days=2)
    departure = today + timedelta(days=2)
    payload = dict(load_fixture("reservation_accepted.json")["data"][0])
    payload.update(
        {
            "id": reservation_id,
            "properties": [{"id": property_id}],
            "arrival_date": f"{arrival.isoformat()}T00:00:00-07:00",
            "departure_date": f"{departure.isoformat()}T00:00:00-07:00",
            "check_in": f"{arrival.isoformat()}T16:00:00-07:00",
            "check_out": f"{departure.isoformat()}T11:00:00-07:00",
        }
    )
    return payload


def _reservations_payload() -> dict[str, Any]:
    """Build the reservations envelope with one occupied stay per property."""
    return {
        "data": [
            _occupied_reservation("res-e2e-001", "prop-example-001"),
            _occupied_reservation("res-e2e-002", "prop-example-002"),
        ],
        "meta": {
            "current_page": 1,
            "last_page": 1,
            "path": "http://public.api.hospitable.com/v2/reservations",
            "per_page": 100,
            "total": 2,
        },
    }


async def test_sensor_platform_creates_entity_per_property(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """Setup yields exactly one reservation-status sensor per property."""
    from custom_components.hospitable.api.const import BASE_URL

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: synthetic_token,
            CONF_ACCOUNT_NAMESPACE: "acct-example-0001",
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
        },
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
        return_value=httpx.Response(200, json=_reservations_payload())
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    registry_entries = er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    )
    assert len(registry_entries) == 2

    for property_id, property_name in (
        ("prop-example-001", "Example Beach House"),
        ("prop-example-002", "Example Mountain Cabin"),
    ):
        unique_id = build_unique_id(
            "acct-example-0001", property_id, "reservation_status"
        )
        entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert entity_id is not None
        assert property_name.split()[0].lower() in entity_id
        entity_entry = entity_registry.async_get(entity_id)
        assert entity_entry is not None
        assert entity_entry.translation_key == "reservation_status"
        assert entity_entry.device_id is not None

        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "occupied"
        assert state.attributes["options"] == list(RESERVATION_STATUS_OPTIONS)
        assert "unavailable" not in state.attributes["options"]

        device_entry = device_registry.async_get(entity_entry.device_id)
        assert device_entry is not None
        assert (
            DOMAIN,
            f"acct-example-0001_{property_id}",
        ) in device_entry.identifiers

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
