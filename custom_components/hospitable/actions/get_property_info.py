# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""The ``hospitable.get_property_info`` handler (FR-027, FR-028, FR-013).

The RAW property payload is returned rather than the coordinator's
model, because the model drops the per-listing ``co_hosts`` array that
FR-013 exists to let an operator discover. Reading the cache would be
cheaper and would answer the wrong question.

Scope note on privacy: FR-047 governs GUEST data. A listing carries the
OPERATOR's own channel contact fields (``platform_email``,
``platform_picture``), which belong to the person making the call and
are the point of the service. They are therefore not filtered, and that
is a deliberate scope decision rather than an oversight — FR-046 asks
for each surface to be named, so this one is named.
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
)
from custom_components.hospitable.actions.schemas import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_PROPERTY_ID,
)
from custom_components.hospitable.api.exceptions import (
    HospitableError,
    HospitableIncludeMissingError,
)


async def async_handle_get_property_info(
    hass: HomeAssistant, call: ServiceCall
) -> ServiceResponse:
    """Return one property's details, listings, and co-hosts.

    Args:
        hass: Home Assistant instance.
        call: The service call.

    Returns:
        The property, filtered through the shared serialiser.

    Raises:
        HomeAssistantError: The upstream request failed, or the
            listings include was not honoured.
    """
    entry = resolve_config_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    property_id = str(call.data[ATTR_PROPERTY_ID])
    client = read_client(hass, entry)
    try:
        payloads = await client.get_property_payloads()
    except HospitableIncludeMissingError as exc:
        raise HomeAssistantError(
            "Hospitable returned properties without the listings this "
            "service requests. Unrecognised includes are ignored upstream "
            "rather than rejected, so this is reported instead of "
            "returning partial data as if it were complete."
        ) from exc
    except HospitableError as exc:
        raise HomeAssistantError(
            f"Property {property_id} could not be retrieved. This is "
            "usually temporary; try again shortly."
        ) from exc

    match: dict[str, Any] | None = next(
        (item for item in payloads if str(item.get("id")) == property_id), None
    )
    filtered: ServiceResponse = response.serialize_response(
        {"found": match is not None, "property": match},
        guest_contact=guest_contact_enabled(entry),
    )
    return filtered
