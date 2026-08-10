# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase exception hierarchy tests."""

from __future__ import annotations


def test_exception_hierarchy() -> None:
    """Assert typed Hospitable exceptions carry context."""
    from custom_components.hospitable.api.exceptions import (
        HospitableAuthError,
        HospitableConnectionError,
        HospitableError,
        HospitableForbiddenError,
        HospitableIncludeMissingError,
        HospitableNotFoundError,
        HospitableRateLimitError,
        HospitableResponseError,
        HospitableScopeError,
    )

    err = HospitableRateLimitError(
        "limited", status=429, endpoint="/user", body="secret", retry_after=3.0
    )
    assert isinstance(err, HospitableError)
    assert isinstance(
        HospitableAuthError("x", status=401, endpoint="/user"), HospitableError
    )
    assert isinstance(
        HospitableScopeError("x", status=403, endpoint="/user"), HospitableError
    )
    assert isinstance(
        HospitableForbiddenError("x", status=403, endpoint="/user"), HospitableError
    )
    assert isinstance(
        HospitableNotFoundError("x", status=404, endpoint="/user"), HospitableError
    )
    assert isinstance(HospitableConnectionError("x", endpoint="/user"), HospitableError)
    assert issubclass(HospitableIncludeMissingError, HospitableResponseError)
    assert err.status == 429 and err.endpoint == "/user" and err.retry_after == 3.0
