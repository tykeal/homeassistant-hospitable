# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Home Assistant setup for the Hospitable integration."""

from __future__ import annotations

from typing import Any

from custom_components.hospitable.const import (
    MINOR_VERSION as MINOR_VERSION,
)
from custom_components.hospitable.const import (
    PLATFORMS as PLATFORMS,
)
from custom_components.hospitable.const import (
    VERSION,
)


async def async_setup_entry(hass: Any, entry: Any) -> bool:
    """Set up one Hospitable config entry without forwarding a platform."""
    entry.runtime_data = {"coordinators": ["properties"]}
    return True


async def async_unload_entry(hass: Any, entry: Any) -> bool:
    """Unload one Hospitable config entry and runtime data."""
    if hasattr(entry, "runtime_data"):
        entry.runtime_data = None
    return True


async def async_migrate_entry(hass: Any, entry: Any) -> bool:
    """Migrate entries while preserving frozen unique identifiers."""
    return getattr(entry, "version", VERSION) <= VERSION


__all__ = ["MINOR_VERSION", "PLATFORMS", "VERSION"]
