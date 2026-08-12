# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""The ``hospitable.get_messages`` service handler (FR-020 to FR-024).

Three things this handler deliberately does NOT do:

* It does not paginate. The endpoint returns the whole thread in one
  ``{data}`` envelope and silently ignores ``page`` and ``per_page``, so
  a loop would be built on evidence that does not exist (D-07).
* It does not log message bodies, at any level. Returning them to the
  caller is the service's purpose; writing them to a log file is not
  (FR-024).
* It does not return the opaque ``sender`` object. That is enforced by
  the shared chokepoint rather than here, so a future service cannot
  reintroduce the leak by forgetting to filter (FR-047a, FR-048).

An upstream 429 is retryable-with-backoff and is reported as such. It is
distinct from a LOCAL pre-refusal, which costs nothing and burns no
upstream allowance.
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.exceptions import HomeAssistantError

from custom_components.hospitable import rate_limit
from custom_components.hospitable.actions import response
from custom_components.hospitable.actions.helpers import (
    guest_contact_enabled,
    read_client,
    resolve_config_entry,
    resolve_reservation_uuid,
)
from custom_components.hospitable.actions.schemas import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_ENTITY_ID,
    ATTR_RESERVATION_UUID,
)
from custom_components.hospitable.api.exceptions import (
    HospitableError,
    HospitableNotFoundError,
    HospitableRateLimitError,
)
from custom_components.hospitable.api.messages import async_get_messages
from custom_components.hospitable.api.models import HospitableMessage
from custom_components.hospitable.const import CONF_TOKEN


async def async_handle_get_messages(
    hass: HomeAssistant, call: ServiceCall
) -> ServiceResponse:
    """Return one reservation's conversation thread.

    Args:
        hass: Home Assistant instance.
        call: The service call.

    Returns:
        The thread, filtered through the shared serialiser.

    Raises:
        HomeAssistantError: The upstream request failed or was
            throttled.
    """
    entry = resolve_config_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    reservation_uuid = resolve_reservation_uuid(
        hass,
        entry,
        reservation_uuid=call.data.get(ATTR_RESERVATION_UUID),
        entity_id=call.data.get(ATTR_ENTITY_ID),
    )
    token = str(entry.data[CONF_TOKEN])
    # The read budget is checked BEFORE the request, and shares the one
    # tracker with the send path: the per-reservation bucket is a single
    # upstream budget, and OQ-007 leaves open whether reads and writes
    # draw on it separately. Treating them as one is the conservative
    # reading, so a burst of reads cannot starve a send.
    rate_limit.TRACKER.check(token, reservation_uuid)

    client = read_client(hass, entry)
    try:
        # The budget is charged in ``finally``: the upstream bucket is
        # spent by the REQUEST, not by a 200. Charging only on success
        # would let a run of 404s or 429s slip past the local guard and
        # hammer a live account. A transport failure may never have
        # reached the server, so charging it is conservative -- it can
        # only make the next call wait, never let more through.
        thread = await async_get_messages(client, reservation_uuid)
    except HospitableNotFoundError:
        # Not-found is a RETURN VALUE, so an automation can branch on it
        # without a try/except (FR-028).
        return _empty(reservation_uuid, entry_contact=guest_contact_enabled(entry))
    except HospitableRateLimitError as exc:
        raise HomeAssistantError(
            "Hospitable is throttling message reads for reservation "
            f"{reservation_uuid}. This clears on its own; retry in about "
            f"{int(exc.retry_after or 60)} seconds."
        ) from exc
    except HospitableError as exc:
        raise HomeAssistantError(
            f"The message thread for reservation {reservation_uuid} could "
            "not be retrieved. This is usually temporary; try again shortly."
        ) from exc
    finally:
        rate_limit.TRACKER.record(token, reservation_uuid)

    rate_limit.TRACKER.apply_headers(token, reservation_uuid, thread.headers)
    filtered: ServiceResponse = response.serialize_response(
        {
            "found": True,
            "reservation_uuid": reservation_uuid,
            "messages": [_as_payload(message) for message in thread.messages],
        },
        guest_contact=guest_contact_enabled(entry),
    )
    return filtered


def _empty(reservation_uuid: str, *, entry_contact: bool) -> ServiceResponse:
    """Build the not-found response.

    Args:
        reservation_uuid: The reservation that was asked for.
        entry_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        A ``found: false`` response, built through the chokepoint like
        every other response.
    """
    empty: ServiceResponse = response.serialize_response(
        {"found": False, "reservation_uuid": reservation_uuid, "messages": []},
        guest_contact=entry_contact,
    )
    return empty


def _as_payload(message: HospitableMessage) -> dict[str, Any]:
    """Render one message for the service response.

    ``sender`` is included here ON PURPOSE and removed by the shared
    serialiser. Stripping it locally would move the guarantee back into
    the handler, which is exactly the forgetting defect the chokepoint
    exists to prevent (FR-048).

    Args:
        message: Parsed message.

    Returns:
        The message as a mapping, before filtering.
    """
    return {
        "id": message.message_id,
        "platform": message.platform,
        "conversation_id": message.conversation_id,
        "body": message.body,
        "content_type": message.content_type,
        "sender_type": message.sender_type,
        "sender_role": message.sender_role,
        "sender": message.sender,
        "created_at": message.created_at,
        "attachments": [dict(item) for item in message.attachments],
        "source": message.source,
    }
