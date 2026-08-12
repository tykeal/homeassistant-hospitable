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

from custom_components.hospitable.api.const import RESERVATION_MESSAGES_PATH
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
