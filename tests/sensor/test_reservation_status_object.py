# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Regression tests pinning the live ``reservation_status`` object shape.

The live Hospitable API returns ``reservation_status.current`` as an
object ``{category, sub_category}``, not the bare string that every
fixture and the model once assumed. Because the fixtures and the code
agreed with each other and were both wrong, the stringified object sent
every reservation sensor to ``unknown`` in production and let cancelled
and declined stays leak through ``is_forthcoming``. These tests guard
the confirmed object shape end to end: the model reads ``current`` as an
object and fails loudly on a malformed one, the sensor surfaces
``status_sub_category``, occupancy tolerates a naive instant, and the
enum sensor reports the derived state rather than ``unknown``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.api.exceptions import HospitableResponseError
from custom_components.hospitable.api.models import HospitableReservation
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from custom_components.hospitable.entity import build_unique_id
from custom_components.hospitable.services.occupancy import classify_occupancy
from custom_components.hospitable.services.selection import is_forthcoming
from tests.helpers import load_fixture

_ZONE = timezone(timedelta(hours=-7))


def _object_status(category: str, sub_category: str | None = None) -> dict[str, Any]:
    """Return a live-shaped ``reservation_status`` object."""
    return {
        "current": {"category": category, "sub_category": sub_category},
        "history": [
            {
                "category": "request",
                "sub_category": "request to book",
                "changed_at": "2026-06-09T21:26:54+00:00",
            }
        ],
    }


def _reservation_payload(
    reservation_id: str,
    property_id: str,
    *,
    arrival_offset: int,
    departure_offset: int,
    status: dict[str, Any],
) -> dict[str, Any]:
    """Build a reservation payload carrying the live object status shape."""
    base = datetime.now(_ZONE).date()
    arrival = base + timedelta(days=arrival_offset)
    departure = base + timedelta(days=departure_offset)
    payload = dict(load_fixture("reservation_accepted.json")["data"][0])
    payload.update(
        {
            "id": reservation_id,
            "properties": [{"id": property_id}],
            "arrival_date": f"{arrival.isoformat()}T00:00:00-07:00",
            "departure_date": f"{departure.isoformat()}T00:00:00-07:00",
            "check_in": f"{arrival.isoformat()}T16:00:00-07:00",
            "check_out": f"{departure.isoformat()}T11:00:00-07:00",
            "reservation_status": status,
        }
    )
    return payload


def test_model_reads_category_from_object() -> None:
    """The category is read from ``current['category']``, not stringified."""
    payload = _reservation_payload(
        "res-obj-1",
        "prop-example-001",
        arrival_offset=1,
        departure_offset=3,
        status=_object_status("accepted"),
    )
    reservation = HospitableReservation.from_api(payload)
    assert reservation.status_category == "accepted"


def test_model_surfaces_sub_category() -> None:
    """A declined stay carries its ``declined`` sub_category on the model."""
    payload = _reservation_payload(
        "res-obj-2",
        "prop-example-001",
        arrival_offset=1,
        departure_offset=3,
        status=_object_status("not accepted", "declined"),
    )
    reservation = HospitableReservation.from_api(payload)
    assert reservation.status_sub_category == "declined"


def test_model_raises_on_malformed_current() -> None:
    """An unexpected ``current`` shape fails loudly, never stringifies."""
    malformed_shapes: list[Any] = [
        {"history": []},
        {"current": "accepted", "history": []},
        {"current": {"sub_category": "declined"}, "history": []},
        {"current": {"category": None, "sub_category": None}, "history": []},
        {"current": {"category": "", "sub_category": None}, "history": []},
        {"current": None, "history": []},
    ]
    for shape in malformed_shapes:
        payload = _reservation_payload(
            "res-obj-3",
            "prop-example-001",
            arrival_offset=1,
            departure_offset=3,
            status={},
        )
        payload["reservation_status"] = shape
        raised = False
        try:
            HospitableReservation.from_api(payload)
        except HospitableResponseError:
            raised = True
        assert raised, f"expected HospitableResponseError for {shape!r}"


def test_cancelled_excluded_by_is_forthcoming() -> None:
    """A cancelled future stay is excluded by ``is_forthcoming``."""
    payload = _reservation_payload(
        "res-obj-4",
        "prop-example-001",
        arrival_offset=5,
        departure_offset=7,
        status=_object_status("cancelled"),
    )
    reservation = HospitableReservation.from_api(payload)
    now = datetime.now(UTC)
    assert is_forthcoming(reservation, now) is False


def test_sensor_surfaces_sub_category_attribute() -> None:
    """The reservation sensor exposes ``status_sub_category`` as an attribute."""
    from types import SimpleNamespace
    from typing import cast

    from custom_components.hospitable.sensor.reservation import (
        HospitableReservationSensor,
    )

    payload = _reservation_payload(
        "res-obj-sub",
        "prop-example-001",
        arrival_offset=1,
        departure_offset=3,
        status=_object_status("not accepted", "declined"),
    )
    reservation = HospitableReservation.from_api(payload)
    coordinator = SimpleNamespace(data=[reservation], consecutive_failures=0)
    sensor = HospitableReservationSensor(
        cast(Any, coordinator),
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )
    assert sensor.extra_state_attributes["status_sub_category"] == "declined"


def test_occupancy_tolerates_naive_checkin() -> None:
    """A naive scheduled check-in is treated as absent, never raising."""
    base = datetime.now(_ZONE).date()
    payload = dict(load_fixture("reservation_accepted.json")["data"][0])
    departure = (base + timedelta(days=2)).isoformat()
    payload.update(
        {
            "id": "res-obj-5",
            "properties": [{"id": "prop-example-001"}],
            "arrival_date": f"{base.isoformat()}T00:00:00-07:00",
            "departure_date": f"{departure}T00:00:00-07:00",
            "check_in": f"{base.isoformat()}T16:00:00",
            "check_out": f"{departure}T11:00:00",
            "reservation_status": _object_status("accepted"),
        }
    )
    reservation = HospitableReservation.from_api(payload)
    now = datetime.now(UTC)
    result = classify_occupancy(reservation, now)
    assert result.state in {
        "awaiting_checkin",
        "occupied",
        "checked_out",
        "unknown",
    }


def _reservations_envelope(reservations: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap reservation payloads in a single-page list envelope."""
    return {
        "data": reservations,
        "meta": {
            "current_page": 1,
            "last_page": 1,
            "path": "http://public.api.hospitable.com/v2/reservations",
            "per_page": 100,
            "total": len(reservations),
        },
    }


async def test_sensor_reports_occupied_for_object_shape(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """An occupied stay with the live object shape reports ``occupied``."""
    from custom_components.hospitable.api.const import BASE_URL

    today = datetime.now(_ZONE).date()
    payload = _reservation_payload(
        "res-e2e-obj",
        "prop-example-001",
        arrival_offset=-2,
        departure_offset=2,
        status=_object_status("accepted"),
    )
    arrival = (today - timedelta(days=2)).isoformat()
    departure = (today + timedelta(days=2)).isoformat()
    payload["arrival_date"] = f"{arrival}T00:00:00-07:00"
    payload["departure_date"] = f"{departure}T00:00:00-07:00"
    payload["check_in"] = f"{arrival}T16:00:00-07:00"
    payload["check_out"] = f"{departure}T11:00:00-07:00"

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: synthetic_token,
            CONF_ACCOUNT_NAMESPACE: "acct-example-0001",
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={CONF_SELECTED_PROPERTIES: ["prop-example-001"]},
        unique_id="acct-example-0001",
    )
    entry.add_to_hass(hass)
    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(200, json=load_fixture("properties_page1.json")),
            httpx.Response(200, json=load_fixture("properties_page2.json")),
        ]
    )
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=_reservations_envelope([payload]))
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    entity_registry = er.async_get(hass)
    unique_id = build_unique_id(
        "acct-example-0001", "prop-example-001", "reservation_status"
    )
    entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id is not None
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "occupied"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
