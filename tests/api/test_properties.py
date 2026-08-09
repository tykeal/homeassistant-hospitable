# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase properties API tests."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T032 properties"
)
def test_properties_query_contract() -> None:
    """Assert property query parameters."""
    from custom_components.hospitable.api.properties import (
        build_properties_params,  # type: ignore[import-not-found, import-untyped, unused-ignore]
    )

    assert build_properties_params(page=1, per_page=500) == {
        "include": "listings",
        "page": 1,
        "per_page": 100,
    }
