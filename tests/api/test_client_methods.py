# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase client method tests."""

from __future__ import annotations

import inspect

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T034 client methods"
)
def test_client_get_only_async_surface() -> None:
    """Assert client entry points are async and GET only."""
    from custom_components.hospitable.api.client import (
        HospitableApiClient,  # type: ignore[import-not-found, import-untyped, unused-ignore]
    )

    assert inspect.iscoroutinefunction(HospitableApiClient.get_user)
    assert not any(
        name.startswith(("post_", "put_", "delete_", "patch_"))
        for name in dir(HospitableApiClient)
    )
