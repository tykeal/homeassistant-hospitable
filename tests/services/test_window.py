# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase window tests."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T035 window"
)
def test_window_bounds() -> None:
    """Assert reservation window defaults and bounds."""
    from custom_components.hospitable.services.window import (
        validate_window,  # type: ignore[import-not-found, import-untyped, unused-ignore]
    )

    assert validate_window(90, 90) == (90, 90)
    with pytest.raises(ValueError, match="lookback"):
        validate_window(6, 90)
