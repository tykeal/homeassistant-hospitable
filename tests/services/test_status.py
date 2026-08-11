# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase status-mapping tests (T069)."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from custom_components.hospitable.api.models import HospitableReservation
from tests.helpers import load_fixture


def _status_mapper() -> Any:
    """Import and build the not-yet-implemented status mapper."""
    from custom_components.hospitable.services.status import (
        StatusMapper,
    )

    return StatusMapper()


def test_six_categories_map_explicitly() -> None:
    """Every upstream category maps to a defined enum state."""
    mapper = _status_mapper()
    assert mapper.map("request", "occupied") == "pending_request"
    assert mapper.map("accepted", "occupied") == "occupied"
    assert mapper.map("accepted", "awaiting_checkin") == "awaiting_checkin"
    assert mapper.map("cancelled", "occupied") == "cancelled"
    assert mapper.map("not accepted", "occupied") == "not_accepted"
    assert mapper.map("unknown", "occupied") == "unknown"
    assert mapper.map("checkpoint", "occupied") == "checkpoint"


def test_checkpoint_does_not_reach_unknown_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Checkpoint is a published category and must not be logged as unknown."""
    mapper = _status_mapper()
    with caplog.at_level(logging.WARNING):
        assert mapper.map("checkpoint", "occupied") == "checkpoint"
    assert caplog.records == []


def test_unrecognized_status_maps_to_unknown_logged_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unrecognized status maps to unknown and logs once without raising."""
    mapper = _status_mapper()
    with caplog.at_level(logging.WARNING):
        assert mapper.map("teleported", "occupied") == "unknown"
        assert mapper.map("teleported", "occupied") == "unknown"
    warnings = [r for r in caplog.records if "teleported" in r.getMessage()]
    assert len(warnings) == 1


def test_status_read_from_structured_path_only() -> None:
    """Status comes from reservation_status.current, never the flat field."""
    mapper = _status_mapper()
    payload = load_fixture("reservation_accepted.json")["data"][0]
    payload["status"] = "cancelled"
    payload["reservation_status"]["current"] = {
        "category": "accepted",
        "sub_category": None,
    }
    reservation = HospitableReservation.from_api(payload)
    assert reservation.status_category == "accepted"
    assert reservation.raw_status == "cancelled"
    assert mapper.map(reservation.status_category, "occupied") == "occupied"
