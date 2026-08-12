# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Two-dimensional client-side rate limiting for writes (FR-017 to FR-019).

The two budgets differ in evidential strength and are never conflated:

* per-(token, reservation), 2 per rolling 60s — CONFIRMED-BY-TEST. The
  messages endpoint returns ``x-ratelimit-limit`` and
  ``x-ratelimit-remaining``, and on 429 ``retry-after`` plus
  ``x-ratelimit-reset``.
* per-token, 50 per rolling 300s — DOCUMENTED-ONLY, never observed.

Accounting keys on a SHA-256 digest of the token, not on the config
entry: two entries holding the same token share one upstream budget. The
raw token is never stored or logged.

Server headers are authoritative over local counting in BOTH directions.
Local counting is a floor, not the authority.
"""

from __future__ import annotations

import hashlib
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from homeassistant.exceptions import ServiceValidationError

from custom_components.hospitable.api.retry import parse_retry_after

RESERVATION_LIMIT = 2
RESERVATION_WINDOW_SECONDS = 60
TOKEN_LIMIT = 50
TOKEN_WINDOW_SECONDS = 300


def token_key(token: str) -> str:
    """Return a stable non-reversible key for a token.

    Args:
        token: Raw personal access token.

    Returns:
        Hex SHA-256 digest of the token.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ServerHint:
    """A rate-limit state reported by the server."""

    remaining: int
    reset_at: float | None

    def applies_at(self, now: float) -> bool:
        """Return whether the hint is still current.

        Args:
            now: Current time on the tracker's clock.

        Returns:
            True while the hint has not expired.
        """
        return self.reset_at is None or now < self.reset_at


class RateLimitTracker:
    """Track both write budgets for every token and reservation."""

    def __init__(self, *, time_source: Callable[[], float] = time.time) -> None:
        """Initialize empty budgets.

        Args:
            time_source: Clock used for BOTH the rolling windows and the
                ``x-ratelimit-reset`` unix-epoch comparison, so the two
                cannot drift apart. Injectable for tests.
        """
        self._now = time_source
        self._reservation: dict[tuple[str, str], deque[float]] = {}
        self._token: dict[str, deque[float]] = {}
        self._hints: dict[tuple[str, str], ServerHint] = {}

    def bucket_keys(self) -> list[tuple[str, str] | str]:
        """Return every tracked bucket key.

        Returns:
            The per-reservation and per-token keys currently held. Used
            by tests to prove the raw token never appears in a key.
        """
        return [*self._reservation, *self._token]

    def check(self, token: str, reservation_uuid: str) -> None:
        """Refuse the call if either budget is exhausted.

        Args:
            token: Raw personal access token.
            reservation_uuid: Target reservation UUID.

        Raises:
            ServiceValidationError: A budget is exhausted. The message
                names which one and when it recovers.
        """
        now = self._now()
        key = (token_key(token), reservation_uuid)
        hint = self._hints.get(key)
        if hint is not None and not hint.applies_at(now):
            self._hints.pop(key, None)
            hint = None
        if hint is not None and hint.remaining <= 0 and hint.reset_at is None:
            # An exhausted hint with no reset time would never clear, so
            # it is discarded and local counting resumes as the floor.
            self._hints.pop(key, None)
            hint = None
        if hint is not None:
            if hint.remaining <= 0:
                raise ServiceValidationError(
                    "Hospitable reports no remaining message allowance for "
                    f"reservation {reservation_uuid}. "
                    f"{self._recovers_in(hint.reset_at, now)}"
                )
        else:
            stamps = self._trim(
                self._reservation.get(key), now, RESERVATION_WINDOW_SECONDS
            )
            if len(stamps) >= RESERVATION_LIMIT:
                raise ServiceValidationError(
                    f"The per-reservation limit of {RESERVATION_LIMIT} messages "
                    f"per {RESERVATION_WINDOW_SECONDS} seconds is reached for "
                    f"reservation {reservation_uuid}. "
                    f"{self._recovers_in(stamps[0] + RESERVATION_WINDOW_SECONDS, now)}"
                )
        token_stamps = self._trim(
            self._token.get(token_key(token)), now, TOKEN_WINDOW_SECONDS
        )
        if len(token_stamps) >= TOKEN_LIMIT:
            raise ServiceValidationError(
                f"The per-token limit of {TOKEN_LIMIT} requests per "
                f"{TOKEN_WINDOW_SECONDS} seconds is reached for this account. "
                f"{self._recovers_in(token_stamps[0] + TOKEN_WINDOW_SECONDS, now)}"
            )

    def record(self, token: str, reservation_uuid: str) -> None:
        """Charge one accepted send against both budgets.

        Only an acceptance is recorded; a refused or failed send
        consumes no budget.

        Args:
            token: Raw personal access token.
            reservation_uuid: Target reservation UUID.
        """
        now = self._now()
        digest = token_key(token)
        self._reservation.setdefault((digest, reservation_uuid), deque()).append(now)
        self._token.setdefault(digest, deque()).append(now)
        hint = self._hints.get((digest, reservation_uuid))
        if hint is not None:
            self._hints[(digest, reservation_uuid)] = ServerHint(
                remaining=hint.remaining - 1, reset_at=hint.reset_at
            )

    def apply_headers(
        self, token: str, reservation_uuid: str, headers: Mapping[str, str]
    ) -> None:
        """Adopt the server's authoritative rate-limit state.

        Args:
            token: Raw personal access token.
            reservation_uuid: Target reservation UUID.
            headers: Response headers, case-insensitive.
        """
        remaining = _as_int(_header(headers, "x-ratelimit-remaining"))
        if remaining is None:
            return
        reset = _as_int(_header(headers, "x-ratelimit-reset"))
        reset_at = float(reset) if reset is not None else None
        self._hints[(token_key(token), reservation_uuid)] = ServerHint(
            remaining=remaining, reset_at=reset_at
        )

    @staticmethod
    def retry_after(headers: Mapping[str, str]) -> float | None:
        """Return the backoff a 429 asks for.

        A 429 is retryable-with-backoff, not a hard failure: OQ-007
        leaves open whether reads and writes share one bucket, so the
        send path must survive being throttled by a poll. Parsing is
        delegated to the shared read-path parser so HTTP-date values and
        the ``MAX_BACKOFF`` cap behave identically on both paths.

        Args:
            headers: Response headers, case-insensitive.

        Returns:
            Seconds to wait, or None when the header is absent.
        """
        return parse_retry_after(_header(headers, "retry-after"))

    def _trim(
        self, stamps: deque[float] | None, now: float, window: float
    ) -> deque[float]:
        """Drop timestamps that have fallen out of a rolling window.

        Args:
            stamps: Recorded timestamps, or None.
            now: Current time.
            window: Window length in seconds.

        Returns:
            The surviving timestamps.
        """
        if stamps is None:
            return deque()
        while stamps and now - stamps[0] >= window:
            stamps.popleft()
        return stamps

    @staticmethod
    def _recovers_in(reset_at: float | None, now: float) -> str:
        """Render when a budget recovers.

        Args:
            reset_at: Recovery time on the tracker's clock.
            now: Current time.

        Returns:
            A short user-facing sentence.
        """
        if reset_at is None:
            return "Try again shortly."
        return f"Try again in about {max(1, int(reset_at - now))} seconds."


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """Read a header case-insensitively.

    Args:
        headers: Response headers.
        name: Lower-case header name.

    Returns:
        The header value, or None.
    """
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return None


def _as_int(value: str | None) -> int | None:
    """Parse an integer header value.

    Args:
        value: Raw header value.

    Returns:
        The parsed integer, or None when absent or unparsable.
    """
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


TRACKER = RateLimitTracker()
