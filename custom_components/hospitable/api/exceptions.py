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
    ) -> None:
        """Initialize the error with status, endpoint, and redacted body."""
        super().__init__(message)
        self.status = status
        self.endpoint = endpoint
        self.body = body


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
    ) -> None:
        """Initialize the rate-limit error."""
        super().__init__(message, status=status, endpoint=endpoint, body=body)
        self.retry_after = retry_after


class HospitableConnectionError(HospitableError):
    """Transport or server-side connection failure."""


class HospitableResponseError(HospitableError):
    """Malformed response or envelope failure."""


class HospitableIncludeMissingError(HospitableResponseError):
    """Raised when an include post-condition is not honored."""
