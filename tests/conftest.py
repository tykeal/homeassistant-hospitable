# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Pytest fixtures for Hospitable integration tests."""

from __future__ import annotations

import importlib
import sys
from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable Home Assistant custom integration loading for every test."""
    module = sys.modules.get("custom_components")
    if module is not None and hasattr(module, "__path__"):
        local_path = str(Path.cwd() / "custom_components")
        if local_path not in module.__path__:
            module.__path__.append(local_path)


@pytest.fixture
async def respx_router() -> AsyncIterator[respx.Router]:
    """Provide a respx router for mocked Hospitable HTTP calls.

    Yields:
        The active respx mock router.
    """
    async with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
async def mock_httpx_client() -> AsyncIterator[httpx.AsyncClient]:
    """Provide an async httpx client for API tests.

    Yields:
        An async HTTP client scoped to the test.
    """
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def synthetic_token() -> str:
    """Return a synthetic token value that is never a real credential."""
    return "hp_test_synthetic_token_000000000000000000000000"


@pytest.fixture
def api_client_factory() -> Callable[[httpx.AsyncClient, str], Any]:
    """Return a factory that imports the API client only when called."""

    def _factory(http_client: httpx.AsyncClient, token: str) -> Any:
        """Build a Hospitable API client from an HTTP client and token."""
        auth_module = importlib.import_module("custom_components.hospitable.api.auth")
        client_module = importlib.import_module(
            "custom_components.hospitable.api.client"
        )
        return client_module.HospitableApiClient(
            auth_module.StaticTokenProvider(token), http_client
        )

    return _factory


@pytest.fixture
def model_factory() -> Callable[[str, dict[str, Any]], Any]:
    """Return a factory that imports model classes only when called."""

    def _factory(name: str, payload: dict[str, Any]) -> Any:
        """Build a model instance by class name from an API payload."""
        models = importlib.import_module("custom_components.hospitable.api.models")
        model = getattr(models, name)
        return model.from_api(payload)

    return _factory


@pytest.fixture(autouse=True)
def reset_write_rate_limits() -> Iterator[None]:
    """Give every test a fresh write rate-limit budget.

    The tracker is a module-level singleton because the upstream budget
    is per token, not per config entry. Without this reset the budget
    would leak between tests and one test's sends would refuse the next
    test's.

    Yields:
        Control to the test.
    """
    from custom_components.hospitable.actions import rate_limit

    original = rate_limit.TRACKER
    rate_limit.TRACKER = rate_limit.RateLimitTracker()
    try:
        yield
    finally:
        rate_limit.TRACKER = original
