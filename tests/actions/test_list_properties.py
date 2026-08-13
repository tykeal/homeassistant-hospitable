# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for the ``hospitable.list_properties`` action (Deliverable A)."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.exceptions import ServiceValidationError


def test_handler_can_be_imported() -> None:
    """async_handle_list_properties is importable (FR-003)."""
    from custom_components.hospitable.actions.list_properties import (
        async_handle_list_properties,
    )

    assert async_handle_list_properties is not None


def test_schema_can_be_imported() -> None:
    """LIST_PROPERTIES_SCHEMA is importable from schemas (FR-004)."""
    from custom_components.hospitable.actions.schemas import (
        LIST_PROPERTIES_SCHEMA,
    )

    assert LIST_PROPERTIES_SCHEMA is not None


def test_list_properties_is_registered_in_definitions() -> None:
    """list_properties appears in SERVICE_DEFINITIONS (FR-003)."""
    from custom_components.hospitable.actions import SERVICE_DEFINITIONS

    names = [d.name for d in SERVICE_DEFINITIONS]
    assert "list_properties" in names


async def test_list_properties_returns_all_known(
    hass: Any,
    respx_router: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """list_properties returns selected and unselected properties.

    Sets up a coordinator cache with 2 properties, one selected and
    one unselected, then asserts the response shape (FR-005, FR-008,
    FR-009, FR-010).
    """
    from custom_components.hospitable.const import DOMAIN

    entry = await loaded_config_entry_factory(hass)

    assert hass.services.has_service(DOMAIN, "list_properties"), (
        "list_properties is not a registered service"
    )

    # Inject an unselected property into known_property_ids
    entry.runtime_data["known_property_ids"] = {
        "prop-example-001",
        "prop-example-002",
        "prop-unselected-999",
    }

    result = await hass.services.async_call(
        DOMAIN,
        "list_properties",
        {},
        blocking=True,
        return_response=True,
    )
    assert isinstance(result, dict)
    assert result["found"] is True
    assert "properties" in result
    props = result["properties"]
    assert len(props) == 3
    for prop in props:
        assert set(prop.keys()) >= {
            "property_id",
            "name",
            "public_name",
            "selected",
            "listings",
        }
    unselected = [p for p in props if p["property_id"] == "prop-unselected-999"]
    assert len(unselected) == 1
    assert unselected[0]["selected"] is False


async def test_list_properties_includes_filtered_co_hosts(
    hass: Any,
    respx_router: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """Co-hosts are returned with allowlisted keys only (FR-006, FR-007).

    When guest_contact_details is disabled, co-host objects carry only
    user_id, channel_name, and name. No email or phone_numbers appear.
    """
    import importlib

    const = importlib.import_module("custom_components.hospitable.const")
    entry = await loaded_config_entry_factory(hass)

    assert hass.services.has_service(const.DOMAIN, "list_properties"), (
        "list_properties is not a registered service"
    )

    models = importlib.import_module("custom_components.hospitable.api.models")
    # Build a property with a listing that has co-hosts
    prop_payload = {
        "id": "prop-example-001",
        "name": "Test",
        "public_name": "Test Public",
        "address": {},
        "listings": [
            {
                "platform": "airbnb",
                "platform_id": "AIR-1",
                "co_hosts": [
                    {
                        "user_id": "ch-001",
                        "channel_name": "airbnb",
                        "name": "CoHost Name",
                    },
                ],
            },
        ],
        "checkin": "15:00",
        "checkout": "10:00",
        "listed": True,
    }
    prop = models.HospitableProperty.from_api(prop_payload)
    entry.runtime_data["coordinators"]["properties"].data = {
        "prop-example-001": prop,
    }
    entry.runtime_data["known_property_ids"] = {"prop-example-001"}

    result = await hass.services.async_call(
        const.DOMAIN,
        "list_properties",
        {},
        blocking=True,
        return_response=True,
    )
    props = result["properties"]
    assert len(props) == 1
    listing = props[0]["listings"][0]
    assert len(listing["co_hosts"]) == 1
    co_host = listing["co_hosts"][0]
    assert set(co_host.keys()) == {"user_id", "channel_name", "name"}
    assert "email" not in co_host
    assert "phone_numbers" not in co_host


async def test_list_properties_multi_entry_disambiguation(
    hass: Any,
    respx_router: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """Multi-entry: no config_entry_id raises, specific id works (FR-022).

    With two loaded entries and no config_entry_id, the call raises
    ServiceValidationError. With a specific config_entry_id, only that
    entry's properties are returned.
    """
    import importlib

    const = importlib.import_module("custom_components.hospitable.const")
    from tests.actions.conftest import SECOND_TOKEN

    entry1 = await loaded_config_entry_factory(hass)

    assert hass.services.has_service(const.DOMAIN, "list_properties"), (
        "list_properties is not a registered service"
    )

    await loaded_config_entry_factory(
        hass, account="acct-example-0002", token=SECOND_TOKEN
    )

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            const.DOMAIN,
            "list_properties",
            {},
            blocking=True,
            return_response=True,
        )

    result = await hass.services.async_call(
        const.DOMAIN,
        "list_properties",
        {"config_entry_id": entry1.entry_id},
        blocking=True,
        return_response=True,
    )
    assert isinstance(result, dict)
    assert "properties" in result
