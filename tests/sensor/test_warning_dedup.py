# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase occupancy warning deduplication tests (D3)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest

from custom_components.hospitable.api.models import HospitableReservation
from custom_components.hospitable.sensor.reservation import HospitableReservationSensor
from tests.helpers import load_fixture


def _arrival_today_missing_checkin() -> HospitableReservation:
    """Build a reservation arriving today whose check-in time is missing."""
    zone = timezone(timedelta(hours=-7))
    today = datetime.now(zone).date()
    departure = today + timedelta(days=2)
    payload = dict(load_fixture("reservation_accepted.json")["data"][0])
    payload.update(
        {
            "id": "res-degraded-001",
            "arrival_date": f"{today.isoformat()}T00:00:00-07:00",
            "departure_date": f"{departure.isoformat()}T00:00:00-07:00",
            "check_in": None,
            "check_out": f"{departure.isoformat()}T11:00:00-07:00",
        }
    )
    return HospitableReservation.from_api(payload)


def _sensor(reservation: HospitableReservation) -> Any:
    """Build a reservation sensor over a fake coordinator."""
    coordinator = SimpleNamespace(data=[reservation], consecutive_failures=0)
    return HospitableReservationSensor(
        cast(Any, coordinator),
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: D3 occupancy degradation must warn once per field",
)
def test_repeated_reads_warn_once(caplog: pytest.LogCaptureFixture) -> None:
    """Repeated state and attribute reads warn once for one degraded field."""
    sensor = _sensor(_arrival_today_missing_checkin())
    with caplog.at_level(logging.WARNING):
        _ = sensor.native_value
        _ = sensor.native_value
        _ = sensor.extra_state_attributes
    warnings = [
        record for record in caplog.records if "res-degraded-001" in record.getMessage()
    ]
    assert len(warnings) == 1
