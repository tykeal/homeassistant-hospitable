# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T138 red phase: a 429 populates retry_after from the Retry-After header.

Found by contract-versus-implementation review. The exception hierarchy
documents ``HospitableRateLimitError`` as carrying ``retry_after``, and
``parse_retry_after`` plus its unit tests exist, but ``client.py`` never
reads the header or populates the field, so the value is unconditionally
``None`` in production. Absence of the header must be tolerated as
``None`` rather than treated as an error.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase T138: retry_after is never populated from the header",
)
async def test_rate_limit_populates_retry_after(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """A 429 carrying Retry-After exposes the parsed delay in seconds."""
    from custom_components.hospitable.api.const import BASE_URL, USER_PATH
    from custom_components.hospitable.api.exceptions import (
        HospitableRateLimitError,
    )

    client = api_client_factory(mock_httpx_client, synthetic_token)
    respx_router.get(f"{BASE_URL}{USER_PATH}").mock(
        return_value=httpx.Response(
            429,
            json={"message": "Too Many Requests"},
            headers={"Retry-After": "42"},
        )
    )

    with pytest.raises(HospitableRateLimitError) as exc_info:
        await client.get_user()

    assert exc_info.value.retry_after == 42.0


async def test_rate_limit_without_header_tolerates_absence(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """A 429 without Retry-After yields retry_after None, never an error."""
    from custom_components.hospitable.api.const import BASE_URL, USER_PATH
    from custom_components.hospitable.api.exceptions import (
        HospitableRateLimitError,
    )

    client = api_client_factory(mock_httpx_client, synthetic_token)
    respx_router.get(f"{BASE_URL}{USER_PATH}").mock(
        return_value=httpx.Response(429, json={"message": "Too Many Requests"})
    )

    with pytest.raises(HospitableRateLimitError) as exc_info:
        await client.get_user()

    assert exc_info.value.retry_after is None
