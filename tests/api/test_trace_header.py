# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Tests for trace header capture (D4, FR-017 to FR-022).

This module covers Deliverable 4 of spec 004: capturing the
``x-hospitable-trace`` response header on API errors and surfacing
the most recent trace ID in the diagnostics payload.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from tests.helpers import load_fixture

# ---- T038: HospitableError accepts trace_id kwarg ----


def test_error_accepts_trace_id() -> None:
    """``HospitableError`` accepts a ``trace_id`` keyword argument."""
    from custom_components.hospitable.api.exceptions import (
        HospitableError,
    )

    exc = HospitableError("test", trace_id="abc123")
    assert exc.trace_id == "abc123"


# ---- T039: _raise_for_status passes trace_id from header ----


async def test_raise_for_status_captures_trace_header(
    respx_router: respx.Router,
    mock_httpx_client: httpx.AsyncClient,
    api_client_factory: Any,
    synthetic_token: str,
) -> None:
    """An error response's ``x-hospitable-trace`` is on the exception."""
    from custom_components.hospitable.api.const import BASE_URL
    from custom_components.hospitable.api.exceptions import (
        HospitableError,
    )

    respx_router.get(f"{BASE_URL}/user").mock(
        return_value=httpx.Response(
            500,
            json={"error": "server error"},
            headers={"x-hospitable-trace": "trace-xyz"},
        )
    )
    client = api_client_factory(mock_httpx_client, synthetic_token)
    with pytest.raises(HospitableError) as exc_info:
        await client.get_user()
    assert getattr(exc_info.value, "trace_id", None) == "trace-xyz"


# ---- T040: coordinator last_trace_id from success ----


async def test_coordinator_stores_trace_on_success(
    hass: Any,
    respx_router: respx.Router,
    mock_httpx_client: httpx.AsyncClient,
    api_client_factory: Any,
    synthetic_token: str,
) -> None:
    """A successful poll stores the trace header on the coordinator."""
    from custom_components.hospitable.api.const import BASE_URL
    from custom_components.hospitable.coordinator import (
        HospitablePropertiesCoordinator,
    )

    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(
                200,
                json=load_fixture("properties_page1.json"),
                headers={"x-hospitable-trace": "trace-abc"},
            ),
            httpx.Response(
                200,
                json=load_fixture("properties_page2.json"),
                headers={"x-hospitable-trace": "trace-abc"},
            ),
        ]
    )
    client = api_client_factory(mock_httpx_client, synthetic_token)
    coordinator = HospitablePropertiesCoordinator(hass, client)
    await coordinator.async_refresh()
    assert getattr(coordinator, "last_trace_id", "MISSING") == "trace-abc"


# ---- T041: absent header -> last_trace_id is None ----


async def test_coordinator_trace_none_when_absent(
    hass: Any,
    respx_router: respx.Router,
    mock_httpx_client: httpx.AsyncClient,
    api_client_factory: Any,
    synthetic_token: str,
) -> None:
    """A poll without the trace header stores ``None``."""
    from custom_components.hospitable.api.const import BASE_URL
    from custom_components.hospitable.coordinator import (
        HospitablePropertiesCoordinator,
    )

    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(
                200,
                json=load_fixture("properties_page1.json"),
            ),
            httpx.Response(
                200,
                json=load_fixture("properties_page2.json"),
            ),
        ]
    )
    client = api_client_factory(mock_httpx_client, synthetic_token)
    coordinator = HospitablePropertiesCoordinator(hass, client)
    await coordinator.async_refresh()
    assert getattr(coordinator, "last_trace_id", "MISSING") is None


# ---- T042: diagnostics includes last_trace_id ----


async def test_diagnostics_includes_trace_id(
    hass: Any,
    respx_router: respx.Router,
    mock_httpx_client: httpx.AsyncClient,
    api_client_factory: Any,
    synthetic_token: str,
) -> None:
    """The diagnostics payload includes ``last_trace_id``."""
    from custom_components.hospitable.api.const import BASE_URL
    from custom_components.hospitable.coordinator import (
        HospitablePropertiesCoordinator,
    )
    from custom_components.hospitable.diagnostics import (
        _coordinator_section,
    )

    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(
                200,
                json=load_fixture("properties_page1.json"),
                headers={"x-hospitable-trace": "trace-diag"},
            ),
            httpx.Response(
                200,
                json=load_fixture("properties_page2.json"),
                headers={"x-hospitable-trace": "trace-diag"},
            ),
        ]
    )
    client = api_client_factory(mock_httpx_client, synthetic_token)
    coordinator = HospitablePropertiesCoordinator(hass, client)
    await coordinator.async_refresh()
    section = _coordinator_section("properties", coordinator)
    assert section.get("last_trace_id") == "trace-diag"


# ---- T043: trace_id passes through redactor unredacted (GREEN) ----


def test_trace_id_survives_redactor() -> None:
    """The trace ID passes through diagnostics redaction unchanged."""
    from custom_components.hospitable.diagnostics import (
        redact_diagnostics,
    )

    payload = {
        "coordinators": {
            "properties": {
                "last_trace_id": "trace-survive",
                "last_update_success": True,
            }
        }
    }
    result = redact_diagnostics(payload)
    props = result["coordinators"]["properties"]
    assert props["last_trace_id"] == "trace-survive"


# ---- T044: diagnostics entrypoint importable (GREEN, no xfail) ----


def test_diagnostics_entrypoint_importable() -> None:
    """The diagnostics entrypoint is importable and callable (FR-022)."""
    from custom_components.hospitable.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    assert callable(async_get_config_entry_diagnostics)
