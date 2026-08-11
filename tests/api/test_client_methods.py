# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase client method tests."""

from __future__ import annotations

import inspect


def test_client_get_only_async_surface() -> None:
    """Assert client entry points are async and GET only."""
    from custom_components.hospitable.api.client import (
        HospitableApiClient,
    )

    assert inspect.iscoroutinefunction(HospitableApiClient.get_user)
    assert not any(
        name.startswith(("post_", "put_", "delete_", "patch_"))
        for name in dir(HospitableApiClient)
    )
    assert not any("channel" in name for name in dir(HospitableApiClient))
