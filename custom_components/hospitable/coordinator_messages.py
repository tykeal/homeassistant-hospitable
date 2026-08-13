# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""The opt-in awaiting-host-reply message fetch (US5, T142 to T142b).

Driven by the reservation coordinator rather than being a coordinator
of its own, because the thing it needs — which reservation is
operationally relevant for each property — is exactly what the
reservation poll has just computed. A second coordinator would have to
either duplicate that or race it.

**Bodies stop here.** ``MessagePresence`` carries the derived indicator
and a guest-message timestamp and NOTHING else. A message body is never
copied out of the thread, so no entity attribute, diagnostic, or log
line downstream can leak one by forgetting to guard it. That is the
same reasoning that keeps ``profile_picture`` off ``HospitableGuest``
and ``note`` off ``HospitableTask``: a field that does not exist cannot
be exposed by accident. The bodies are still parsed onto
``HospitableMessage``, because the ``get_messages`` service returns
them on a user-invoked surface — this module simply does not carry them
any further.

The word "unread" appears nowhere by design. The upstream API has NO
read-state field; the indicator reports only who wrote last (FR-037).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.hospitable.api.client import HospitableApiClient
from custom_components.hospitable.api.exceptions import (
    HospitableError,
    HospitableRateLimitError,
)
from custom_components.hospitable.api.messages import async_get_messages
from custom_components.hospitable.api.models import (
    HospitableMessage,
    HospitableReservation,
)
from custom_components.hospitable.rate_limit import TRACKER
from custom_components.hospitable.services.selection import select_reservation

_LOGGER = logging.getLogger(__name__)

# The minimum spacing between two message fetches for the SAME
# reservation.
#
# This is a DELIBERATELY CONSERVATIVE CHOICE, not a derivation. The
# confirmed upstream budget is 2 requests per 60 seconds per
# reservation, which would mathematically permit 30 seconds. Polling at
# that mathematical maximum would consume both slots, and OQ-007 — which
# is OPEN, and cannot be closed without issuing a real send — leaves it
# unknown whether reads and writes share one bucket. If they do, a
# maximal poll would starve a user-initiated send. Sixty seconds leaves
# exactly one slot free in either case.
#
# Enforced INDEPENDENTLY of the configured reservation poll interval,
# whose own floor is one minute: without that independence an
# aggressively configured entry would drive message traffic straight at
# the upstream limit (T142a, FR-038a).
MESSAGE_FETCH_FLOOR_SECONDS = 60.0

# Which sender labels count as the guest. Upstream sends ``sender_type``
# and ``sender_role`` as SIBLINGS of the ``sender`` object rather than
# children of it, which is why they survive the privacy filter that
# drops ``sender`` wholesale (FR-047a).
_GUEST_ROLES = frozenset({"guest"})
_HOST_ROLES = frozenset({"host", "user", "operator", "teammate"})


@dataclass(frozen=True)
class MessagePresence:
    """What a property's thread reveals, with the content removed.

    Deliberately only two fields. Anything richer would be a body, a
    sender identity, or a message count that implies one, none of which
    has a permitted entity surface (T138, FR-024, FR-041).
    """

    awaiting_host_reply: bool | None
    last_guest_message_at: str | None


def derive_presence(messages: tuple[HospitableMessage, ...]) -> MessagePresence:
    """Derive the indicator from a thread's sender roles.

    An EMPTY thread yields ``None``, not ``False``. Reporting false
    would assert that the host has replied, which nothing in an empty
    thread supports (T137).

    Args:
        messages: The thread's messages, oldest first as upstream
            returns them.

    Returns:
        The derived presence record.
    """
    if not messages:
        return MessagePresence(awaiting_host_reply=None, last_guest_message_at=None)
    latest = messages[-1]
    role = (latest.sender_role or latest.sender_type or "").casefold()
    awaiting: bool | None
    if role in _GUEST_ROLES:
        awaiting = True
    elif role in _HOST_ROLES:
        awaiting = False
    else:
        # An unrecognised label is reported as unknown rather than
        # guessed at. Guessing false would claim a reply nobody saw.
        awaiting = None
    last_guest_at = next(
        (
            message.created_at
            for message in reversed(messages)
            if (message.sender_role or message.sender_type or "").casefold()
            in _GUEST_ROLES
        ),
        None,
    )
    return MessagePresence(
        awaiting_host_reply=awaiting, last_guest_message_at=last_guest_at
    )


class MessagePresenceFetcher:
    """Fetches at most one thread per property per reservation cycle."""

    def __init__(
        self,
        client: HospitableApiClient,
        *,
        token: str,
        property_ids: list[str],
    ) -> None:
        """Initialize the fetcher for one config entry's properties.

        Args:
            client: GET-only API client. The write client is neither
                needed nor accepted, so this module cannot send.
            token: Raw personal access token, needed only to key the
                shared rate-limit tracker's per-token budget.
            property_ids: Properties to fetch for.
        """
        # Annotated explicitly as the GET-only base client so the
        # write-isolation gate 1 scan can see it. The type is what makes
        # ``self._client._post(...)`` a mypy error here rather than a
        # runtime surprise (D-01 gate 1, FR-001).
        self._client: HospitableApiClient = client
        self._token = token
        self._property_ids = list(property_ids)
        self._presence: dict[str, MessagePresence] = {}
        self._last_attempt: dict[str, float] = {}
        self._blocked_until: dict[str, float] = {}

    @property
    def presence(self) -> dict[str, MessagePresence]:
        """Return the last known presence record for each property.

        Returns:
            A copy keyed by property id. Properties whose fetch has not
            yet succeeded are simply absent, which the sensor reports as
            unknown.
        """
        return dict(self._presence)

    async def async_update(self, reservations: list[HospitableReservation]) -> None:
        """Fetch each property's operationally relevant thread, once.

        Never raises. Every failure mode here — a throttle, a transport
        error, an exhausted local budget — leaves the previous value in
        place and lets the reservation data that WAS fetched
        successfully through untouched. A throttle is not an outage
        (T142b, FR-019).

        Args:
            reservations: The reservations the poll just returned.
        """
        now = dt_util.utcnow().timestamp()
        for property_id in self._property_ids:
            uuid = self._target_reservation(property_id, reservations)
            if uuid is None:
                continue
            if not self._may_fetch(uuid, now):
                continue
            # Charged BEFORE the request, so a fetch that ends in a 429
            # still consumes the floor. Charging only on success would
            # let a throttled reservation be retried every cycle.
            self._last_attempt[uuid] = now
            await self._fetch_one(property_id, uuid, now)

    def _target_reservation(
        self, property_id: str, reservations: list[HospitableReservation]
    ) -> str | None:
        """Return the operationally relevant reservation for a property.

        The SAME selection the rest of the integration uses, so the
        indicator and the property's other sensors always describe one
        stay rather than two different ones.

        Args:
            property_id: Property to select for.
            reservations: Every reservation the poll returned.

        Returns:
            The reservation UUID, or ``None`` when the property has no
            reservation at all.
        """
        owned = [
            reservation
            for reservation in reservations
            if reservation.property_id == property_id
        ]
        if not owned:
            return None
        selected, _ = select_reservation(owned, dt_util.utcnow())
        return selected.reservation_id if selected is not None else None

    def _may_fetch(self, uuid: str, now: float) -> bool:
        """Return whether this reservation may be fetched right now.

        Args:
            uuid: Target reservation UUID.
            now: Current POSIX timestamp.

        Returns:
            Whether all three gates — the floor, an outstanding
            ``retry-after``, and the shared tracker — permit a fetch.
        """
        previous = self._last_attempt.get(uuid)
        if previous is not None and now - previous < MESSAGE_FETCH_FLOOR_SECONDS:
            return False
        if now < self._blocked_until.get(uuid, 0.0):
            return False
        try:
            # The SHARED tracker from T047, not a second counter: the
            # upstream budget this consumes is the same one a send
            # consumes, and OQ-007 leaves open whether they are literally
            # the same bucket. Two counters could not model that.
            TRACKER.check(self._token, uuid)
        except ServiceValidationError:
            # A refusal is a deferral, not an error. The reservation
            # data is still good and the previous indicator still holds.
            return False
        return True

    async def _fetch_one(self, property_id: str, uuid: str, now: float) -> None:
        """Fetch and store one property's presence, tolerating failure.

        Args:
            property_id: Property the thread belongs to.
            uuid: Target reservation UUID.
            now: Current POSIX timestamp.
        """
        try:
            thread = await async_get_messages(self._client, uuid)
        except HospitableRateLimitError as exc:
            # ``retry_after`` was already parsed by the shared read-path
            # parser, which handles both delta-seconds and HTTP-date
            # forms and caps at MAX_BACKOFF. Falling back to the floor
            # keeps a header-less 429 from being retried immediately.
            wait = exc.retry_after or MESSAGE_FETCH_FLOOR_SECONDS
            self._blocked_until[uuid] = now + wait
            _LOGGER.debug(
                "Hospitable throttled the message poll for reservation %s; "
                "retaining the last known indicator and retrying in %.0fs",
                uuid,
                wait,
            )
            return
        except HospitableError as err:
            # Logged by TYPE, never by content: a message body must not
            # reach a log record even indirectly (T138, FR-041).
            _LOGGER.debug(
                "Message poll for reservation %s failed (%s); "
                "retaining the last known indicator",
                uuid,
                type(err).__name__,
            )
            return
        TRACKER.record(self._token, uuid)
        TRACKER.apply_headers(self._token, uuid, thread.headers)
        self._presence[property_id] = derive_presence(thread.messages)
