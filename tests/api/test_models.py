# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase model tests."""

from __future__ import annotations

import copy

import pytest

from tests.helpers import load_fixture


def test_models_drop_personal_fields_and_timezone() -> None:
    """Assert models parse fixtures and drop prohibited fields."""
    from custom_components.hospitable.api.models import (
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
    assert prop.capacity is not None
    assert prop.capacity.max_guests == 6
    assert res.arrival_date.isoformat() == "2025-06-14"
    assert not hasattr(res, "guest")


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T020 property shape and wall-clock times",
)
def test_property_capacity_keys_and_wall_clock_validation() -> None:
    """Assert capacity uses confirmed keys and invalid wall-clock strings degrade."""
    from custom_components.hospitable.api.models import HospitableProperty

    payload = copy.deepcopy(load_fixture("properties_single.json")["data"][0])
    payload["capacity"] = {
        "max": 6,
        "bedrooms": 3,
        "beds": 4,
        "bathrooms": 2.5,
    }
    prop = HospitableProperty.from_api(payload)

    assert prop.capacity is not None
    assert prop.capacity.max_guests == 6
    assert prop.capacity.bedrooms == 3
    assert prop.capacity.beds == 4
    assert prop.capacity.bathrooms == 2.5
    assert prop.checkin == "16:00"
    assert prop.checkout == "11:00"

    payload["capacity"] = {"max_guests": 9, "bedrooms": 1, "beds": 1, "bathrooms": 1}
    payload["checkin"] = "4pm"
    payload["checkout"] = "1100"
    degraded = HospitableProperty.from_api(payload)

    assert degraded.capacity is not None
    assert degraded.capacity.max_guests is None
    assert degraded.checkin is None
    assert degraded.checkout is None
