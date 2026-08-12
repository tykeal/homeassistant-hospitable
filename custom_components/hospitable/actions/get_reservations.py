# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""The ``hospitable.get_reservations`` service handler (FR-026, FR-028).

Two different answers are kept apart on purpose:

* ``found: false`` — this account does not hold that property. Nothing
  was requested upstream, because there was nothing to request.
* ``found: true`` with an empty list — the property is real and has no
  bookings in the window.

Collapsing them would leave a caller unable to tell a typo in a property
id from a genuinely quiet week.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from custom_components.hospitable.actions import response
from custom_components.hospitable.actions.helpers import (
    guest_contact_enabled,
    known_property_ids,
    read_client,
    resolve_config_entry,
)
from custom_components.hospitable.actions.schemas import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_PROPERTY_ID,
)
from custom_components.hospitable.api.exceptions import (
    HospitableError,
    HospitableIncludeMissingError,
)
from custom_components.hospitable.const import (
    CONF_LOOKAHEAD_DAYS,
    CONF_LOOKBACK_DAYS,
)
from custom_components.hospitable.services.window import (
    LOOKAHEAD_DEFAULT,
    LOOKBACK_DEFAULT,
)

# SINGULAR guest. Plural `guests` is silently ignored upstream.
RESERVATION_INCLUDE = "guest,properties"


async def async_handle_get_reservations(
    hass: HomeAssistant, call: ServiceCall
) -> ServiceResponse:
    """Return one property's reservations within the configured window.

    Args:
        hass: Home Assistant instance.
        call: The service call.

    The queried window matches the one the reservation coordinator
    polls, so the service and the entities describe the same span of
    time.

    Returns:
        The reservations, filtered through the shared serialiser.

    Raises:
        HomeAssistantError: The upstream request failed, or a requested
            include was not honoured.
    """
    entry = resolve_config_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    property_id = str(call.data[ATTR_PROPERTY_ID])
    guest_contact = guest_contact_enabled(entry)
    if property_id not in known_property_ids(entry):
        return _not_found(property_id, guest_contact=guest_contact)

    today = dt_util.utcnow().date()
    start = today - timedelta(
        days=int(entry.options.get(CONF_LOOKBACK_DAYS, LOOKBACK_DEFAULT))
    )
    end = today + timedelta(
        days=int(entry.options.get(CONF_LOOKAHEAD_DAYS, LOOKAHEAD_DEFAULT))
    )
    client = read_client(hass, entry)
    try:
        payloads = await client.get_reservation_payloads(
            [property_id], start, end, include=RESERVATION_INCLUDE
        )
    except HospitableIncludeMissingError as exc:
        raise HomeAssistantError(
            f"Hospitable returned reservations for property {property_id} "
            "without the guest details this service requests. Unrecognised "
            "includes are ignored upstream rather than rejected, so this is "
            "reported instead of returning partial data as if it were "
            "complete."
        ) from exc
    except HospitableError as exc:
        raise HomeAssistantError(
            f"Reservations for property {property_id} could not be "
            "retrieved. This is usually temporary; try again shortly."
        ) from exc

    filtered: ServiceResponse = response.serialize_response(
        {"found": True, "property_id": property_id, "reservations": payloads},
        guest_contact=guest_contact,
    )
    return filtered


def _not_found(property_id: str, *, guest_contact: bool) -> ServiceResponse:
    """Build the unknown-property response.

    Args:
        property_id: The property that was asked for.
        guest_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        A ``found: false`` response, built through the chokepoint like
        every other response.
    """
    empty: ServiceResponse = response.serialize_response(
        {"found": False, "property_id": property_id, "reservations": []},
        guest_contact=guest_contact,
    )
    return empty
