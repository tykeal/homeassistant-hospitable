# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for listing field privacy gating (D2, FR-009 to FR-014).

This module covers Deliverable 2 of spec 004: gating
``platform_email`` and ``platform_picture`` on listing objects behind
the ``guest_contact_details`` option through the existing response
privacy chokepoint.
"""

from __future__ import annotations

from typing import Any

import pytest


def _serialize(payload: Any, *, guest_contact: bool = False) -> Any:
    """Run a payload through the shared response serialiser.

    Args:
        payload: Raw payload to serialise.
        guest_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        The filtered payload.
    """
    from custom_components.hospitable.actions.response import (
        serialize_response,
    )

    return serialize_response(payload, guest_contact=guest_contact)


# ---- T025: Import test for LISTING_KEYS ----


@pytest.mark.xfail(
    raises=ImportError,
    reason="TDD red phase: T025 LISTING_KEYS not yet defined",
    strict=True,
)
def test_listing_keys_import() -> None:
    """``LISTING_KEYS`` can be imported from the response module."""
    from custom_components.hospitable.actions.response import (  # type: ignore[attr-defined]
        LISTING_KEYS,
    )

    assert isinstance(LISTING_KEYS, frozenset)
    assert "listings" in LISTING_KEYS


# ---- T026: Contact fields withheld when opt-in disabled ----


@pytest.mark.xfail(
    raises=AssertionError,
    reason="TDD red phase: T026 listing filter not implemented",
    strict=True,
)
def test_listing_contact_fields_withheld_when_disabled() -> None:
    """``platform_email`` and ``platform_picture`` absent when off.

    The fixture contains SYNTHETIC contact fields. No live listing
    has been observed with ``platform_email`` populated as an email
    address in production data; these are preventive.
    """
    payload = {
        "found": True,
        "property": {
            "id": "prop-1",
            "listings": [
                {
                    "platform": "airbnb",
                    "platform_id": "123",
                    "platform_email": "x@y.com",
                    "platform_picture": "http://pic",
                    "co_hosts": [],
                }
            ],
        },
    }
    result = _serialize(payload, guest_contact=False)
    listing = result["property"]["listings"][0]
    assert "platform_email" not in listing
    assert "platform_picture" not in listing


# ---- T027: Contact fields present when opt-in enabled + unknown dropped ----


@pytest.mark.xfail(
    raises=AssertionError,
    reason="TDD red phase: T027 listing allowlist not implemented",
    strict=True,
)
def test_listing_contact_fields_present_when_enabled_unknown_dropped() -> None:
    """Contact fields present when enabled; unknown keys dropped.

    The unknown ``secret_field`` MUST be absent (fail-closed). The
    current code passes ALL keys through, so this assertion fails.
    """
    payload = {
        "found": True,
        "property": {
            "id": "prop-1",
            "listings": [
                {
                    "platform": "airbnb",
                    "platform_id": "123",
                    "platform_email": "x@y.com",
                    "platform_picture": "http://pic",
                    "co_hosts": [],
                    "secret_field": "oops",
                }
            ],
        },
    }
    result = _serialize(payload, guest_contact=True)
    listing = result["property"]["listings"][0]
    assert listing["platform_email"] == "x@y.com"
    assert listing["platform_picture"] == "http://pic"
    assert "secret_field" not in listing


# ---- T028: List-of-dicts path (THE critical trap) ----


@pytest.mark.xfail(
    raises=AssertionError,
    reason="TDD red phase: T028 list-of-dicts filter not implemented",
    strict=True,
)
def test_listing_filter_on_list_of_dicts() -> None:
    """Every entry in a listing LIST is individually filtered.

    This is the mutation target for T037. The current code's
    ``_filter_identity`` guard ``if not isinstance(value, dict)``
    routes the list through recursive serialisation WITHOUT applying
    the listing allowlist, so ``platform_email`` survives.
    """
    payload = {
        "found": True,
        "property": {
            "id": "prop-1",
            "listings": [
                {
                    "platform": "airbnb",
                    "platform_email": "a@b",
                    "platform_id": "1",
                    "co_hosts": [],
                },
                {
                    "platform": "vrbo",
                    "platform_email": "c@d",
                    "platform_id": "2",
                    "co_hosts": [],
                },
            ],
        },
    }
    result = _serialize(payload, guest_contact=False)
    for entry in result["property"]["listings"]:
        assert "platform_email" not in entry


# ---- T029: co_hosts[].user_id regression + platform_email gating ----


@pytest.mark.xfail(
    raises=AssertionError,
    reason="TDD red phase: T029 listing allowlist not implemented",
    strict=True,
)
def test_co_host_user_id_survives_listing_filter() -> None:
    """``co_hosts[].user_id`` must survive the listing filter.

    This regression test ensures the Airbnb co-host message-sending
    workflow is not broken. The co-host data shape is exactly what
    has been observed in live data: ``{user_id, channel_name, name}``.
    The ``platform_email`` assertion fails in red because no listing
    allowlist filters it out yet.
    """
    payload = {
        "found": True,
        "property": {
            "id": "prop-1",
            "listings": [
                {
                    "platform": "airbnb",
                    "platform_id": "X",
                    "platform_email": "host@example.com",
                    "co_hosts": [
                        {
                            "user_id": "U1",
                            "channel_name": "C",
                            "name": "N",
                        }
                    ],
                }
            ],
        },
    }
    result = _serialize(payload, guest_contact=False)
    listing = result["property"]["listings"][0]
    assert listing["co_hosts"][0]["user_id"] == "U1"
    assert "platform_email" not in listing


# ---- T030: Unknown listing key dropped (fail-closed) ----


@pytest.mark.xfail(
    raises=AssertionError,
    reason="TDD red phase: T030 fail-closed listing filter missing",
    strict=True,
)
def test_unknown_listing_key_dropped() -> None:
    """An unknown listing key MUST be dropped (fail-closed).

    SYNTHETIC fixture: ``totally_new_field`` does not exist in any
    known listing shape.
    """
    payload = {
        "found": True,
        "property": {
            "id": "prop-1",
            "listings": [
                {
                    "platform": "airbnb",
                    "platform_id": "X",
                    "co_hosts": [],
                    "totally_new_field": "surprise",
                }
            ],
        },
    }
    result = _serialize(payload, guest_contact=False)
    listing = result["property"]["listings"][0]
    assert "totally_new_field" not in listing
