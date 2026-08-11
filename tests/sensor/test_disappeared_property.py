# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Test for the disappeared-property lifecycle path.

Covers T093 (FR-056): when a monitored property disappears from the
account its entities become unavailable, its registry entries and
history are RETAINED, and exactly one explanatory warning is logged.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
import pytest
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


def _property_payload(property_id: str, name: str) -> dict[str, Any]:
    """Return a single-property payload with the given id and name."""
    payload = dict(load_fixture("properties_page1.json")["data"][0])
    payload["id"] = property_id
    payload["name"] = name
    return payload


def _envelope(*payloads: dict[str, Any]) -> dict[str, Any]:
    """Return a one-page properties envelope for the given payloads."""
    return paginator_envelope(list(payloads))


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


async def test_disappeared_property_unavailable_retained_warned_once(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A vanished property goes unavailable, is retained, and warns once."""
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
    both = _envelope(
        _property_payload("prop-example-001", "Example Beach House"),
        _property_payload("prop-example-002", "Example Mountain Cabin"),
    )
    only_first = _envelope(
        _property_payload("prop-example-001", "Example Beach House"),
    )
    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(200, json=both),
            httpx.Response(200, json=only_first),
        ]
    )
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=_empty_reservations())
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    entity_registry = er.async_get(hass)
    gone_uid = build_unique_id("acct-example-0001", "prop-example-002", "property_info")
    gone_id = entity_registry.async_get_entity_id("sensor", DOMAIN, gone_uid)
    assert gone_id is not None
    reservation_uid = build_unique_id(
        "acct-example-0001", "prop-example-002", "reservation_status"
    )
    reservation_id = entity_registry.async_get_entity_id(
        "sensor", DOMAIN, reservation_uid
    )
    assert reservation_id is not None

    runtime = entry.runtime_data
    properties_coordinator = runtime["coordinators"]["properties"]

    with caplog.at_level(logging.WARNING):
        await properties_coordinator.async_refresh()
        await hass.async_block_till_done()

    gone_state = hass.states.get(gone_id)
    assert gone_state is not None
    assert gone_state.state == "unavailable"

    reservation_state = hass.states.get(reservation_id)
    assert reservation_state is not None
    assert reservation_state.state == "unavailable"

    # Registry entries (and therefore recorder history) are retained.
    assert entity_registry.async_get(gone_id) is not None
    assert entity_registry.async_get(reservation_id) is not None

    warnings = [
        record
        for record in caplog.records
        if record.levelno == logging.WARNING
        and "prop-example-002" in record.getMessage()
    ]
    assert len(warnings) == 1

    # The surviving property's entities remain available.
    present_uid = build_unique_id(
        "acct-example-0001", "prop-example-001", "property_info"
    )
    present_id = entity_registry.async_get_entity_id("sensor", DOMAIN, present_uid)
    assert present_id is not None
    present_state = hass.states.get(present_id)
    assert present_state is not None
    assert present_state.state != "unavailable"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
