# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Entity and device identifier helpers for Hospitable properties."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.hospitable.const import DOMAIN
from custom_components.hospitable.coordinator import HospitableDataUpdateCoordinator
from custom_components.hospitable.services.lifecycle import property_active

MAX_CONSECUTIVE_FAILURES = 3


class HospitableEntity(CoordinatorEntity[HospitableDataUpdateCoordinator[Any]]):
    """Base entity applying the three-strike availability policy.

    The entity stays available through two consecutive poll failures,
    retaining its last known state, and only reports unavailable once a
    third consecutive failure has occurred (FR-057). An entity that has
    never received coordinator data is unavailable.

    When ``_presence_coordinator`` and ``_presence_property_id`` are set,
    the entity is additionally unavailable whenever its property is no
    longer present or monitored, which is the shared non-destructive
    lifecycle path for upstream disappearance (FR-056) and deselection
    (FR-018).
    """

    _attr_has_entity_name = True
    _presence_coordinator: HospitableDataUpdateCoordinator[Any] | None = None
    _presence_property_id: str | None = None

    @property
    def available(self) -> bool:
        """Return availability under the three-strike failure policy."""
        coordinator = self.coordinator
        if (
            coordinator.data is None
            or coordinator.consecutive_failures >= MAX_CONSECUTIVE_FAILURES
        ):
            return False
        if self._presence_coordinator is None or self._presence_property_id is None:
            return True
        return property_active(self._presence_coordinator, self._presence_property_id)

    async def async_added_to_hass(self) -> None:
        """Subscribe to the presence coordinator for availability updates.

        Entities whose primary coordinator is not the properties
        coordinator would otherwise never re-render when a monitored
        property disappears, because that event arrives on the properties
        coordinator. Subscribing here makes their availability track the
        shared disappearance path (FR-056).
        """
        await super().async_added_to_hass()
        presence = self._presence_coordinator
        if presence is not None and presence is not self.coordinator:
            self.async_on_remove(presence.async_add_listener(self.async_write_ha_state))


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
