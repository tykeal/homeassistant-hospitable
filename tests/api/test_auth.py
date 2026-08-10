# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase auth tests."""

from __future__ import annotations


async def test_token_provider_auth_header(synthetic_token: str) -> None:
    """Assert token providers add Authorization headers only."""
    from custom_components.hospitable.api.auth import (
        StaticTokenProvider,
        build_auth_headers,
    )

    provider = StaticTokenProvider(synthetic_token)
    headers = await build_auth_headers(provider)
    assert headers["Authorization"].startswith("Bearer ")
    assert synthetic_token in headers["Authorization"]
