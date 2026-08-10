# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase redaction tests."""

from __future__ import annotations


def test_redaction_removes_private_values(synthetic_token: str) -> None:
    """Assert token and personal fields are redacted."""
    from custom_components.hospitable.api.redaction import (
        redact,
    )

    text = redact(
        {
            "token": synthetic_token,
            "email": "guest@example.com",
            "phone": "+15550101000",
        }
    )
    assert synthetic_token not in text and "guest@example.com" not in text
