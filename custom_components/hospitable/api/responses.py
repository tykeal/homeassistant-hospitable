# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Response envelope validators for Hospitable payloads."""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class ErrorEnvelope:
    """A parsed Laravel-style error body.

    The same shape is returned by a ``/tasks`` 400, a message send 422,
    and a 429, so one parser serves all three. ``errors`` is absent on
    the observed 429 body, hence the tolerant default.
    """

    status_code: int | None
    reason_phrase: str | None
    errors: dict[str, list[str]]

    def field_messages(self) -> list[str]:
        """Return every per-field message, flattened.

        Returns:
            Each validation message, in field order.
        """
        return [message for messages in self.errors.values() for message in messages]


def parse_error_envelope(payload: Any) -> ErrorEnvelope:
    """Parse a Laravel-style error envelope.

    Args:
        payload: Decoded response body, of any shape.

    Returns:
        The parsed envelope. A non-mapping body, or one with no
        ``errors`` key, yields empty errors rather than raising.
    """
    if not isinstance(payload, dict):
        return ErrorEnvelope(status_code=None, reason_phrase=None, errors={})
    raw_status = payload.get("status_code")
    raw_reason = payload.get("reason_phrase") or payload.get("message")
    raw_errors = payload.get("errors")
    errors: dict[str, list[str]] = {}
    if isinstance(raw_errors, dict):
        for field, messages in raw_errors.items():
            if isinstance(messages, list):
                errors[str(field)] = [str(message) for message in messages]
            elif messages is not None:
                errors[str(field)] = [str(messages)]
    return ErrorEnvelope(
        status_code=int(raw_status) if isinstance(raw_status, int) else None,
        reason_phrase=str(raw_reason) if raw_reason is not None else None,
        errors=errors,
    )
