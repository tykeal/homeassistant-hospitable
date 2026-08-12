# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""A real config-entry harness carrying guest identity data (US3).

Shared by the end-to-end entity tests and the privacy log tests so both
drive the SAME wiring: a real ``hass``, a real ``MockConfigEntry``, real
registries, and ``respx``-mocked endpoints. No request is ever made to
the live host.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_GUEST_CONTACT_DETAILS,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from custom_components.hospitable.entity import build_unique_id
from tests.helpers import load_fixture

ACCOUNT = "acct-example-0001"
ZONE = timezone(timedelta(hours=-7))
PROFILE_PICTURE = "https://example.com/guest-avatar.png"

# The harness overrides the shared fixture's generic name and language
# with values distinctive enough for a substring leak check. "Example",
# "Guest" and "en" all occur throughout unrelated log text, so asserting
# on them would produce noise rather than proof.
GUEST_FIRST_NAME = "Zephyrine"
GUEST_LAST_NAME = "Quillfeather"
GUEST_LANGUAGE = "qx-ZZ"

# Every guest value the harness carries, so a leak test can name them
# all rather than sampling. NAMES and LANGUAGE are guest fields too:
# FR-041 keeps every guest field out of the logs, not just the ones the
# entity surface hides. Attribute KEY names such as "guest_first_name"
# are deliberately NOT listed; a key name is not guest data, and the
# entity publishes it by design.
GUEST_SECRETS = (
    GUEST_FIRST_NAME,
    GUEST_LAST_NAME,
    GUEST_LANGUAGE,
    "Example City, Example Region",
    "guest@example.com",
    "+15550101001",
    PROFILE_PICTURE,
    "guest-example-0001",
)


def current_stay(reservation_id: str, property_id: str, guest: Any) -> dict[str, Any]:
    """Build an accepted, mid-stay reservation carrying a guest object.

    Args:
        reservation_id: Reservation identifier to assign.
        property_id: Property the stay belongs to.
        guest: Raw guest object, or ``None`` for no guest.

    Returns:
        A reservation payload occupying the property right now.
    """
    today = datetime.now(ZONE).date()
    arrival = today - timedelta(days=1)
    departure = today + timedelta(days=2)
    payload = dict(load_fixture("reservation_accepted.json")["data"][0])
    payload.update(
        {
            "id": reservation_id,
            "properties": [{"id": property_id}],
            "arrival_date": f"{arrival.isoformat()}T00:00:00-07:00",
            "departure_date": f"{departure.isoformat()}T00:00:00-07:00",
            "check_in": f"{arrival.isoformat()}T16:00:00-07:00",
            "check_out": f"{departure.isoformat()}T11:00:00-07:00",
            "guest": guest,
        }
    )
    return payload


def reservations_payload() -> dict[str, Any]:
    """Build a reservations envelope with a full guest and a null guest.

    Returns:
        A single-page reservations envelope.
    """
    fixture = load_fixture("reservation_with_guest.json")["data"]
    guest = dict(fixture[0]["guest"])
    guest.update(
        {
            "first_name": GUEST_FIRST_NAME,
            "last_name": GUEST_LAST_NAME,
            "language": GUEST_LANGUAGE,
        }
    )
    return {
        "data": [
            current_stay("res-guest-001", "prop-example-001", guest),
            current_stay("res-guest-002", "prop-example-002", None),
        ],
        "meta": {
            "current_page": 1,
            "last_page": 1,
            "path": "http://public.api.hospitable.com/v2/reservations",
            "per_page": 100,
            "total": 2,
        },
    }


def _properties_side_effect(request: httpx.Request) -> httpx.Response:
    """Return the paginated properties fixture for the requested page.

    Args:
        request: The captured properties request.

    Returns:
        The fixture response for the requested page.
    """
    page = request.url.params.get("page", "1")
    fixture = "properties_page2.json" if page == "2" else "properties_page1.json"
    return httpx.Response(200, json=load_fixture(fixture))


def mock_endpoints(respx_router: Any) -> Any:
    """Mock every GET endpoint the entry setup needs.

    Args:
        respx_router: The active respx router.

    Returns:
        The reservations route, so callers can inspect the request.
    """
    respx_router.get(f"{BASE_URL}/properties").mock(side_effect=_properties_side_effect)
    reservations = respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=reservations_payload())
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-001/calendar").mock(
        return_value=httpx.Response(200, json=load_fixture("calendar_prop1.json"))
    )
    respx_router.get(f"{BASE_URL}/properties/prop-example-002/calendar").mock(
        return_value=httpx.Response(200, json=load_fixture("calendar_prop2.json"))
    )
    return reservations


async def setup_guest_entry(hass: Any, *, guest_contact: bool) -> MockConfigEntry:
    """Set up a loaded config entry with the opt-in in a known state.

    Args:
        hass: The Home Assistant test instance.
        guest_contact: Whether the guest-contact opt-in is enabled.

    Returns:
        The loaded config entry.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
            CONF_GUEST_CONTACT_DETAILS: guest_contact,
        },
        unique_id=ACCOUNT,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


def reservation_entity_id(hass: Any, property_id: str) -> str:
    """Return the reservation sensor entity id for a property.

    Args:
        hass: The Home Assistant test instance.
        property_id: Property whose sensor is wanted.

    Returns:
        The registered entity id.
    """
    registry = er.async_get(hass)
    unique_id = build_unique_id(ACCOUNT, property_id, "reservation_status")
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    assert entity_id is not None
    return entity_id
