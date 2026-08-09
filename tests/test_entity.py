# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase entity helper tests."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T039 entity"
)
def test_unique_id_and_device_helpers() -> None:
    """Assert frozen unique IDs and suggested object IDs."""
    from custom_components.hospitable.entity import (  # type: ignore[import-not-found, import-untyped, unused-ignore]
        build_device_identifier,
        build_suggested_object_id,
        build_unique_id,
    )

    assert (
        build_unique_id("acct", "prop", "reservation_status")
        == "acct_prop_reservation_status"
    )
    assert (
        build_suggested_object_id("Beach House", "property_info")
        == "hospitable_beach_house_property_info"
    )
    assert build_device_identifier("acct", "prop") == ("hospitable", "acct_prop")
