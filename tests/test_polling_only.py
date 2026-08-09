# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase polling-only tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError, strict=True, reason="TDD red phase: T045 polling only"
)
def test_polling_only_manifest_and_package() -> None:
    """Assert no webhook surface is registered."""
    from custom_components.hospitable.const import (
        DOMAIN,  # type: ignore[import-not-found, import-untyped, unused-ignore]
    )

    manifest = json.loads(Path(f"custom_components/{DOMAIN}/manifest.json").read_text())
    assert manifest["iot_class"] == "cloud_polling"
    assert "webhook" not in "\n".join(
        p.read_text() for p in Path(f"custom_components/{DOMAIN}").rglob("*.py")
    )
