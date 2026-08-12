# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Message send helper for the Hospitable messages endpoint.

A 202 means the message was ACCEPTED FOR DELIVERY. Delivery itself is
asynchronous and this integration never observes it, so nothing here
reports a message as sent or delivered. ``sent_reference_id`` is the
correlation handle.

OQ-001 is UNVERIFIED: no real send has ever been made, so the 202 body
shape is unknown. The parser tolerates a body carrying the handle, a
body without it, and no body at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from custom_components.hospitable.api.client import HospitableApiClient
from custom_components.hospitable.api.const import RESERVATION_MESSAGES_PATH
from custom_components.hospitable.api.models import HospitableMessage
from custom_components.hospitable.api.write_client import HospitableWriteClient


@dataclass(frozen=True, slots=True)
class SendAcceptance:
    """The upstream response to one accepted send."""

    reservation_uuid: str
    sent_reference_id: str | None
    headers: dict[str, str] = field(default_factory=dict)


def build_send_body(
    *, body: str, images: list[str] | None = None, sender_id: str | None = None
) -> dict[str, Any]:
    """Build the message send request body.

    ``body`` is transmitted verbatim. The upstream documentation renders
    "/n is parsed for line breaks", which is a typographical error for a
    newline escape; no literal substitution is performed.

    Args:
        body: Message text.
        images: Image URIs, at most three.
        sender_id: Airbnb-only sending identity.

    Returns:
        The request body, omitting unsupplied optional fields.
    """
    payload: dict[str, Any] = {"body": body}
    if images:
        payload["images"] = list(images)
    if sender_id is not None:
        payload["sender_id"] = sender_id
    return payload


def parse_acceptance(
    reservation_uuid: str, data: dict[str, Any], headers: dict[str, str]
) -> SendAcceptance:
    """Extract the correlation handle from a 202 body.

    Args:
        reservation_uuid: Reservation the send targeted.
        data: Parsed response body, possibly empty.
        headers: Response headers.

    Returns:
        The acceptance record. ``sent_reference_id`` is None when the
        body does not carry one, which is not an error.
    """
    container = data.get("data") if isinstance(data.get("data"), dict) else data
    reference = container.get("sent_reference_id") if container else None
    return SendAcceptance(
        reservation_uuid=reservation_uuid,
        sent_reference_id=str(reference) if reference is not None else None,
        headers=headers,
    )


async def async_send_message(
    client: HospitableWriteClient,
    reservation_uuid: str,
    *,
    body: str,
    images: list[str] | None = None,
    sender_id: str | None = None,
) -> SendAcceptance:
    """Send one message and return the acceptance record.

    Args:
        client: Write-capable API client.
        reservation_uuid: Target reservation UUID.
        body: Message text.
        images: Image URIs, at most three.
        sender_id: Airbnb-only sending identity.

    Returns:
        The acceptance record.
    """
    result = await client._post(
        RESERVATION_MESSAGES_PATH.format(uuid=reservation_uuid),
        json=build_send_body(body=body, images=images, sender_id=sender_id),
    )
    return parse_acceptance(reservation_uuid, result.data, result.headers)


@dataclass(frozen=True, slots=True)
class MessageThread:
    """One reservation's conversation, fetched in a SINGLE request."""

    reservation_uuid: str
    messages: tuple[HospitableMessage, ...]
    headers: dict[str, str] = field(default_factory=dict)


async def async_get_messages(
    client: HospitableApiClient, reservation_uuid: str
) -> MessageThread:
    """Fetch one reservation's whole thread in ONE request.

    There is deliberately NO pagination loop and no ``page`` or
    ``per_page`` parameter. ``GET /reservations/{uuid}/messages``
    returns a ``{data}`` envelope with no ``meta`` and no ``links``, and
    both parameters are silently ignored upstream, so sending them would
    create a false impression that the payload is bounded (D-07,
    FR-023).

    Scope caveat, recorded rather than assumed away: non-pagination was
    observed only up to a TEN-message thread, the busiest on the
    reference account. Pagination appearing above some unobserved
    threshold cannot be ruled out, so a ``meta`` or ``links`` block is
    tolerated here — but it is deliberately NOT followed, because
    following it would build the pagination loop this decision forbids
    on evidence that does not exist.

    Args:
        client: GET-only API client. A write client is neither needed
            nor accepted by the read path's typing.
        reservation_uuid: Target reservation UUID.

    Returns:
        The thread and the response headers, which carry the
        ``x-ratelimit-*`` budget this endpoint reports.
    """
    payload, headers = await client._get_with_response(
        RESERVATION_MESSAGES_PATH.format(uuid=reservation_uuid)
    )
    data = payload.get("data")
    items = (
        [item for item in data if isinstance(item, dict)]
        if isinstance(data, list)
        else []
    )
    return MessageThread(
        reservation_uuid=reservation_uuid,
        messages=tuple(HospitableMessage.from_api(item) for item in items),
        headers=headers,
    )
