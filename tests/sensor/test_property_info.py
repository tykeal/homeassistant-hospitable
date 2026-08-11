# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the property-information diagnostic sensor.

Covers T091 (FR-053, FR-062): the ``property_info`` sensor's state is the
display name and it exposes exactly the eight contract attributes with no
coordinates, street number, postcode, or owner contact details.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN, EntityCategory
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.api.models import HospitableProperty
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from custom_components.hospitable.entity import build_unique_id
from custom_components.hospitable.sensor.property import HospitablePropertyInfoSensor
from tests.helpers import load_fixture

EXPECTED_ATTRIBUTES = {
    "address",
    "checkin_time",
    "checkout_time",
    "max_guests",
    "effective_timezone",
    "timezone_source",
    "listings",
    "listings_available",
}

# The address attribute is the upstream-composed ``address.display``
# string, which the contract explicitly permits. The guard therefore
# targets the structured leak vectors that must never appear: raw
# coordinates and any owner contact detail.
FORBIDDEN_VALUES = {
    "37.1001",
    "-122.1001",
    "host@example.com",
    "Example Host",
}


def _property(fixture: str = "properties_page1.json") -> HospitableProperty:
    """Build a property model from a fixture's first item."""
    return HospitableProperty.from_api(load_fixture(fixture)["data"][0])


def _info_sensor(
    property_model: HospitableProperty,
    *,
    effective_timezone: str = "America/Los_Angeles",
    timezone_source: str = "instance",
) -> Any:
    """Build a property_info sensor on a fake properties coordinator."""
    properties_coordinator = SimpleNamespace(
        data={property_model.property_id: property_model},
        consecutive_failures=0,
        monitored_property_ids={property_model.property_id},
    )
    return HospitablePropertyInfoSensor(
        cast(Any, properties_coordinator),
        account_namespace="acct",
        property_id=property_model.property_id,
        property_name=property_model.name,
        effective_timezone=effective_timezone,
        timezone_source=timezone_source,
    )


def test_state_is_display_name() -> None:
    """The sensor state is the property's display name."""
    sensor = _info_sensor(_property())
    assert sensor.native_value == "Example Beach House"


def test_entity_category_is_diagnostic() -> None:
    """The sensor is a diagnostic entity."""
    sensor = _info_sensor(_property())
    assert sensor.entity_category is EntityCategory.DIAGNOSTIC


def test_attribute_keys_match_contract_exactly() -> None:
    """The attribute keys match the entities.md contract exactly."""
    sensor = _info_sensor(_property())
    assert set(sensor.extra_state_attributes) == EXPECTED_ATTRIBUTES


def test_attribute_values_and_types() -> None:
    """Attribute values follow the contract types and the address is display."""
    sensor = _info_sensor(
        _property(), effective_timezone="America/New_York", timezone_source="override"
    )
    attributes = sensor.extra_state_attributes
    assert attributes["address"] == "100 Example Avenue, Example City, CA 90210, US"
    assert attributes["checkin_time"] == "16:00"
    assert attributes["checkout_time"] == "11:00"
    assert attributes["max_guests"] == 6
    assert attributes["effective_timezone"] == "America/New_York"
    assert attributes["timezone_source"] == "override"
    assert attributes["listings_available"] is True
    assert attributes["listings"] == [
        {"platform": "airbnb", "platform_id": "AIR-EXAMPLE-1"}
    ]


def test_no_coordinates_or_contact_details_leak() -> None:
    """No coordinates, street number, postcode, or owner contact appear."""
    sensor = _info_sensor(_property())
    rendered = repr(sensor.extra_state_attributes)
    for forbidden in FORBIDDEN_VALUES:
        assert forbidden not in rendered


def _reservations_payload() -> dict[str, Any]:
    """Envelope with no reservations, sufficient for property_info setup."""
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


async def test_property_info_end_to_end(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """A full setup creates a property_info sensor exposing eight attributes."""
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
    info_uid = build_unique_id("acct-example-0001", "prop-example-001", "property_info")
    info_id = entity_registry.async_get_entity_id("sensor", DOMAIN, info_uid)
    assert info_id is not None
    state = hass.states.get(info_id)
    assert state is not None
    assert state.state == "Example Beach House"
    attribute_keys = set(state.attributes) - {"friendly_name"}
    assert attribute_keys == EXPECTED_ATTRIBUTES

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
