# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase constants tests."""

from __future__ import annotations


def test_api_constants() -> None:
    """Assert API constants are centralized."""
    from custom_components.hospitable.api.const import (
        BASE_URL,
        CALENDAR_PATH,
        PROPERTIES_PATH,
        RESERVATIONS_PATH,
        USER_PATH,
    )

    assert BASE_URL == "https://public.api.hospitable.com/v2"
    assert {USER_PATH, PROPERTIES_PATH, RESERVATIONS_PATH, CALENDAR_PATH} == {
        "/user",
        "/properties",
        "/reservations",
        "/properties/{id}/calendar",
    }
