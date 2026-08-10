# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Redaction helpers for Hospitable logs and exceptions."""

from __future__ import annotations

import json
import re
from typing import Any

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.I)
PHONE_RE = re.compile(r"\+?1?\d{10,}")
SENSITIVE_KEYS = ("token", "authorization", "secret", "password", "email", "phone")


def _scrub(value: Any) -> Any:
    """Recursively replace sensitive values in mappings."""
    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if any(part in key.casefold() for part in SENSITIVE_KEYS)
                else _scrub(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def redact(value: Any) -> str:
    """Return a string with credentials and personal fields removed."""
    text = json.dumps(_scrub(value), default=str, sort_keys=True)
    text = BEARER_RE.sub("Bearer [REDACTED]", text)
    text = EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    return PHONE_RE.sub("[REDACTED_PHONE]", text)


def contains_private_data(text: str, needles: list[str]) -> bool:
    """Return whether any non-empty private value appears in text."""
    return any(needle and needle in text for needle in needles)
