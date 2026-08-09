# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase integration setup tests."""

from __future__ import annotations


def test_setup_wires_only_properties_coordinator() -> None:
    """Assert US1 setup does not forward platforms."""
    import custom_components.hospitable as integration

    assert integration.VERSION == 1 and integration.MINOR_VERSION == 1
    assert integration.PLATFORMS == []
