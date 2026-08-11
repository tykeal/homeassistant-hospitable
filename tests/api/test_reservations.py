# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Reservations API behavior tests."""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from tests.helpers import assert_query_value, load_fixture


def test_reservation_query_contract() -> None:
    """Assert reservations send required filters."""
    from custom_components.hospitable.api.reservations import (
        build_reservation_params,
        chunk_property_ids,
    )

    batches = list(chunk_property_ids([str(i) for i in range(101)]))
    assert [len(batch) for batch in batches] == [50, 50, 1]
    params = build_reservation_params(["p1"], date(2025, 1, 1), date(2025, 1, 2))
    assert params["properties[]"] == ["p1"]
    assert params["start_date"] == "2025-01-01"
    assert params["end_date"] == "2025-01-02"
    assert params["date_query"] == "checkin"
    assert params["include"] == "properties"
    assert set(params) == {
        "properties[]",
        "start_date",
        "end_date",
        "date_query",
        "include",
        "page",
        "per_page",
    }
    assert "date_type" not in params
    assert "filter_date_type" not in params
    assert "status[]" not in params


async def test_client_reservations_send_filters_and_refilter(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """Assert reservation requests send filters and locally enforce the window."""
    from custom_components.hospitable.api.const import BASE_URL

    client = api_client_factory(mock_httpx_client, synthetic_token)
    route = respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )

    reservations = await client.get_reservations(
        ["prop-example-001"], date(2025, 6, 14), date(2025, 6, 16)
    )

    request = route.calls.last.request
    assert_query_value(request, "properties[]", "prop-example-001")
    assert_query_value(request, "start_date", "2025-06-14")
    assert_query_value(request, "end_date", "2025-06-16")
    assert_query_value(request, "date_query", "checkin")
    assert_query_value(request, "include", "properties")
    query = request.url.query.decode()
    assert "include=guests" not in query
    assert "date_type=" not in query
    assert "filter_date_type=" not in query
    assert "status%5B%5D=" not in query
    assert {reservation.reservation_id for reservation in reservations} == {
        "res-example-accepted",
        "res-example-cancelled",
    }
