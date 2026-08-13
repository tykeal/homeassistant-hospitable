# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""The ``hospitable.send_message`` service handler (FR-009 to FR-019).

Order of operations matters and is enforced by test:

1. Resolve the account and the reservation.
2. Check BOTH rate-limit budgets, BEFORE any HTTP request. A local
   refusal costs the user nothing and burns no upstream allowance.
3. Resolve the platform ONLY when ``sender_id`` was supplied, because
   ``sender_id`` is Airbnb-only. An unresolved platform is a REJECTION,
   not permission to proceed.
4. POST, then charge the budget only on acceptance.
5. Return through the shared privacy chokepoint.

A 202 means Hospitable ACCEPTED the message for asynchronous
delivery. It is not a confirmation that the guest received anything,
and no text this module produces may imply otherwise.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.httpx_client import get_async_client

from custom_components.hospitable import rate_limit
from custom_components.hospitable.actions import response
from custom_components.hospitable.actions.helpers import (
    cached_reservation,
    resolve_config_entry,
    resolve_reservation_uuid,
)
from custom_components.hospitable.actions.schemas import (
    ATTR_BODY,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_ENTITY_ID,
    ATTR_IMAGES,
    ATTR_RESERVATION_UUID,
    ATTR_SENDER_ID,
)
from custom_components.hospitable.api.auth import StaticTokenProvider
from custom_components.hospitable.api.exceptions import (
    HospitableError,
    HospitableForbiddenError,
    HospitableNotFoundError,
    HospitableRateLimitError,
    HospitableRequestValidationError,
    HospitableScopeError,
)
from custom_components.hospitable.api.messages import async_send_message
from custom_components.hospitable.api.write_client import HospitableWriteClient
from custom_components.hospitable.const import (
    CONF_GUEST_CONTACT_DETAILS,
    CONF_TOKEN,
    DEFAULT_GUEST_CONTACT_DETAILS,
)

# sender_id is accepted by Airbnb only (FR-013).
SENDER_ID_PLATFORM = "airbnb"


async def async_handle_send_message(
    hass: HomeAssistant, call: ServiceCall
) -> ServiceResponse:
    """Accept a guest message for delivery.

    Args:
        hass: Home Assistant instance.
        call: The service call.

    Returns:
        An acceptance record, filtered through the shared serialiser.

    Raises:
        ServiceValidationError: The call is not valid or is refused
            locally.
        HomeAssistantError: The upstream request failed.
    """
    entry = resolve_config_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    reservation_uuid = resolve_reservation_uuid(
        hass,
        entry,
        reservation_uuid=call.data.get(ATTR_RESERVATION_UUID),
        entity_id=call.data.get(ATTR_ENTITY_ID),
    )
    token = str(entry.data[CONF_TOKEN])
    rate_limit.TRACKER.check(token, reservation_uuid)

    client = HospitableWriteClient(StaticTokenProvider(token), get_async_client(hass))
    sender_id = call.data.get(ATTR_SENDER_ID)
    if sender_id is not None:
        await _assert_airbnb(entry, client, reservation_uuid)

    try:
        acceptance = await async_send_message(
            client,
            reservation_uuid,
            body=call.data[ATTR_BODY],
            images=call.data.get(ATTR_IMAGES),
            sender_id=sender_id,
        )
    except HospitableRequestValidationError as exc:
        raise ServiceValidationError(_render_validation(exc)) from exc
    except HospitableScopeError as exc:
        raise HomeAssistantError(
            "Hospitable refused the message send. The token may lack the "
            "scope required to send messages; check the token's scopes in "
            "the Hospitable dashboard and reconnect."
        ) from exc
    except HospitableForbiddenError as exc:
        raise HomeAssistantError(
            "Hospitable refused the message send. The token may lack the "
            "scope required to send messages, or the account plan may not "
            "include messaging; check both and reconnect."
        ) from exc
    except HospitableRateLimitError as exc:
        raise HomeAssistantError(
            "Hospitable is throttling message sends. This clears on its "
            f"own; retry in about {exc.retry_after or 60} seconds."
        ) from exc
    except HospitableError as exc:
        raise HomeAssistantError(
            "The message could not be submitted to Hospitable. This is "
            "usually temporary; try again shortly."
        ) from exc

    rate_limit.TRACKER.record(token, reservation_uuid)
    rate_limit.TRACKER.apply_headers(token, reservation_uuid, acceptance.headers)
    # Referenced through the module so the single chokepoint stays
    # patchable and observable as one code path.
    filtered: ServiceResponse = response.serialize_response(
        {
            "accepted": True,
            "reservation_uuid": acceptance.reservation_uuid,
            "sent_reference_id": acceptance.sent_reference_id,
        },
        guest_contact=bool(
            entry.options.get(CONF_GUEST_CONTACT_DETAILS, DEFAULT_GUEST_CONTACT_DETAILS)
        ),
    )
    return filtered


async def _assert_airbnb(
    entry: ConfigEntry, client: HospitableWriteClient, reservation_uuid: str
) -> None:
    """Reject ``sender_id`` unless the reservation is confirmed Airbnb.

    The upstream ``platform`` value is carried on the model as
    ``channel``. A null channel means UNRESOLVED, which is a rejection
    rather than permission to proceed.

    Args:
        entry: The selected config entry.
        client: Client used for a cache miss lookup.
        reservation_uuid: Target reservation UUID.

    Raises:
        ServiceValidationError: The platform is not Airbnb or could not
            be resolved.
    """
    cached = cached_reservation(entry, reservation_uuid)
    if cached is not None:
        _reject_unless_airbnb(getattr(cached, "channel", None), reservation_uuid)
        return
    try:
        payload: dict[str, Any] = await client.get_reservation(reservation_uuid)
    except HospitableNotFoundError as exc:
        raise ServiceValidationError(
            f"Reservation {reservation_uuid} was not found, so sender_id "
            "cannot be validated. Remove sender_id or correct the "
            "reservation."
        ) from exc
    except HospitableError as exc:
        raise ServiceValidationError(
            f"The booking channel for reservation {reservation_uuid} could "
            "not be determined, so sender_id cannot be validated. Remove "
            "sender_id or try again later."
        ) from exc
    _reject_unless_airbnb(payload.get("platform"), reservation_uuid)


def _reject_unless_airbnb(platform: Any, reservation_uuid: str) -> None:
    """Raise unless the resolved platform is Airbnb.

    Args:
        platform: Resolved platform value, possibly None.
        reservation_uuid: Target reservation UUID.

    Raises:
        ServiceValidationError: The platform is not Airbnb or is
            unresolved.
    """
    if platform is None:
        raise ServiceValidationError(
            f"The booking channel for reservation {reservation_uuid} is "
            "unknown, and sender_id is accepted only on Airbnb "
            "reservations. Remove sender_id."
        )
    if str(platform).casefold() != SENDER_ID_PLATFORM:
        raise ServiceValidationError(
            f"sender_id is accepted only on Airbnb reservations, and "
            f"reservation {reservation_uuid} is a {platform} booking. "
            "Remove sender_id."
        )


def _render_validation(exc: HospitableRequestValidationError) -> str:
    """Render a rejected request body as a user-fixable message.

    Args:
        exc: The upstream validation failure.

    Returns:
        A message preserving every per-field message upstream returned.
    """
    detail = " ".join(exc.field_messages)
    summary = "Hospitable rejected the message"
    return f"{summary}: {detail}" if detail else f"{summary}."
