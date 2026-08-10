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
