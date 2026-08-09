# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase timezone tests."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T036 timezones"
)
async def test_timezone_resolution_uses_ha_helper(hass) -> None:
    """Assert effective timezone validates IANA names."""
    from custom_components.hospitable.services.timezones import (
        resolve_timezone,  # type: ignore[import-not-found, import-untyped, unused-ignore]
    )

    assert await resolve_timezone(hass, None) == str(hass.config.time_zone)
    with pytest.raises(ValueError, match="IANA"):
        await resolve_timezone(hass, "-0700")
