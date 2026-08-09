# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase timezone tests."""

from __future__ import annotations

from typing import Any

import pytest


async def test_timezone_resolution_uses_ha_helper(hass: Any) -> None:
    """Assert effective timezone validates IANA names."""
    from custom_components.hospitable.services.timezones import (
        resolve_timezone,
    )

    assert await resolve_timezone(hass, None) == str(hass.config.time_zone)
    with pytest.raises(ValueError, match="IANA"):
        await resolve_timezone(hass, "-0700")
