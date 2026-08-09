# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase pagination tests."""

from __future__ import annotations

from typing import Any

import httpx

from tests.helpers import load_fixture


async def test_pagination_constructs_https_pages(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """Assert pagination never follows upstream http links."""
    from custom_components.hospitable.api.const import (
        BASE_URL,
    )

    client = api_client_factory(mock_httpx_client, synthetic_token)
    respx_router.get("http://public.api.hospitable.com/v2/properties?page=2").mock(
        side_effect=AssertionError("followed http link")
    )
    respx_router.get(f"{BASE_URL}/properties").mock(
        side_effect=[
            httpx.Response(200, json=load_fixture("properties_page1.json")),
            httpx.Response(200, json=load_fixture("properties_page2.json")),
        ]
    )
    await client.get_properties()
