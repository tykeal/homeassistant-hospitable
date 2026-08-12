# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""The ``hospitable.find_reservation`` service handler (FR-025, FR-028).

Not-found is a RETURN VALUE — ``{"found": false, "reservation": null}``
— so an automation can branch on it without a try/except. API failures
still raise, because a handler that swallowed every failure into
``found: false`` would report a broken integration as an empty answer.

The reservation is fetched with ``include=guest``, SINGULAR. Plural
``guests`` is a silently-ignored no-op upstream, and unrecognised
include names are ignored rather than rejected, so the client verifies
the key actually arrived instead of assuming it (FR-075).

The guest object carries ``profile_picture``, ``email``, and
``phone_numbers``. None of them are filtered here: the response goes
through the ONE shared chokepoint (FR-048).
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.exceptions import HomeAssistantError

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
    HospitableIncludeMissingError,
    HospitableNotFoundError,
)
from custom_components.hospitable.api.reservations import (
    RESERVATION_INCLUDE,
)

# Only `guest` is asserted present. Live probing confirmed 29/29
# reservations carry a non-null guest; the behaviour of `properties` on
# the SINGLE-reservation endpoint was never observed, so requiring it
# would risk failing a lookup on an untested assumption.
REQUIRED_INCLUDES = ("guest",)


async def async_handle_find_reservation(
    hass: HomeAssistant, call: ServiceCall
) -> ServiceResponse:
    """Look up one reservation by UUID.

    Args:
        hass: Home Assistant instance.
        call: The service call.

    Returns:
        The reservation, filtered through the shared serialiser.

    Raises:
        HomeAssistantError: The upstream request failed, or the
            requested include was not honoured.
    """
    entry = resolve_config_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    reservation_uuid = resolve_reservation_uuid(
        hass,
        entry,
        reservation_uuid=call.data.get(ATTR_RESERVATION_UUID),
        entity_id=call.data.get(ATTR_ENTITY_ID),
    )
    client = read_client(hass, entry)
    payload: dict[str, Any] | None
    try:
        payload = await client.get_reservation(
            reservation_uuid, include=RESERVATION_INCLUDE, require=REQUIRED_INCLUDES
        )
    except HospitableNotFoundError:
        payload = None
    except HospitableIncludeMissingError as exc:
        raise HomeAssistantError(
            f"Hospitable returned reservation {reservation_uuid} without the "
            "guest details this service requests. Unrecognised includes are "
            "ignored upstream rather than rejected, so this is reported "
            "instead of returning partial data as if it were complete."
        ) from exc
    except HospitableError as exc:
        raise HomeAssistantError(
            f"Reservation {reservation_uuid} could not be retrieved. This is "
            "usually temporary; try again shortly."
        ) from exc

    filtered: ServiceResponse = response.serialize_response(
        {"found": payload is not None, "reservation": payload},
        guest_contact=guest_contact_enabled(entry),
    )
    return filtered
