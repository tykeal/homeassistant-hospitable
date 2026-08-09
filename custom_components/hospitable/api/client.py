# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Async GET-only client for Hospitable Public API requests."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from custom_components.hospitable.api.auth import TokenProvider, build_auth_headers
from custom_components.hospitable.api.const import (
    BASE_URL,
    PER_PAGE_MAX,
    PROPERTIES_PATH,
    USER_PATH,
)
from custom_components.hospitable.api.exceptions import (
    HospitableAuthError,
    HospitableConnectionError,
    HospitableForbiddenError,
    HospitableNotFoundError,
    HospitableRateLimitError,
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
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._raise_for_status(exc.response, path)
        data = response.json()
        if not isinstance(data, dict):
            return {}
        return data

    def _raise_for_status(self, response: httpx.Response, path: str) -> None:
        """Translate HTTP failures into typed Hospitable errors."""
        body: dict[str, Any] | None
        try:
            parsed = response.json()
        except ValueError:
            parsed = None
        body = parsed if isinstance(parsed, dict) else None
        if response.status_code == 401:
            raise HospitableAuthError(
                "Hospitable token was rejected", status=401, endpoint=path
            )
        if response.status_code == 403:
            error_type = classify_403(body)
            raise error_type(
                "Hospitable request is forbidden", status=403, endpoint=path
            )
        if response.status_code == 404:
            raise HospitableNotFoundError(
                "Hospitable resource was not found", status=404, endpoint=path
            )
        if response.status_code == 429:
            raise HospitableRateLimitError(
                "Hospitable rate limit reached", endpoint=path
            )
        raise HospitableConnectionError(
            "Hospitable API request failed", status=response.status_code, endpoint=path
        )

    async def get_user(self) -> HospitableAccount:
        """Return the authenticated account identifier."""
        return HospitableAccount.from_api(await self._get(USER_PATH))

    async def get_properties(self) -> dict[str, HospitableProperty]:
        """Return all properties keyed by immutable property identifier."""
        page = 1
        properties: dict[str, HospitableProperty] = {}
        while True:
            payload = await self._get(
                PROPERTIES_PATH,
                params=build_properties_params(page=page, per_page=PER_PAGE_MAX),
            )
            items = validate_list_envelope(payload, expected_page=page)
            assert_include(items, "listings", endpoint=PROPERTIES_PATH)
            for item in items:
                model = HospitableProperty.from_api(item)
                properties[model.property_id] = model
            meta = payload.get("meta", {})
            last_page = meta.get("last_page", page) if isinstance(meta, dict) else page
            if page >= int(last_page):
                break
            page += 1
        return properties
