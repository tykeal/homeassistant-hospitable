# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase diagnostics tests."""

from __future__ import annotations


def test_diagnostics_are_allowlisted(synthetic_token: str) -> None:
    """Assert diagnostics omit credentials and personal data."""
    from custom_components.hospitable.diagnostics import (
        redact_diagnostics,
    )

    data = redact_diagnostics(
        {
            "token": synthetic_token,
            "email": "guest@example.com",
            "options": {"lookback_days": 90},
        }
    )
    assert synthetic_token not in str(data) and "guest@example.com" not in str(data)
