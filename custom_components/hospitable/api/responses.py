# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Response envelope validators for Hospitable payloads."""

from __future__ import annotations

from typing import Any

from custom_components.hospitable.api.exceptions import (
    HospitableIncludeMissingError,
    HospitableResponseError,
)


def validate_list_envelope(
    payload: dict[str, Any], *, expected_page: int
) -> list[dict[str, Any]]:
    """Validate a Laravel-style list envelope and return its items."""
    data = payload.get("data")
    meta = payload.get("meta")
    if not isinstance(data, list) or not isinstance(meta, dict):
        raise HospitableResponseError("Response envelope is malformed")
    if meta.get("current_page") != expected_page:
        raise HospitableResponseError("Response page did not match request")
    return [item for item in data if isinstance(item, dict)]


def assert_include(items: list[dict[str, Any]], key: str, *, endpoint: str) -> None:
    """Assert each item includes the requested expansion key."""
    if any(key not in item for item in items):
        raise HospitableIncludeMissingError(f"Missing include {key}", endpoint=endpoint)
