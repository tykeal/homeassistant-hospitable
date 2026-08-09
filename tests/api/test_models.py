# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase model tests."""

from __future__ import annotations

import pytest

from tests.helpers import load_fixture


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T031 models"
)
def test_models_drop_personal_fields_and_timezone() -> None:
    """Assert models parse fixtures and drop prohibited fields."""
    from custom_components.hospitable.api.models import (  # type: ignore[import-not-found, import-untyped, unused-ignore]
        HospitableProperty,
        HospitableReservation,
    )

    prop = HospitableProperty.from_api(
        load_fixture("properties_single.json")["data"][0]
    )
    res = HospitableReservation.from_api(
        load_fixture("reservations_page1.json")["data"][0]
    )
    assert not hasattr(prop, "timezone")
    assert prop.capacity.max_guests == 6
    assert res.arrival_date.isoformat() == "2025-06-14"
    assert not hasattr(res, "guest")
