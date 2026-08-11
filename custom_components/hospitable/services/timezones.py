# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Timezone resolution helpers that avoid blocking ZoneInfo calls."""

from __future__ import annotations

from typing import Any

from homeassistant.util import dt as dt_util


async def resolve_timezone(hass: Any, override: str | None) -> str:
    """Resolve an effective IANA timezone from an optional override."""
    if override is None:
        return str(hass.config.time_zone)
    zone = await dt_util.async_get_time_zone(override)
    if zone is None:
        raise ValueError("timezone override must be an IANA name")
    return override


async def resolve_property_timezone(hass: Any, override: str | None) -> tuple[str, str]:
    """Resolve a property's effective IANA timezone and its source.

    Returns the effective IANA zone name paired with ``"override"`` when
    a per-property override supplied it, or ``"instance"`` when it falls
    back to the Home Assistant instance timezone. A non-IANA override
    (such as an upstream fixed offset) raises ``ValueError`` so it is
    rejected rather than silently applied (FR-074).
    """
    if override is None:
        return str(hass.config.time_zone), "instance"
    return await resolve_timezone(hass, override), "override"
