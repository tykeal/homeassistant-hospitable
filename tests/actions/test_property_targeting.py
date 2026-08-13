# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for entity/device targeting on property-scoped actions (Deliverable C)."""

from __future__ import annotations

from typing import Any

import pytest


def _try_import_resolver() -> Any:
    """Import resolve_property_id, returning None on failure."""
    try:
        from custom_components.hospitable.actions.helpers import (  # type: ignore[attr-defined]
            resolve_property_id,
        )
    except ImportError:
        return None
    return resolve_property_id


# --- T035 --- #


@pytest.mark.xfail(
    raises=ImportError,
    reason="T035: resolve_property_id not yet defined",
    strict=True,
)
def test_resolve_property_id_importable() -> None:
    """resolve_property_id is importable from helpers (FR-019)."""
    from custom_components.hospitable.actions.helpers import (  # type: ignore[attr-defined]
        resolve_property_id,
    )

    assert resolve_property_id is not None


# --- T036: conflict rule --- #


@pytest.mark.xfail(
    raises=AssertionError,
    reason="T036: resolve_property_id does not exist",
    strict=True,
)
def test_conflict_same_property_proceeds() -> None:
    """Both property_id and target resolve to same property (FR-017)."""
    resolve_property_id = _try_import_resolver()
    assert resolve_property_id is not None, "resolve_property_id must exist"


@pytest.mark.xfail(
    raises=AssertionError,
    reason="T036: resolve_property_id does not exist",
    strict=True,
)
def test_conflict_different_property_raises() -> None:
    """Differing property_id and target raise error (FR-017)."""
    resolve_property_id = _try_import_resolver()
    assert resolve_property_id is not None, "resolve_property_id must exist"


# --- T037: neither supplied --- #


@pytest.mark.xfail(
    raises=AssertionError,
    reason="T037: resolve_property_id does not exist",
    strict=True,
)
def test_neither_property_id_nor_target_raises() -> None:
    """Neither property_id nor target raises error (FR-018)."""
    resolve_property_id = _try_import_resolver()
    assert resolve_property_id is not None, "resolve_property_id must exist"


# --- T038: only property_id supplied --- #


@pytest.mark.xfail(
    raises=AssertionError,
    reason="T038: resolve_property_id does not exist",
    strict=True,
)
def test_only_property_id_proceeds() -> None:
    """Only property_id supplied proceeds directly (FR-016)."""
    resolve_property_id = _try_import_resolver()
    assert resolve_property_id is not None, "resolve_property_id must exist"


# --- T039: cross-entry device target --- #


@pytest.mark.xfail(
    raises=AssertionError,
    reason="T039: resolve_property_id does not exist",
    strict=True,
)
def test_cross_entry_device_target_raises() -> None:
    """Device from different config entry raises error (FR-020)."""
    resolve_property_id = _try_import_resolver()
    assert resolve_property_id is not None, "resolve_property_id must exist"


# --- T040: wrong integration domain --- #


@pytest.mark.xfail(
    raises=AssertionError,
    reason="T040: resolve_property_id does not exist",
    strict=True,
)
def test_non_hospitable_device_target_raises() -> None:
    """Device from wrong integration domain raises error (FR-020)."""
    resolve_property_id = _try_import_resolver()
    assert resolve_property_id is not None, "resolve_property_id must exist"


# --- T041: entity target resolution --- #


@pytest.mark.xfail(
    raises=AssertionError,
    reason="T041: resolve_property_id does not exist",
    strict=True,
)
def test_entity_target_resolves_property_id() -> None:
    """Entity target resolves to property_id via device (FR-015)."""
    resolve_property_id = _try_import_resolver()
    assert resolve_property_id is not None, "resolve_property_id must exist"


# --- T042: get_reservations e2e with device target --- #


@pytest.mark.xfail(
    raises=AssertionError,
    reason="T042: get_reservations does not support targets",
    strict=True,
)
async def test_get_reservations_with_device_target(
    hass: Any,
    respx_router: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """get_reservations accepts device target without property_id (FR-015)."""
    from custom_components.hospitable.const import DOMAIN

    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "get_reservations")

    # The service currently requires property_id; calling without
    # it will fail. Assert success to force the red phase failure.
    try:
        result = await hass.services.async_call(
            DOMAIN,
            "get_reservations",
            {},
            target={"device_id": ["nonexistent_device_id"]},
            blocking=True,
            return_response=True,
        )
    except Exception:
        result = None
    assert result is not None, "get_reservations should accept device target"


# --- T043: get_property_info e2e with entity target --- #


@pytest.mark.xfail(
    raises=AssertionError,
    reason="T043: get_property_info does not support targets",
    strict=True,
)
async def test_get_property_info_with_entity_target(
    hass: Any,
    respx_router: Any,
    loaded_config_entry_factory: Any,
) -> None:
    """get_property_info accepts entity target without property_id (FR-015)."""
    from custom_components.hospitable.const import DOMAIN

    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "get_property_info")

    try:
        result = await hass.services.async_call(
            DOMAIN,
            "get_property_info",
            {},
            target={"entity_id": ["sensor.nonexistent"]},
            blocking=True,
            return_response=True,
        )
    except Exception:
        result = None
    assert result is not None, "get_property_info should accept entity target"
