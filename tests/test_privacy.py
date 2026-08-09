# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase privacy tests."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T043 privacy"
)
def test_privacy_audit_helpers(synthetic_token: str) -> None:
    """Assert lifecycle privacy audit has no leaks and no channels call."""
    from custom_components.hospitable.api.redaction import (  # type: ignore[import-not-found, import-untyped, unused-ignore]
        contains_private_data,
        redact,
    )

    assert not contains_private_data(
        redact({"token": synthetic_token, "email": "guest@example.com"}),
        [synthetic_token, "guest@example.com"],
    )
