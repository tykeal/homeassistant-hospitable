# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase entity helper tests."""

from __future__ import annotations


def test_unique_id_and_device_helpers() -> None:
    """Assert frozen unique IDs and suggested object IDs."""
    from custom_components.hospitable.entity import (
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


def test_parse_device_identifier_round_trips() -> None:
    """Assert parse inverts build and rejects foreign identifiers."""
    from custom_components.hospitable.entity import (
        build_device_identifier,
        parse_device_identifier,
    )

    identifier = build_device_identifier("acct-0001", "prop-example-001")
    assert parse_device_identifier(identifier, "acct-0001") == "prop-example-001"

    assert parse_device_identifier(identifier, "acct-0002") is None
    foreign = ("other_domain", "acct-0001_prop")
    assert parse_device_identifier(foreign, "acct-0001") is None
