# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""The ``hospitable.list_properties`` handler (FR-003 to FR-010).

Returns every known property for the account with curated metadata
including listing co-host identifiers. Served entirely from the
properties coordinator cache with NO additional API request (FR-009).
"""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse

from custom_components.hospitable.actions import response
from custom_components.hospitable.actions.helpers import (
    guest_contact_enabled,
    resolve_config_entry,
)
from custom_components.hospitable.actions.schemas import ATTR_CONFIG_ENTRY_ID
from custom_components.hospitable.api.models import HospitableProperty


async def async_handle_list_properties(
    hass: HomeAssistant, call: ServiceCall
) -> ServiceResponse:
    """Return every known property with curated metadata.

    The response is served from the properties coordinator cache.
    No API request is issued (FR-009).

    Args:
        hass: Home Assistant instance.
        call: The service call.

    Returns:
        A dictionary with key ``properties`` listing every known
        property in curated form.
    """
    entry = resolve_config_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    guest_contact = guest_contact_enabled(entry)

    runtime = getattr(entry, "runtime_data", None) or {}
    coordinators = runtime.get("coordinators", {})
    properties_coordinator = coordinators.get("properties")
    cache: dict[str, HospitableProperty] = (
        getattr(properties_coordinator, "data", None) or {}
    )

    known: set[str] = {str(pid) for pid in runtime.get("known_property_ids", [])}
    selected: set[str] = {str(pid) for pid in runtime.get("selected_property_ids", [])}

    properties_out: list[dict[str, Any]] = []
    for property_id in sorted(known):
        prop = cache.get(property_id)
        entry_out = _curate_property(prop, property_id, selected, guest_contact)
        properties_out.append(entry_out)

    result: ServiceResponse = {
        "found": True,
        "properties": properties_out,  # type: ignore[dict-item]
    }
    return result


def _curate_property(
    prop: HospitableProperty | None,
    property_id: str,
    selected: set[str],
    guest_contact: bool,
) -> dict[str, Any]:
    """Build the curated shape for one property (FR-005, FR-010).

    Args:
        prop: The cached property model, or None for an unselected
            property with no cached data.
        property_id: The property's identifier.
        selected: The set of selected property IDs.
        guest_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        A curated property dictionary.
    """
    if prop is None:
        return {
            "property_id": property_id,
            "name": None,
            "public_name": None,
            "selected": property_id in selected,
            "listings": [],
        }

    listings = [
        _curate_listing(listing, guest_contact=guest_contact)
        for listing in prop.listings
    ]
    return {
        "property_id": prop.property_id,
        "name": prop.name,
        "public_name": prop.public_name,
        "selected": property_id in selected,
        "listings": listings,
    }


def _curate_listing(
    listing: Any,
    *,
    guest_contact: bool,
) -> dict[str, Any]:
    """Build the curated shape for one listing (FR-006).

    Co-hosts are passed through the EXISTING response privacy
    chokepoint (FR-007, FR-048). This is NOT a second filtering
    path: the co-host dicts flow through ``serialize_response``
    which delegates to ``_filter_co_hosts``.

    Args:
        listing: A ``HospitableListing`` model instance.
        guest_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        A curated listing dictionary.
    """
    co_host_dicts = [
        {"user_id": ch.user_id, "channel_name": ch.channel_name, "name": ch.name}
        for ch in getattr(listing, "co_hosts", ())
    ]
    # Pass through the ONE privacy chokepoint (FR-048).
    filtered = response.serialize_response(
        {"co_hosts": co_host_dicts},
        guest_contact=guest_contact,
    )
    return {
        "platform": listing.platform,
        "platform_id": listing.platform_id,
        "co_hosts": filtered.get("co_hosts", []),
    }
