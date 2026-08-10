# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Allowlist diagnostics helpers for Hospitable."""

from __future__ import annotations

from typing import Any

ALLOWED_TOP_LEVEL = {
    "version",
    "minor_version",
    "namespace_source",
    "options",
    "coordinators",
    "counts",
}


def redact_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    """Return an allowlisted diagnostics payload without private values."""
    return {key: value for key, value in payload.items() if key in ALLOWED_TOP_LEVEL}
