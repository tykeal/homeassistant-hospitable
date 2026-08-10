# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Credential provider abstractions for Hospitable requests."""

from __future__ import annotations

from typing import Protocol


class TokenProvider(Protocol):
    """Protocol for providers that can asynchronously return a token."""

    async def get_token(self) -> str:
        """Return an access token for the next request."""


class StaticTokenProvider:
    """Personal Access Token provider used by the first release."""

    def __init__(self, token: str) -> None:
        """Store the token in memory for request headers."""
        self._token = token

    async def get_token(self) -> str:
        """Return the configured Personal Access Token."""
        return self._token


async def build_auth_headers(provider: TokenProvider) -> dict[str, str]:
    """Build Authorization headers from a provider."""
    token = await provider.get_token()
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}
