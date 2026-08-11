# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase calendar API tests (T138).

The calendar route is strictly ``GET /properties/{id}/calendar`` with a
forward window expressed as ``start_date`` and ``end_date`` only. The
``listing_id`` parameter is silently discarded upstream and MUST NEVER be
sent. The response ``listing_id`` and ``provider`` are cosmetic listing
metadata describing an aggregate across sales channels, not a scope
selector, so parsing MUST NOT depend on them.
"""

from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from tests.helpers import load_fixture


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T143 api.calendar params builder not implemented",
)
def test_calendar_params_send_window_and_omit_listing_id() -> None:
    """The params builder sends only the window, never a listing id."""
    import importlib

    # ``import_module`` defers resolution to call time so the missing
    # module is an expected ``ModuleNotFoundError`` rather than a
    # collection error, and returns ``Any`` so no ``type: ignore`` is
    # needed while the module does not exist.
    calendar_module = importlib.import_module(
        "custom_components.hospitable.api.calendar"
    )
    build_calendar_params = calendar_module.build_calendar_params

    params = build_calendar_params(date(2026, 8, 11), date(2026, 8, 25))
    assert params["start_date"] == "2026-08-11"
    assert params["end_date"] == "2026-08-25"
    assert "listing_id" not in params
    assert set(params) == {"start_date", "end_date"}


@pytest.mark.xfail(
    raises=AttributeError,
    strict=True,
    reason="TDD red phase: T143 client.get_calendar not implemented",
)
async def test_client_calendar_sends_window_only(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """The client sends the forward window and never a listing id."""
    from custom_components.hospitable.api.const import BASE_URL

    client = api_client_factory(mock_httpx_client, synthetic_token)
    route = respx_router.get(f"{BASE_URL}/properties/prop-example-001/calendar").mock(
        return_value=httpx.Response(200, json=load_fixture("calendar_prop1.json"))
    )

    await client.get_calendar("prop-example-001", date(2026, 8, 11), date(2026, 8, 13))

    request = route.calls.last.request
    query = parse_qs(request.url.query.decode())
    assert query.get("start_date") == ["2026-08-11"]
    assert query.get("end_date") == ["2026-08-13"]
    assert "listing_id" not in query


@pytest.mark.xfail(
    raises=AttributeError,
    strict=True,
    reason="TDD red phase: T143 client.get_calendar not implemented",
)
async def test_client_calendar_ignores_cosmetic_response_metadata(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """Response ``listing_id`` and ``provider`` do not scope the parse.

    The same day data is returned even when the response reports a
    different cosmetic ``listing_id``/``provider``, proving parsing keys
    off the requested property id rather than the cosmetic metadata.
    """
    from custom_components.hospitable.api.const import BASE_URL

    payload = load_fixture("calendar_prop1.json")
    payload["data"]["listing_id"] = "some-other-cosmetic-listing"
    payload["data"]["provider"] = "booking-com"

    client = api_client_factory(mock_httpx_client, synthetic_token)
    respx_router.get(f"{BASE_URL}/properties/prop-example-001/calendar").mock(
        return_value=httpx.Response(200, json=payload)
    )

    calendar = await client.get_calendar(
        "prop-example-001", date(2026, 8, 11), date(2026, 8, 13)
    )

    assert calendar.property_id == "prop-example-001"
    assert len(calendar.days) == 3
