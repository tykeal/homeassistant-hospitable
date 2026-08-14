# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for relative-day window override (D5, FR-023 to FR-032).

This module covers Deliverable 5 of spec 004: optional
``lookforward_days`` and ``lookbackward_days`` parameters on the
``get_reservations`` service action for per-call window overrides.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import httpx
import pytest
import respx
import voluptuous as vol
from freezegun import freeze_time
from homeassistant.core import HomeAssistant

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import DOMAIN
from tests.helpers import load_fixture

_FROZEN = "2025-06-15T12:00:00+00:00"
_FROZEN_DATE = date(2025, 6, 15)


async def _call(hass: HomeAssistant, data: dict[str, Any]) -> Any:
    """Call the get_reservations service.

    Args:
        hass: Home Assistant instance.
        data: Service call data.

    Returns:
        The service response payload.
    """
    return await hass.services.async_call(
        DOMAIN,
        "get_reservations",
        data,
        blocking=True,
        return_response=True,
    )


def _mock_reservations_route(
    router: respx.Router,
) -> respx.Route:
    """Register a reservations list response.

    Args:
        router: Active respx router.

    Returns:
        The registered route.
    """
    route = router.get(
        f"{BASE_URL}/reservations",
        params={"include": "guest,properties"},
    )
    route.mock(
        return_value=httpx.Response(
            200,
            json=load_fixture("reservations_page1.json"),
        )
    )
    return route


# ---- T053: lookforward_days accepted ----


async def test_lookforward_days_accepted_by_schema(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """The schema accepts lookforward_days (FR-023).

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    _mock_reservations_route(respx_router)
    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "get_reservations")
    result = await _call(
        hass,
        {
            "property_id": "prop-example-001",
            "lookforward_days": 400,
        },
    )
    assert result is not None


# ---- T054: lookbackward_days accepted ----


async def test_lookbackward_days_accepted_by_schema(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """The schema accepts lookbackward_days (FR-023, FR-025).

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    _mock_reservations_route(respx_router)
    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "get_reservations")
    result = await _call(
        hass,
        {
            "property_id": "prop-example-001",
            "lookbackward_days": 30,
        },
    )
    assert result is not None


# ---- T059: lookbackward_days=0 valid ----


async def test_lookbackward_zero_is_valid(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """lookbackward_days: 0 is a valid future-only search (FR-026).

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    _mock_reservations_route(respx_router)
    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "get_reservations")
    result = await _call(
        hass,
        {
            "property_id": "prop-example-001",
            "lookbackward_days": 0,
        },
    )
    assert result is not None


# ---- T060: backward default is fixed 7 ----


@freeze_time(_FROZEN)
async def test_backward_default_is_fixed_seven(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """Default backward reach is fixed 7 days, not config (FR-025).

    This is the key behavioural test for D5: the deliberate
    asymmetry where backward defaults to 7 while forward inherits
    the config lookahead_days.

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    captured: list[httpx.Request] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        """Capture the request and delegate to the original mock.

        Args:
            request: The captured request.

        Returns:
            A mock response.
        """
        captured.append(request)
        return httpx.Response(
            200,
            json=load_fixture("reservations_page1.json"),
        )

    await loaded_config_entry_factory(hass)

    # Replace the reservations route after setup so only the action
    # call is captured — the coordinator poll already happened.
    respx_router.get(f"{BASE_URL}/reservations").mock(side_effect=_capture)

    await _call(hass, {"property_id": "prop-example-001"})

    today = _FROZEN_DATE
    expected_start = today - timedelta(days=7)
    assert len(captured) > 0, "No reservations request captured"
    params = captured[-1].url.params
    start_date = params.get("start_date", "")
    assert start_date == expected_start.isoformat()


# ---- T061: docstring rewritten ----


async def test_docstring_no_longer_claims_same_window(
    hass: HomeAssistant,
) -> None:
    """The handler docstring no longer claims equivalence (FR-031).

    Args:
        hass: Home Assistant instance.
    """
    from custom_components.hospitable.actions.get_reservations import (
        async_handle_get_reservations,
    )

    doc = async_handle_get_reservations.__doc__ or ""
    assert "the service and the entities describe the same span" not in doc.lower()
    assert "matches the one the reservation coordinator" not in doc.lower()


# ---- T055: lookforward_days 1096 rejected (GREEN) ----


async def test_lookforward_above_ceiling_rejected(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """lookforward_days: 1096 is rejected by vol.Range (FR-027).

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    _mock_reservations_route(respx_router)
    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "get_reservations")
    with pytest.raises(vol.MultipleInvalid):
        await _call(
            hass,
            {
                "property_id": "prop-example-001",
                "lookforward_days": 1096,
            },
        )


# ---- T057: lookforward_days 0 rejected (GREEN) ----


async def test_lookforward_zero_rejected(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """lookforward_days: 0 is rejected by vol.Range (FR-027).

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    _mock_reservations_route(respx_router)
    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "get_reservations")
    with pytest.raises(vol.MultipleInvalid):
        await _call(
            hass,
            {
                "property_id": "prop-example-001",
                "lookforward_days": 0,
            },
        )


# ---- T056: lookbackward_days 366 rejected (GREEN) ----


async def test_lookbackward_above_ceiling_rejected(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """lookbackward_days: 366 is rejected by vol.Range (FR-026).

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    _mock_reservations_route(respx_router)
    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "get_reservations")
    with pytest.raises(vol.MultipleInvalid):
        await _call(
            hass,
            {
                "property_id": "prop-example-001",
                "lookbackward_days": 366,
            },
        )


# ---- T058: lookbackward_days -1 rejected (GREEN) ----


async def test_lookbackward_negative_rejected(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """lookbackward_days: -1 is rejected by vol.Range (FR-026).

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    _mock_reservations_route(respx_router)
    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "get_reservations")
    with pytest.raises(vol.MultipleInvalid):
        await _call(
            hass,
            {
                "property_id": "prop-example-001",
                "lookbackward_days": -1,
            },
        )


# ---- Boundary valid: lookforward 1 and 1095, lookbackward 365 ----


async def test_lookforward_boundary_one_valid(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """lookforward_days: 1 is the minimum valid value (FR-027).

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    _mock_reservations_route(respx_router)
    await loaded_config_entry_factory(hass)
    result = await _call(
        hass,
        {"property_id": "prop-example-001", "lookforward_days": 1},
    )
    assert result is not None


async def test_lookforward_boundary_ceiling_valid(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """lookforward_days: 1095 is the maximum valid value (FR-027).

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    _mock_reservations_route(respx_router)
    await loaded_config_entry_factory(hass)
    result = await _call(
        hass,
        {"property_id": "prop-example-001", "lookforward_days": 1095},
    )
    assert result is not None


async def test_lookbackward_boundary_ceiling_valid(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """lookbackward_days: 365 is the maximum valid value (FR-026).

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    _mock_reservations_route(respx_router)
    await loaded_config_entry_factory(hass)
    result = await _call(
        hass,
        {"property_id": "prop-example-001", "lookbackward_days": 365},
    )
    assert result is not None


# ---- E2E: actual upstream dates asserted ----


@freeze_time(_FROZEN)
async def test_lookforward_extends_upstream_window(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """lookforward_days: 400 sends end_date 400 days ahead (FR-023).

    This end-to-end test through real hass + respx asserts the ACTUAL
    dates sent upstream, not merely that the schema accepts the value.

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    captured: list[httpx.Request] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        """Capture the request parameters.

        Args:
            request: The captured request.

        Returns:
            A mock response.
        """
        captured.append(request)
        return httpx.Response(
            200,
            json=load_fixture("reservations_page1.json"),
        )

    await loaded_config_entry_factory(hass)
    respx_router.get(f"{BASE_URL}/reservations").mock(side_effect=_capture)

    await _call(
        hass,
        {
            "property_id": "prop-example-001",
            "lookforward_days": 400,
        },
    )

    today = _FROZEN_DATE
    expected_end = today + timedelta(days=400)
    expected_start = today - timedelta(days=7)
    assert len(captured) > 0, "No reservations request captured"
    params = captured[-1].url.params
    assert params.get("end_date") == expected_end.isoformat()
    assert params.get("start_date") == expected_start.isoformat()


@freeze_time(_FROZEN)
async def test_lookbackward_extends_upstream_window(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """lookbackward_days: 30 sends start_date 30 days ago (FR-025).

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    captured: list[httpx.Request] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        """Capture the request parameters.

        Args:
            request: The captured request.

        Returns:
            A mock response.
        """
        captured.append(request)
        return httpx.Response(
            200,
            json=load_fixture("reservations_page1.json"),
        )

    await loaded_config_entry_factory(hass)
    respx_router.get(f"{BASE_URL}/reservations").mock(side_effect=_capture)

    await _call(
        hass,
        {
            "property_id": "prop-example-001",
            "lookbackward_days": 30,
        },
    )

    today = _FROZEN_DATE
    expected_start = today - timedelta(days=30)
    assert len(captured) > 0, "No reservations request captured"
    params = captured[-1].url.params
    assert params.get("start_date") == expected_start.isoformat()


@freeze_time(_FROZEN)
async def test_forward_default_inherits_config_lookahead(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """Default forward reach inherits lookahead_days option (FR-024).

    The config entry sets lookahead_days=30, so end_date should be
    today + 30 when lookforward_days is omitted.

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Factory for loaded config entries.
    """
    captured: list[httpx.Request] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        """Capture the request parameters.

        Args:
            request: The captured request.

        Returns:
            A mock response.
        """
        captured.append(request)
        return httpx.Response(
            200,
            json=load_fixture("reservations_page1.json"),
        )

    await loaded_config_entry_factory(hass)
    respx_router.get(f"{BASE_URL}/reservations").mock(side_effect=_capture)

    await _call(hass, {"property_id": "prop-example-001"})

    today = _FROZEN_DATE
    # Config sets lookahead_days=30
    expected_end = today + timedelta(days=30)
    assert len(captured) > 0, "No reservations request captured"
    params = captured[-1].url.params
    assert params.get("end_date") == expected_end.isoformat()
