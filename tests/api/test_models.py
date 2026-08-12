# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase model tests."""

from __future__ import annotations

import copy

from tests.helpers import load_fixture


def test_models_drop_personal_fields_and_timezone() -> None:
    """Assert models parse fixtures and drop prohibited fields."""
    from custom_components.hospitable.api.models import (
        HospitableGuest,
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
    assert prop.capacity.max == 6
    assert res.arrival_date.isoformat() == "2025-06-14"
    # US3 (FR-039) deliberately reverses the spec 001 claim that the
    # reservation model carries no ``guest``: guest identity is now
    # parsed for the entity attribute surface, under its own per-surface
    # controls.
    assert res.guest is not None
    assert res.guest.first_name == "Example"
    # What is UNCHANGED is that ``profile_picture`` is never read into
    # the model at all, even though the fixture supplies one (FR-039d).
    assert not hasattr(res.guest, "profile_picture")
    assert "avatar" not in repr(res.guest)
    assert HospitableGuest.from_api(None) is None


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
    assert prop.capacity.max == 6
    assert prop.capacity.bedrooms == 3
    assert prop.capacity.beds == 4
    assert prop.capacity.bathrooms == 2.5
    assert prop.checkin == "16:00"
    assert prop.checkout == "11:00"

    payload["capacity"] = {"maximum": 9, "bedrooms": 1, "beds": 1, "bathrooms": 1}
    payload["checkin"] = "4pm"
    payload["checkout"] = "1100"
    degraded = HospitableProperty.from_api(payload)

    assert degraded.capacity is not None
    assert degraded.capacity.max is None
    assert degraded.checkin is None
    assert degraded.checkout is None
