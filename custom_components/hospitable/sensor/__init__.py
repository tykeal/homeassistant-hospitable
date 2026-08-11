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
    CONF_TIMEZONE_OVERRIDES,
)
from custom_components.hospitable.sensor.property import build_property_sensors
from custom_components.hospitable.sensor.reservation import build_reservation_sensors
from custom_components.hospitable.services.timezones import resolve_property_timezone


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the reservation and property sensors for the configuration."""
    runtime_data: dict[str, Any] = entry.runtime_data
    coordinators = runtime_data["coordinators"]
    reservations_coordinator = coordinators["reservations"]
    properties_coordinator = coordinators["properties"]
    properties = properties_coordinator.data or {}

    account_namespace = entry.data[CONF_ACCOUNT_NAMESPACE]
    selected = sorted(
        set(entry.options.get(CONF_SELECTED_PROPERTIES, [])) or set(properties)
    )
    properties_coordinator.monitored_property_ids = set(selected)
    property_names = {
        property_id: (
            properties[property_id].name if property_id in properties else property_id
        )
        for property_id in selected
    }

    overrides: dict[str, str] = entry.options.get(CONF_TIMEZONE_OVERRIDES, {}) or {}
    property_timezones: dict[str, tuple[str, str]] = {}
    for property_id in selected:
        override = overrides.get(property_id)
        try:
            property_timezones[property_id] = await resolve_property_timezone(
                hass, override
            )
        except ValueError:
            property_timezones[property_id] = (str(hass.config.time_zone), "instance")

    async_add_entities(
        [
            *build_reservation_sensors(
                reservations_coordinator,
                account_namespace,
                property_names,
                properties_coordinator,
            ),
            *build_property_sensors(
                reservations_coordinator,
                properties_coordinator,
                account_namespace,
                property_names,
                property_timezones,
            ),
        ]
    )
