# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase terminology tests."""

from __future__ import annotations

import json
from pathlib import Path


def test_user_strings_use_property_not_listing() -> None:
    """Assert user-facing strings prefer property terminology."""
    from custom_components.hospitable.const import (
        DOMAIN,
    )

    base = Path(f"custom_components/{DOMAIN}")
    payloads = [
        json.loads((base / "strings.json").read_text()),
        json.loads((base / "translations/en.json").read_text()),
    ]
    rendered = json.dumps(payloads).casefold().replace('"listings"', '""')
    assert "listing" not in rendered
