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
from custom_components.hospitable.coordinator import HospitablePropertiesCoordinator
from custom_components.hospitable.entity import build_device_identifier


async def _async_update_options(hass: Any, entry: Any) -> None:
    """Reload an entry after options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: Any, entry: Any) -> bool:
    """Set up one Hospitable config entry without forwarding a platform."""
    client = HospitableApiClient(
        StaticTokenProvider(entry.data[CONF_TOKEN]), get_async_client(hass)
    )
    coordinator = HospitablePropertiesCoordinator(client.get_properties)
    await coordinator.async_refresh()

    account_namespace = entry.data[CONF_ACCOUNT_NAMESPACE]
    selected_properties = set(entry.options.get(CONF_SELECTED_PROPERTIES, []))
    properties = coordinator.data or {}
    selected = selected_properties or set(properties)
    registry = dr.async_get(hass)
    for property_id in selected:
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
        "coordinators": {"properties": coordinator},
        "listeners": [remove_listener],
    }
    return True


async def async_unload_entry(hass: Any, entry: Any) -> bool:
    """Unload one Hospitable config entry and runtime data."""
    runtime_data = getattr(entry, "runtime_data", None)
    if isinstance(runtime_data, dict):
        for remove_listener in runtime_data.get("listeners", []):
            remove_listener()
    entry.runtime_data = None
    return True


async def async_migrate_entry(hass: Any, entry: Any) -> bool:
    """Migrate entries while preserving frozen unique identifiers."""
    return getattr(entry, "version", VERSION) <= VERSION


__all__ = ["MINOR_VERSION", "PLATFORMS", "VERSION"]
