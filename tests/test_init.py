# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase integration setup tests."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T040 setup"
)
def test_setup_wires_only_properties_coordinator() -> None:
    """Assert US1 setup does not forward platforms."""
    import custom_components.hospitable as integration  # type: ignore[import-not-found, import-untyped, unused-ignore]

    assert integration.VERSION == 1 and integration.MINOR_VERSION == 1
    assert integration.PLATFORMS == []
