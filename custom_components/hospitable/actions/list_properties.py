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

    runtime = getattr(entry, "runtime_data", None)
    if not isinstance(runtime, dict):
        runtime = {}
    coordinators = runtime.get("coordinators", {})
    if not isinstance(coordinators, dict):
        coordinators = {}
    properties_coordinator = coordinators.get("properties")
    data = getattr(properties_coordinator, "data", None)
    cache: dict[str, HospitableProperty] = data if isinstance(data, dict) else {}

    known: set[str] = {str(pid) for pid in runtime.get("known_property_ids", [])}
    selected: set[str] = {str(pid) for pid in runtime.get("selected_property_ids", [])}

    properties_out: list[dict[str, Any]] = []
    for property_id in sorted(known):
        prop = cache.get(property_id)
        properties_out.append(
            _curate_property(prop, property_id, selected),
        )

    filtered: ServiceResponse = response.serialize_response(
        {"found": True, "properties": properties_out},
        guest_contact=guest_contact,
    )
    return filtered


def _curate_property(
    prop: HospitableProperty | None,
    property_id: str,
    selected: set[str],
) -> dict[str, Any]:
    """Build the curated shape for one property (FR-005, FR-010).

    Args:
        prop: The cached property model, or None for an unselected
            property with no cached data.
        property_id: The property's identifier.
        selected: The set of selected property IDs.

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

    listings = [_curate_listing(listing) for listing in prop.listings]
    return {
        "property_id": prop.property_id,
        "name": prop.name,
        "public_name": prop.public_name,
        "selected": property_id in selected,
        "listings": listings,
    }


def _curate_listing(listing: Any) -> dict[str, Any]:
    """Build the curated shape for one listing (FR-006).

    Co-host dicts are included unfiltered here. The caller
    passes the entire response through ``serialize_response``,
    which walks recursively and delegates co-host filtering
    to ``_filter_co_hosts`` (FR-007, FR-048).

    Args:
        listing: A ``HospitableListing`` model instance.

    Returns:
        A curated listing dictionary.
    """
    co_host_dicts = [
        {
            "user_id": ch.user_id,
            "channel_name": ch.channel_name,
            "name": ch.name,
        }
        for ch in getattr(listing, "co_hosts", ())
    ]
    return {
        "platform": listing.platform,
        "platform_id": listing.platform_id,
        "co_hosts": co_host_dicts,
    }
