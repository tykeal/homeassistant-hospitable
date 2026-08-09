# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase 403 classifier tests."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T026 403 classifier"
)
def test_403_classifier_defaults_to_forbidden() -> None:
    """Assert scope classification is narrow and non-reauth."""
    from custom_components.hospitable.api.client import (
        classify_403,  # type: ignore[import-not-found, import-untyped, unused-ignore]
    )
    from custom_components.hospitable.api.exceptions import (  # type: ignore[import-not-found, import-untyped, unused-ignore]
        HospitableForbiddenError,
        HospitableScopeError,
    )

    assert (
        classify_403({"reason_phrase": "Invalid scope(s) provided."})
        is HospitableScopeError
    )
    assert classify_403({"message": "SCOPE missing"}) is HospitableScopeError
    assert classify_403({"error": "nope"}) is HospitableForbiddenError
    assert classify_403(None) is HospitableForbiddenError
