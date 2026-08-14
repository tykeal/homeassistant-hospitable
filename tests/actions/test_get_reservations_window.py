# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for relative-day window override (D5, FR-023 to FR-032).

This module covers Deliverable 5 of spec 004: optional
``lookforward_days`` and ``lookbackward_days`` parameters on the
``get_reservations`` service action for per-call window overrides.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import httpx
import pytest
import respx
import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import DOMAIN
from tests.helpers import load_fixture


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


# ---- RED PHASE: T053 ----


@pytest.mark.xfail(
    raises=vol.MultipleInvalid,
    reason=("TDD red phase: T053 — schema rejects unknown lookforward_days key"),
    strict=True,
)
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
    await _call(
        hass,
        {
            "property_id": "prop-example-001",
            "lookforward_days": 400,
        },
    )


# ---- RED PHASE: T054 ----


@pytest.mark.xfail(
    raises=vol.MultipleInvalid,
    reason=("TDD red phase: T054 — schema rejects unknown lookbackward_days key"),
    strict=True,
)
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
    await _call(
        hass,
        {
            "property_id": "prop-example-001",
            "lookbackward_days": 30,
        },
    )


# ---- RED PHASE: T059 ----


@pytest.mark.xfail(
    raises=vol.MultipleInvalid,
    reason=(
        "TDD red phase: T059 — schema rejects unknown "
        "lookbackward_days key before range is checkable"
    ),
    strict=True,
)
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


# ---- RED PHASE: T060 ----


@pytest.mark.xfail(
    raises=AssertionError,
    reason=(
        "TDD red phase: T060 — backward defaults to config "
        "lookback_days (90), not the new fixed 7"
    ),
    strict=True,
)
async def test_backward_default_is_fixed_seven(
    hass: HomeAssistant,
    respx_router: respx.Router,
    loaded_config_entry_factory: Any,
) -> None:
    """Default backward reach is fixed 7 days, not config (FR-025).

    This is the key behavioural red test for D5: the deliberate
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

    today = dt_util.utcnow().date()
    expected_start = today - timedelta(days=7)
    assert len(captured) > 0, "No reservations request captured"
    params = captured[-1].url.params
    start_date = params.get("start_date", "")
    assert start_date == expected_start.isoformat()


# ---- RED PHASE: T061 ----


@pytest.mark.xfail(
    raises=AssertionError,
    reason=(
        "TDD red phase: T061 — docstring still claims "
        "service and entities describe the same span of time"
    ),
    strict=True,
)
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
