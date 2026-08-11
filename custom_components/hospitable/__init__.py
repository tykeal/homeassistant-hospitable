# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Home Assistant setup for the Hospitable integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.httpx_client import get_async_client

from custom_components.hospitable.api.auth import StaticTokenProvider
from custom_components.hospitable.api.client import HospitableApiClient
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_LOOKAHEAD_DAYS,
    CONF_LOOKBACK_DAYS,
    CONF_PROPERTY_INTERVAL,
    CONF_RESERVATION_INTERVAL,
    CONF_SELECTED_PROPERTIES,
    CONF_TOKEN,
    VERSION,
)
from custom_components.hospitable.const import (
    MINOR_VERSION as MINOR_VERSION,
)
from custom_components.hospitable.const import (
    PLATFORMS as PLATFORMS,
)
from custom_components.hospitable.coordinator import (
    HospitablePropertiesCoordinator,
    HospitableReservationsCoordinator,
)
from custom_components.hospitable.entity import (
    build_device_identifier,
    parse_device_identifier,
)
from custom_components.hospitable.services.window import (
    LOOKAHEAD_DEFAULT,
    LOOKBACK_DEFAULT,
)


async def _async_update_options(hass: Any, entry: Any) -> None:
    """Reload an entry after options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _known_property_ids(
    registry: dr.DeviceRegistry, entry_id: str, account_namespace: str
) -> set[str]:
    """Return property ids that already have a device for this entry.

    A deselected property keeps its device (and entities) so its history
    survives; discovering those ids lets the sensor platform recreate the
    entities as unavailable rather than deleting them (FR-018, FR-055).
    """
    known: set[str] = set()
    for device in dr.async_entries_for_config_entry(registry, entry_id):
        for identifier in device.identifiers:
            property_id = parse_device_identifier(identifier, account_namespace)
            if property_id is not None:
                known.add(property_id)
    return known


async def async_setup_entry(hass: Any, entry: Any) -> bool:
    """Set up one Hospitable config entry and forward the sensor platform."""
    client = HospitableApiClient(
        StaticTokenProvider(entry.data[CONF_TOKEN]), get_async_client(hass)
    )
    properties_coordinator = HospitablePropertiesCoordinator(
        hass,
        client,
        config_entry=entry,
        interval_minutes=entry.options.get(CONF_PROPERTY_INTERVAL),
    )
    await properties_coordinator.async_refresh()

    account_namespace = entry.data[CONF_ACCOUNT_NAMESPACE]
    selected_properties = set(entry.options.get(CONF_SELECTED_PROPERTIES, []))
    properties = properties_coordinator.data or {}
    selected = sorted(selected_properties or set(properties))

    registry = dr.async_get(hass)
    known = sorted(
        set(selected) | _known_property_ids(registry, entry.entry_id, account_namespace)
    )

    reservations_coordinator = HospitableReservationsCoordinator(
        hass,
        client,
        property_ids=list(selected),
        lookback_days=entry.options.get(CONF_LOOKBACK_DAYS, LOOKBACK_DEFAULT),
        lookahead_days=entry.options.get(CONF_LOOKAHEAD_DAYS, LOOKAHEAD_DEFAULT),
        config_entry=entry,
        interval_minutes=entry.options.get(CONF_RESERVATION_INTERVAL),
    )
    await reservations_coordinator.async_refresh()

    for property_id in known:
        property_model = properties.get(property_id)
        registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={build_device_identifier(account_namespace, property_id)},
            manufacturer="Hospitable",
            name=property_model.name if property_model is not None else property_id,
        )

    remove_listener = entry.add_update_listener(_async_update_options)
    entry.runtime_data = {
        "client": client,
        "coordinators": {
            "properties": properties_coordinator,
            "reservations": reservations_coordinator,
        },
        "selected_property_ids": selected,
        "known_property_ids": known,
        "listeners": [remove_listener],
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: Any, entry: Any) -> bool:
    """Unload one Hospitable config entry and runtime data."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    runtime_data = getattr(entry, "runtime_data", None)
    if isinstance(runtime_data, dict):
        for remove_listener in runtime_data.get("listeners", []):
            remove_listener()
    entry.runtime_data = None
    return bool(unload_ok)


async def async_migrate_entry(hass: Any, entry: Any) -> bool:
    """Migrate entries while preserving frozen unique identifiers."""
    return bool(getattr(entry, "version", VERSION) <= VERSION)


__all__ = ["MINOR_VERSION", "PLATFORMS", "VERSION"]
