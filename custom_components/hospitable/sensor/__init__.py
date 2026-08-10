# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Sensor platform setup for the Hospitable integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_SELECTED_PROPERTIES,
)
from custom_components.hospitable.sensor.reservation import build_reservation_sensors


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create reservation status sensors for the configured properties."""
    runtime_data: dict[str, Any] = entry.runtime_data
    coordinators = runtime_data["coordinators"]
    reservations_coordinator = coordinators["reservations"]
    properties = coordinators["properties"].data or {}

    account_namespace = entry.data[CONF_ACCOUNT_NAMESPACE]
    selected = set(entry.options.get(CONF_SELECTED_PROPERTIES, [])) or set(properties)
    property_names = {
        property_id: (
            properties[property_id].name if property_id in properties else property_id
        )
        for property_id in selected
    }

    async_add_entities(
        build_reservation_sensors(
            reservations_coordinator, account_namespace, property_names
        )
    )
