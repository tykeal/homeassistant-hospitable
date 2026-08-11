# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T106 (FR-023): options help text documents the request trade-off.

The user-facing help text on the options step must document both that a
wider window increases upstream requests and that a shorter lookback can
hide an in-progress long stay and make an occupied property report no
reservation. Both the source strings and the shipped English
translation must carry the full warning.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _init_description(relative_path: str) -> str:
    """Return the options ``init`` step description from a strings file."""
    data = json.loads(Path(relative_path).read_text(encoding="utf-8"))
    return str(data["options"]["step"]["init"]["description"])


def _assert_documents_tradeoff(description: str) -> None:
    """Assert the description names both sides of the request trade-off."""
    lowered = description.lower()
    # Widening the window increases upstream requests.
    assert "request" in lowered
    assert "wider" in lowered or "widen" in lowered or "increase" in lowered
    # Narrowing the lookback hides in-progress long stays ...
    assert "lookback" in lowered
    assert "in-progress" in lowered or "in progress" in lowered
    # ... and makes an occupied property report no reservation.
    assert "occupied" in lowered
    assert "no reservation" in lowered


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T114 help text omits the occupied/no-reservation clause",
)
def test_strings_help_text_documents_tradeoff() -> None:
    """strings.json documents the window and lookback request trade-off."""
    _assert_documents_tradeoff(
        _init_description("custom_components/hospitable/strings.json")
    )


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T114 English translation omits the full warning",
)
def test_translation_help_text_documents_tradeoff() -> None:
    """translations/en.json documents the same request trade-off."""
    _assert_documents_tradeoff(
        _init_description("custom_components/hospitable/translations/en.json")
    )
