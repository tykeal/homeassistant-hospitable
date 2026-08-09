# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase reservations API tests."""

from __future__ import annotations

from datetime import date

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T033 reservations"
)
def test_reservation_query_contract() -> None:
    """Assert reservations send required filters."""
    from custom_components.hospitable.api.reservations import (  # type: ignore[import-not-found, import-untyped, unused-ignore]
        build_reservation_params,
        chunk_property_ids,
    )

    assert len(next(chunk_property_ids([str(i) for i in range(51)]))) == 50
    params = build_reservation_params(["p1"], date(2025, 1, 1), date(2025, 1, 2))
    assert params["date_query"] == "checkin" and params["include"] == "properties"
