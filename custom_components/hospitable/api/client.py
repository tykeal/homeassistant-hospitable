# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Async GET-only client for Hospitable Public API requests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from custom_components.hospitable.api.auth import TokenProvider, build_auth_headers
from custom_components.hospitable.api.const import BASE_URL, PROPERTIES_PATH, USER_PATH
from custom_components.hospitable.api.exceptions import (
    HospitableForbiddenError,
    HospitableScopeError,
)
from custom_components.hospitable.api.models import (
    HospitableAccount,
    HospitableProperty,
)
from custom_components.hospitable.api.properties import build_properties_params
from custom_components.hospitable.api.responses import (
    assert_include,
    validate_list_envelope,
)

QueryValue = str | int | float | bool | None


def classify_403(
    body: dict[str, Any] | None,
) -> type[HospitableScopeError] | type[HospitableForbiddenError]:
    """Classify a 403 body into scope or ordinary forbidden errors."""
    if body:
        reason = str(
            body.get("reason_phrase") or body.get("message") or body.get("error") or ""
        )
        if "scope" in reason.casefold():
            return HospitableScopeError
    return HospitableForbiddenError


class HospitableApiClient:
    """Small async Hospitable client with a GET-only public surface."""

    def __init__(
        self,
        token_provider: TokenProvider,
        http_client: httpx.AsyncClient,
        *,
        base_url: str = BASE_URL,
    ) -> None:
        """Initialize the client with a token provider and HTTP client."""
        self._token_provider = token_provider
        self._http = http_client
        self._base_url = base_url.rstrip("/")

    async def _get(
        self, path: str, *, params: Mapping[str, QueryValue] | None = None
    ) -> dict[str, Any]:
        """Issue one authenticated GET request and return JSON."""
        response = await self._http.get(
            f"{self._base_url}{path}",
            params=params,
            headers=await build_auth_headers(self._token_provider),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return {}
        return data

    async def get_user(self) -> HospitableAccount:
        """Return the authenticated account identifier."""
        return HospitableAccount.from_api(await self._get(USER_PATH))

    async def get_properties(self) -> dict[str, HospitableProperty]:
        """Return all properties keyed by immutable property identifier."""
        payload = await self._get(
            PROPERTIES_PATH, params=build_properties_params(page=1, per_page=100)
        )
        items = validate_list_envelope(payload, expected_page=1)
        assert_include(items, "listings", endpoint=PROPERTIES_PATH)
        properties = [HospitableProperty.from_api(item) for item in items]
        return {item.property_id: item for item in properties}
