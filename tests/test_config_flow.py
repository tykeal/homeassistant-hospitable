# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase config flow tests."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T041 config flow"
)
def test_config_flow_schema_and_defaults() -> None:
    """Assert config flow exposes required steps and defaults."""
    from custom_components.hospitable.config_flow import (  # type: ignore[import-not-found, import-untyped, unused-ignore]
        DEFAULT_OPTIONS,
        HospitableConfigFlow,
    )

    assert {"user", "properties", "reauth_confirm"}.issubset(
        HospitableConfigFlow.supported_steps
    )
    assert DEFAULT_OPTIONS["reservation_interval_minutes"] == 5
