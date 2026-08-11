# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T126 regression guard: an unparsable 403 body lands on the non-scope branch.

This test asserts existing behavior of ``classify_403`` and the client
error path rather than new behavior, so under the Principle XII
Exemptions clause it carries no ``xfail`` marker: it is a regression
guard proving the fail-safe default is not silently regressed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from tests.helpers import load_fixture


def test_classify_403_defaults_to_forbidden() -> None:
    """Absent, empty, and non-scope bodies classify as forbidden, not scope."""
    from custom_components.hospitable.api.client import classify_403
    from custom_components.hospitable.api.exceptions import (
        HospitableForbiddenError,
        HospitableScopeError,
    )

    assert classify_403(None) is HospitableForbiddenError
    assert classify_403({}) is HospitableForbiddenError
    assert classify_403({"message": "Forbidden for this account."}) is (
        HospitableForbiddenError
    )
    assert classify_403(load_fixture("error_403_scope.json")) is HospitableScopeError


async def test_client_403_unparsable_body_raises_forbidden(
    respx_router: Any,
    mock_httpx_client: httpx.AsyncClient,
    api_client_factory: Callable[[httpx.AsyncClient, str], Any],
    synthetic_token: str,
) -> None:
    """A 403 with a non-JSON body raises the forbidden branch, not scope."""
    from custom_components.hospitable.api.const import BASE_URL
    from custom_components.hospitable.api.exceptions import (
        HospitableForbiddenError,
        HospitableScopeError,
    )

    respx_router.get(f"{BASE_URL}/user").mock(
        return_value=httpx.Response(403, text="not json")
    )
    client = api_client_factory(mock_httpx_client, synthetic_token)
    with pytest.raises(HospitableForbiddenError) as excinfo:
        await client.get_user()
    assert not isinstance(excinfo.value, HospitableScopeError)
