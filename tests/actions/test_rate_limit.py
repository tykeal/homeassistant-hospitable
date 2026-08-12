# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for the two-dimensional rate limiter (T037-T040).

The two budgets differ in evidential strength and must never be
conflated:

* per-(token, reservation) 2 per rolling 60s — CONFIRMED-BY-TEST against
  the messages endpoint, which returns ``x-ratelimit-limit``,
  ``x-ratelimit-remaining``, and on 429 ``retry-after`` plus
  ``x-ratelimit-reset``.
* per-token 50 per rolling 300s — DOCUMENTED-ONLY, never observed. These
  tests assert the implementation honours the documented number, NOT
  that upstream enforces it.

Server headers are authoritative over local counting: local counting is
a floor, not the authority.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.actions.conftest import (
    RESERVATION_A,
    RESERVATION_B,
    SECOND_TOKEN,
    SYNTHETIC_TOKEN,
)

XFAIL_RED = pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: actions/rate_limit.py does not exist yet",
)


class FakeClock:
    """A manually advanced monotonic clock."""

    def __init__(self) -> None:
        """Start the clock at zero."""
        self.now = 0.0

    def __call__(self) -> float:
        """Return the current fake time.

        Returns:
            Seconds elapsed on the fake clock.
        """
        return self.now

    def advance(self, seconds: float) -> None:
        """Move the clock forward.

        Args:
            seconds: Number of seconds to advance by.
        """
        self.now += seconds


def _tracker(clock: FakeClock) -> Any:
    """Build a tracker bound to a fake clock.

    Args:
        clock: Fake monotonic clock.

    Returns:
        A fresh rate-limit tracker.
    """
    from custom_components.hospitable.actions.rate_limit import (  # type: ignore
        RateLimitTracker,
    )

    return RateLimitTracker(time_source=clock)


@XFAIL_RED
def test_documented_limits_are_the_defaults() -> None:
    """The tracker's defaults are the two documented budgets."""
    from custom_components.hospitable.actions import (  # type: ignore
        rate_limit,
    )

    assert rate_limit.RESERVATION_LIMIT == 2
    assert rate_limit.RESERVATION_WINDOW_SECONDS == 60
    assert rate_limit.TOKEN_LIMIT == 50
    assert rate_limit.TOKEN_WINDOW_SECONDS == 300


@XFAIL_RED
def test_per_reservation_budget_is_two_per_sixty_seconds() -> None:
    """Two sends pass, the third is refused, and the window slides."""
    from homeassistant.exceptions import ServiceValidationError

    clock = FakeClock()
    tracker = _tracker(clock)

    for _ in range(2):
        tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)
        tracker.record(SYNTHETIC_TOKEN, RESERVATION_A)

    with pytest.raises(ServiceValidationError):
        tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)

    clock.advance(59)
    with pytest.raises(ServiceValidationError):
        tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)

    clock.advance(2)
    tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)


@XFAIL_RED
def test_per_token_budget_is_fifty_per_three_hundred_seconds() -> None:
    """The documented per-token budget is honoured and recovers.

    Each send targets a DISTINCT reservation so the per-reservation gate
    cannot be what refuses the call; only the per-token gate can.
    """
    from homeassistant.exceptions import ServiceValidationError

    clock = FakeClock()
    tracker = _tracker(clock)

    for index in range(50):
        reservation = f"res-example-{index:04d}"
        tracker.check(SYNTHETIC_TOKEN, reservation)
        tracker.record(SYNTHETIC_TOKEN, reservation)
        clock.advance(1)

    with pytest.raises(ServiceValidationError):
        tracker.check(SYNTHETIC_TOKEN, "res-example-9999")

    clock.advance(300)
    tracker.check(SYNTHETIC_TOKEN, "res-example-9999")


@XFAIL_RED
def test_both_gates_are_evaluated_on_every_check() -> None:
    """Exhausting either dimension alone refuses the call."""
    from homeassistant.exceptions import ServiceValidationError

    clock = FakeClock()
    reservation_exhausted = _tracker(clock)
    for _ in range(2):
        reservation_exhausted.check(SYNTHETIC_TOKEN, RESERVATION_A)
        reservation_exhausted.record(SYNTHETIC_TOKEN, RESERVATION_A)
    with pytest.raises(ServiceValidationError) as reservation_error:
        reservation_exhausted.check(SYNTHETIC_TOKEN, RESERVATION_A)
    reservation_exhausted.check(SYNTHETIC_TOKEN, RESERVATION_B)

    token_exhausted = _tracker(clock)
    for index in range(50):
        reservation = f"res-example-{index:04d}"
        token_exhausted.check(SYNTHETIC_TOKEN, reservation)
        token_exhausted.record(SYNTHETIC_TOKEN, reservation)
    with pytest.raises(ServiceValidationError) as token_error:
        token_exhausted.check(SYNTHETIC_TOKEN, "res-example-untouched")

    assert "reservation" in str(reservation_error.value).lower()
    assert str(reservation_error.value) != str(token_error.value), (
        "the two limits must be distinguishable to the user"
    )


@XFAIL_RED
def test_per_reservation_buckets_are_independent() -> None:
    """Exhausting reservation A leaves reservation B callable.

    This is CONFIRMED-BY-TEST upstream: A returned 429 while B returned
    200 with a fresh remaining count.
    """
    from homeassistant.exceptions import ServiceValidationError

    clock = FakeClock()
    tracker = _tracker(clock)

    for _ in range(2):
        tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)
        tracker.record(SYNTHETIC_TOKEN, RESERVATION_A)

    with pytest.raises(ServiceValidationError):
        tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)
    tracker.check(SYNTHETIC_TOKEN, RESERVATION_B)


@XFAIL_RED
def test_server_headers_override_optimistic_local_counting() -> None:
    """A server ``remaining`` of zero refuses even with local budget left.

    Local counting is a floor, not the authority. After one send the
    local budget still allows a second, but the server says none remain.
    """
    from homeassistant.exceptions import ServiceValidationError

    clock = FakeClock()
    tracker = _tracker(clock)

    tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)
    tracker.record(SYNTHETIC_TOKEN, RESERVATION_A)
    tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)

    tracker.apply_headers(
        SYNTHETIC_TOKEN,
        RESERVATION_A,
        {
            "x-ratelimit-limit": "2",
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": str(int(clock.now) + 30),
        },
    )

    with pytest.raises(ServiceValidationError):
        tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)


@XFAIL_RED
def test_server_headers_also_relax_a_pessimistic_local_count() -> None:
    """A server ``remaining`` above zero wins over a local exhaustion.

    The same authority rule has to cut both ways, or it is not authority
    at all — it is just a second floor.
    """
    clock = FakeClock()
    tracker = _tracker(clock)

    for _ in range(2):
        tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)
        tracker.record(SYNTHETIC_TOKEN, RESERVATION_A)

    tracker.apply_headers(
        SYNTHETIC_TOKEN,
        RESERVATION_A,
        {"x-ratelimit-limit": "2", "x-ratelimit-remaining": "1"},
    )

    tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)


@XFAIL_RED
def test_a_stale_server_hint_expires_at_its_reset() -> None:
    """A server hint stops applying once its reset time has passed."""
    clock = FakeClock()
    tracker = _tracker(clock)

    tracker.apply_headers(
        SYNTHETIC_TOKEN,
        RESERVATION_A,
        {
            "x-ratelimit-limit": "2",
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": str(int(clock.now) + 10),
        },
    )
    clock.advance(11)

    tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)


@XFAIL_RED
def test_a_429_is_retryable_with_backoff_not_a_hard_failure() -> None:
    """A 429 yields a retry delay driven by ``retry-after``.

    OQ-007 is UNVERIFIED: it is unknown whether reads and writes share a
    per-reservation bucket, so the send path must survive being
    throttled by a poll rather than treating a 429 as terminal.
    """
    clock = FakeClock()
    tracker = _tracker(clock)

    delay = tracker.retry_after({"retry-after": "60", "x-ratelimit-remaining": "0"})

    assert delay == 60
    assert tracker.retry_after({}) is None


@XFAIL_RED
def test_accounting_keys_on_a_hash_of_the_token() -> None:
    """Two entries sharing a token share a budget; the raw token never leaks."""
    from homeassistant.exceptions import ServiceValidationError

    from tests.helpers.tokens import token_key

    clock = FakeClock()
    tracker = _tracker(clock)

    for _ in range(2):
        tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)
        tracker.record(SYNTHETIC_TOKEN, RESERVATION_A)

    with pytest.raises(ServiceValidationError):
        tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)
    tracker.check(SECOND_TOKEN, RESERVATION_A)

    rendered = repr(sorted(str(key) for key in tracker.bucket_keys()))
    assert SYNTHETIC_TOKEN not in rendered
    assert SECOND_TOKEN not in rendered
    assert token_key(SYNTHETIC_TOKEN) in rendered


@XFAIL_RED
def test_the_budget_is_recorded_only_on_acceptance() -> None:
    """A failed send consumes no budget."""
    clock = FakeClock()
    tracker = _tracker(clock)

    for _ in range(5):
        tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)

    tracker.record(SYNTHETIC_TOKEN, RESERVATION_A)
    tracker.check(SYNTHETIC_TOKEN, RESERVATION_A)


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: hospitable.send_message is not registered yet",
)
async def test_refusal_happens_before_any_http_request(
    hass: Any,
    loaded_config_entry_factory: Any,
    messages_routes: Any,
    respx_router: Any,
) -> None:
    """The third send in a minute is refused without touching the network.

    Registered through the real service bus so the ordering assertion is
    about the shipped handler, not about a helper called in isolation.
    """
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.hospitable.const import DOMAIN
    from tests.helpers import load_fixture

    await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "send_message"), (
        "hospitable.send_message is not registered"
    )
    route = messages_routes.post(
        RESERVATION_A, json_body=load_fixture("send_message_202_full.json")
    )
    data = {"reservation_uuid": RESERVATION_A, "body": "Synthetic."}

    for _ in range(2):
        await hass.services.async_call(
            DOMAIN, "send_message", data, blocking=True, return_response=True
        )
    before = len(respx_router.calls)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "send_message", data, blocking=True, return_response=True
        )

    assert route.call_count == 2
    assert len(respx_router.calls) == before
