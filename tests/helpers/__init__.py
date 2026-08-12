# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Helpers shared by Hospitable integration tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx

# ``tests/helpers`` is a PACKAGE, so ``__file__`` sits one level deeper
# than the ``tests/`` root that holds ``fixtures/``.
FIXTURES = Path(__file__).parent.parent / "fixtures"


def load_fixture(name: str) -> Any:
    """Load a JSON fixture by filename from ``tests/fixtures``.

    Args:
        name: Fixture filename to load.

    Returns:
        Parsed JSON fixture content.
    """
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def paginator_envelope(
    data: list[dict[str, Any]],
    *,
    page: int = 1,
    per_page: int = 100,
    last_page: int = 1,
    path: str = "http://public.api.hospitable.com/v2/properties",
) -> dict[str, Any]:
    """Build a Laravel-style paginator envelope.

    Args:
        data: Page items.
        page: Current page number.
        per_page: Requested page size.
        last_page: Final page number.
        path: Upstream path value to include in metadata.

    Returns:
        A paginator payload matching Hospitable list endpoints.
    """
    return {
        "data": data,
        "links": [
            {"url": f"{path}?page={page}", "label": str(page), "active": True},
        ],
        "meta": {
            "current_page": page,
            "from": 1,
            "last_page": last_page,
            "path": path,
            "per_page": per_page,
            "to": len(data),
            "total": len(data),
        },
    }


def assert_query_value(request: httpx.Request, key: str, value: str) -> None:
    """Assert a captured request includes an expected query value.

    Args:
        request: Request captured by respx.
        key: Query parameter key to inspect.
        value: Expected query parameter value.

    Raises:
        AssertionError: If the key or value is absent.
    """
    query = parse_qs(request.url.query.decode())
    assert value in query.get(key, [])
