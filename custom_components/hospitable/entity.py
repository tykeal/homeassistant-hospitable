# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Entity and device identifier helpers for Hospitable properties."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.hospitable.const import DOMAIN
from custom_components.hospitable.coordinator import _HospitableCoordinator

MAX_CONSECUTIVE_FAILURES = 3


class HospitableEntity(CoordinatorEntity[_HospitableCoordinator[Any]]):
    """Base entity applying the three-strike availability policy.

    The entity stays available through two consecutive poll failures,
    retaining its last known state, and only reports unavailable once a
    third consecutive failure has occurred (FR-057). An entity that has
    never received coordinator data is unavailable.
    """

    _attr_has_entity_name = True

    @property
    def available(self) -> bool:
        """Return availability under the three-strike failure policy."""
        coordinator = self.coordinator
        return (
            coordinator.data is not None
            and coordinator.consecutive_failures < MAX_CONSECUTIVE_FAILURES
        )


def _slugify(value: str) -> str:
    """Return a Home Assistant style slug."""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.casefold())).strip("_")


def build_unique_id(account_namespace: str, property_id: str, entity_key: str) -> str:
    """Build the frozen unique identifier for a property entity."""
    return f"{account_namespace}_{property_id}_{entity_key}"


def build_suggested_object_id(property_name: str, entity_key: str) -> str:
    """Build the default entity object identifier."""
    return f"hospitable_{_slugify(property_name)}_{entity_key}"


def build_device_identifier(
    account_namespace: str, property_id: str
) -> tuple[str, str]:
    """Build the device registry identifier tuple."""
    return (DOMAIN, f"{account_namespace}_{property_id}")
