# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for entity/device targeting on property-scoped actions (Deliverable C)."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    device_registry as dr,
)
from homeassistant.helpers import (
    entity_registry as er,
)

from custom_components.hospitable.actions.helpers import resolve_property_id
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    DOMAIN,
)
from custom_components.hospitable.entity import build_device_identifier

NAMESPACE = "acct-example-0001"


def _mock_entry(hass: Any, entry_id: str = "test-entry-id") -> Any:
    """Build and register a minimal MockConfigEntry."""
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_ACCOUNT_NAMESPACE: NAMESPACE,
            CONF_NAMESPACE_SOURCE: "account",
            "token": "hp_test_000",
        },
        unique_id=entry_id,
        entry_id=entry_id,
    )
    entry.add_to_hass(hass)
    return entry


# --- T035 --- #


def test_resolve_property_id_importable() -> None:
    """resolve_property_id is importable from helpers (FR-019)."""
    assert resolve_property_id is not None


# --- T036: conflict rule --- #


def test_conflict_same_property_proceeds(hass: Any) -> None:
    """Both property_id and target resolve to same property (FR-017)."""
    entry = _mock_entry(hass)
    device_reg = dr.async_get(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={build_device_identifier(NAMESPACE, "prop-001")},
    )

    result = resolve_property_id(
        hass,
        entry,
        property_id="prop-001",
        target={"device_id": [device_entry.id]},
    )
    assert result == "prop-001"


def test_conflict_different_property_raises(hass: Any) -> None:
    """Differing property_id and target raise error (FR-017)."""
    entry = _mock_entry(hass)
    device_reg = dr.async_get(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={build_device_identifier(NAMESPACE, "prop-001")},
    )

    with pytest.raises(ServiceValidationError, match="different"):
        resolve_property_id(
            hass,
            entry,
            property_id="prop-other",
            target={"device_id": [device_entry.id]},
        )


# --- T037: neither supplied --- #


def test_neither_property_id_nor_target_raises(hass: Any) -> None:
    """Neither property_id nor target raises error (FR-018)."""
    entry = _mock_entry(hass)
    with pytest.raises(ServiceValidationError, match="Provide"):
        resolve_property_id(
            hass,
            entry,
            property_id=None,
            target=None,
        )


# --- T038: only property_id supplied --- #


def test_only_property_id_proceeds(hass: Any) -> None:
    """Only property_id supplied proceeds directly (FR-016)."""
    entry = _mock_entry(hass)
    result = resolve_property_id(
        hass,
        entry,
        property_id="prop-direct",
        target=None,
    )
    assert result == "prop-direct"


# --- T039: cross-entry device target --- #


def test_cross_entry_device_target_raises(hass: Any) -> None:
    """Device from different config entry raises error (FR-020)."""
    entry_a = _mock_entry(hass, entry_id="entry-A")
    _mock_entry(hass, entry_id="entry-B")
    device_reg = dr.async_get(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id="entry-B",
        identifiers={build_device_identifier(NAMESPACE, "prop-001")},
    )

    with pytest.raises(ServiceValidationError, match="different"):
        resolve_property_id(
            hass,
            entry_a,
            property_id=None,
            target={"device_id": [device_entry.id]},
        )


# --- T040: wrong integration domain --- #


def test_non_hospitable_device_target_raises(hass: Any) -> None:
    """Device from wrong integration domain raises error (FR-020)."""
    entry = _mock_entry(hass)
    device_reg = dr.async_get(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("other_integration", "some_id")},
    )

    with pytest.raises(ServiceValidationError, match="not a Hospitable"):
        resolve_property_id(
            hass,
            entry,
            property_id=None,
            target={"device_id": [device_entry.id]},
        )


# --- T041: entity target resolution --- #


def test_entity_target_resolves_property_id(hass: Any) -> None:
    """Entity target resolves to property_id via device (FR-015)."""
    entry = _mock_entry(hass)
    device_reg = dr.async_get(hass)
    device_entry = device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={build_device_identifier(NAMESPACE, "prop-001")},
    )
    ent_registry = er.async_get(hass)
    ent_entry = ent_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{NAMESPACE}_prop-001_property_info",
        config_entry=entry,
        device_id=device_entry.id,
    )

    result = resolve_property_id(
        hass,
        entry,
        property_id=None,
        target={"entity_id": [ent_entry.entity_id]},
    )
    assert result == "prop-001"


# --- T042: get_reservations e2e with device target --- #


async def test_get_reservations_with_device_target(
    hass: Any,
    respx_router: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """get_reservations accepts device target without property_id (FR-015)."""
    import httpx

    from custom_components.hospitable.api.const import BASE_URL
    from custom_components.hospitable.const import DOMAIN as HDOM

    entry = await loaded_config_entry_factory(hass)
    assert hass.services.has_service(HDOM, "get_reservations")

    # Find the device for prop-example-001
    device_reg = dr.async_get(hass)
    namespace = entry.data[CONF_ACCOUNT_NAMESPACE]
    device_entry = device_reg.async_get_device(
        identifiers={build_device_identifier(namespace, "prop-example-001")},
    )
    assert device_entry is not None

    from tests.helpers import load_fixture

    respx_router.get(
        f"{BASE_URL}/reservations",
        params={"include": "guest,properties"},
    ).mock(
        return_value=httpx.Response(
            200,
            json=load_fixture("reservations_page1.json"),
        ),
    )

    result = await hass.services.async_call(
        HDOM,
        "get_reservations",
        {},
        target={"device_id": [device_entry.id]},
        blocking=True,
        return_response=True,
    )
    assert result is not None
    assert result["found"] is True
    assert result["property_id"] == "prop-example-001"


# --- T043: get_property_info e2e with entity target --- #


async def test_get_property_info_with_entity_target(
    hass: Any,
    respx_router: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """get_property_info accepts entity target without property_id (FR-015)."""
    from custom_components.hospitable.const import DOMAIN as HDOM
    from custom_components.hospitable.entity import build_unique_id

    entry = await loaded_config_entry_factory(hass)
    assert hass.services.has_service(HDOM, "get_property_info")

    ent_registry = er.async_get(hass)
    uid = build_unique_id(
        entry.data[CONF_ACCOUNT_NAMESPACE],
        "prop-example-001",
        "property_info",
    )
    entity_id = ent_registry.async_get_entity_id("sensor", HDOM, uid)
    assert entity_id is not None

    result = await hass.services.async_call(
        HDOM,
        "get_property_info",
        {},
        target={"entity_id": [entity_id]},
        blocking=True,
        return_response=True,
    )
    assert result is not None
    assert result["found"] is True
