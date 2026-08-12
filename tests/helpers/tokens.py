# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Token hashing helper mirroring the rate-limiter key (T017, FR-018).

Rate-limit accounting keys on the TOKEN, not the config entry, so two
entries holding the same personal access token share one budget. Tests
need the same key the tracker uses without reaching into private state.
The raw token is never logged or persisted by this helper.
"""

from __future__ import annotations

import hashlib


def token_key(token: str) -> str:
    """Return the SHA-256 hex digest the rate limiter keys on.

    Args:
        token: Raw personal access token.

    Returns:
        Hex digest used as the tracker key.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
