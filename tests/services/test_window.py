# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase window tests."""

from __future__ import annotations

import pytest


def test_window_bounds() -> None:
    """Assert reservation window defaults and bounds."""
    from custom_components.hospitable.services.window import (
        validate_window,
    )

    assert validate_window(90, 90) == (90, 90)
    with pytest.raises(ValueError, match="lookback"):
        validate_window(6, 90)
