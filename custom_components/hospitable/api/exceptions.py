# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Typed exceptions raised by the Hospitable API client."""

from __future__ import annotations


class HospitableError(Exception):
    """Base exception carrying sanitized API failure context."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        endpoint: str = "",
        body: str = "",
        trace_id: str | None = None,
    ) -> None:
        """Initialize the error with status, endpoint, and redacted body."""
        super().__init__(message)
        self.status = status
        self.endpoint = endpoint
        self.body = body
        self.trace_id = trace_id


class HospitableAuthError(HospitableError):
    """Authentication failure from HTTP 401."""


class HospitableScopeError(HospitableError):
    """Capability failure for a scope-related HTTP 403."""


class HospitableForbiddenError(HospitableError):
    """Non-scope HTTP 403 failure."""


class HospitableNotFoundError(HospitableError):
    """HTTP 404 failure."""


class HospitableRateLimitError(HospitableError):
    """HTTP 429 failure carrying a retry delay when supplied."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        status: int | None = 429,
        endpoint: str = "",
        body: str = "",
        trace_id: str | None = None,
    ) -> None:
        """Initialize the rate-limit error."""
        super().__init__(
            message,
            status=status,
            endpoint=endpoint,
            body=body,
            trace_id=trace_id,
        )
        self.retry_after = retry_after


class HospitableConnectionError(HospitableError):
    """Transport or server-side connection failure."""


class HospitableResponseError(HospitableError):
    """Malformed response or envelope failure."""


class HospitableIncludeMissingError(HospitableResponseError):
    """Raised when an include post-condition is not honored."""


class HospitableRequestValidationError(HospitableError):
    """Upstream rejected the request body with 400 or 422.

    Carries the parsed Laravel envelope so the caller can surface the
    per-field messages the user needs to fix the call.
    """

    def __init__(
        self,
        message: str,
        *,
        field_messages: list[str] | None = None,
        status: int | None = None,
        endpoint: str = "",
        trace_id: str | None = None,
    ) -> None:
        """Initialize with the per-field validation messages.

        Args:
            message: Sanitized summary message.
            field_messages: Per-field messages from the envelope.
            status: HTTP status that produced the error.
            endpoint: Endpoint path that was called.
            trace_id: Upstream trace correlation identifier.
        """
        super().__init__(
            message,
            status=status,
            endpoint=endpoint,
            trace_id=trace_id,
        )
        self.field_messages = list(field_messages or [])
