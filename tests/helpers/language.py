# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Assertion helper forbidding delivery claims in user-facing text.

HTTP 202 means the message was ACCEPTED for delivery. Delivery itself is
asynchronous and unconfirmed, so no service response, log line,
``services.yaml`` description, ``strings.json`` entry, or docstring may
claim the message was sent or delivered (FR-011, T018).
"""

from __future__ import annotations

import json
import re
from typing import Any

# ``sent`` and ``delivered`` are matched with word boundaries, so the
# identifier ``sent_reference_id`` does not trip the check: ``_`` is a
# word character. ``delivery`` alone is permitted because the one
# sanctioned phrasing is "accepted for delivery".
_DELIVERY_CLAIM_PATTERNS = (
    re.compile(r"\bsent\b", re.IGNORECASE),
    re.compile(r"\bdelivered\b", re.IGNORECASE),
    re.compile(r"\bdelivery\s+confirmed\b", re.IGNORECASE),
    re.compile(r"\bconfirmed\s+delivery\b", re.IGNORECASE),
    re.compile(r"\bsuccessfully\s+delivery\b", re.IGNORECASE),
)


def find_delivery_claims(text: str) -> list[str]:
    """Return every delivery claim found in ``text``.

    Args:
        text: Candidate user-facing text.

    Returns:
        The matched substrings, empty when the text makes no claim.
    """
    matches: list[str] = []
    for pattern in _DELIVERY_CLAIM_PATTERNS:
        matches.extend(match.group(0) for match in pattern.finditer(text))
    return matches


def assert_no_delivery_language(text: str) -> None:
    """Fail when ``text`` claims a message was sent or delivered.

    Args:
        text: Candidate user-facing text.

    Raises:
        AssertionError: If the text claims delivery.
    """
    matches = find_delivery_claims(text)
    assert not matches, f"Delivery claim in user-facing text: {matches!r}"


def assert_payload_has_no_delivery_language(payload: Any) -> None:
    """Fail when any string inside ``payload`` claims delivery.

    Args:
        payload: JSON-serialisable structure to audit.

    Raises:
        AssertionError: If any nested string claims delivery.
    """
    assert_no_delivery_language(json.dumps(payload, default=str))
