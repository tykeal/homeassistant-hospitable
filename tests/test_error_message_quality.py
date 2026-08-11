# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""T128 red phase: audit every user-facing error string for FR-064 quality."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_COMPONENT = Path("custom_components/hospitable")
_STRINGS = _COMPONENT / "strings.json"
_EN = _COMPONENT / "translations" / "en.json"

# Imperative guidance cues: a user-facing error must tell the user what to
# do, not merely what failed.
_ACTION_CUE = re.compile(
    r"\b("
    r"try again|adjust|increase|decrease|correct|select|generate|choose|"
    r"enter|check|update|re-?authenticate|regenerate|reconnect|remove|"
    r"contact|verify|confirm|add|use|review|replace|provide"
    r")\b",
    re.IGNORECASE,
)
# A bare HTTP status or an exception repr is never acceptable user text.
_BARE_CODE = re.compile(r"^\s*(HTTP\s*)?\d{3}\s*$", re.IGNORECASE)
_EXCEPTION_REPR = re.compile(r"[A-Za-z_]+Error\s*\(|Traceback|Exception\(")


def _load(path: Path) -> dict[str, Any]:
    """Load a translation JSON file relative to the repository root."""
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _actionable_strings(catalog: dict[str, Any]) -> dict[str, str]:
    """Collect every string that must state a cause and an action.

    Issue titles are short summaries whose action lives in the paired
    description, so only descriptions are held to the action bar. Success
    and informational aborts (for example ``reauth_successful``) are
    audited separately because they are not error text.
    """
    result: dict[str, str] = {}
    config = catalog.get("config", {})
    options = catalog.get("options", {})
    for key, value in config.get("error", {}).items():
        result[f"config.error.{key}"] = value
    for key, value in options.get("error", {}).items():
        result[f"options.error.{key}"] = value
    for key, issue in catalog.get("issues", {}).items():
        result[f"issues.{key}.description"] = issue["description"]
    return result


def _all_user_strings(catalog: dict[str, Any]) -> dict[str, str]:
    """Collect every user-facing error, abort, and issue string."""
    result = dict(_actionable_strings(catalog))
    for key, value in catalog.get("config", {}).get("abort", {}).items():
        result[f"config.abort.{key}"] = value
    for key, issue in catalog.get("issues", {}).items():
        result[f"issues.{key}.title"] = issue["title"]
    return result


def test_every_error_string_states_cause_and_action() -> None:
    """Each audited error string names a cause and an action, never a code."""
    strings = _load(_STRINGS)
    en = _load(_EN)

    # Repair issues surfaced by US6 must be present and described.
    issues = strings.get("issues", {})
    assert "forbidden_access" in issues
    assert "persistent_failure" in issues

    audited = _actionable_strings(strings)
    assert _actionable_strings(en) == audited

    # No user-facing string may be a bare status code or an exception repr.
    for key, value in _all_user_strings(strings).items():
        assert isinstance(value, str) and value.strip(), key
        assert not _BARE_CODE.match(value), key
        assert not _EXCEPTION_REPR.search(value), key
        assert len(value) >= 12, key

    # Error and repair-issue text must additionally prescribe an action.
    for key, value in audited.items():
        assert _ACTION_CUE.search(value), key
