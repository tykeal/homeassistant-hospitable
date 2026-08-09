# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase auth tests."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T025 auth"
)
async def test_token_provider_auth_header(synthetic_token: str) -> None:
    """Assert token providers add Authorization headers only."""
    from custom_components.hospitable.api.auth import (  # type: ignore[import-not-found, import-untyped, unused-ignore]
        StaticTokenProvider,
        build_auth_headers,
    )

    provider = StaticTokenProvider(synthetic_token)
    headers = await build_auth_headers(provider)
    assert headers["Authorization"] == "******"
    assert "token" not in str(headers).casefold()
