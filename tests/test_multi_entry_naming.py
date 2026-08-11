# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Two accounts owning identically named properties stay distinct.

Account A and account B each own a property whose *display name* is the
same ("Example Shared Villa") but whose immutable property identifier and
account namespace differ. This test observes, through the real entity and
device registries, that:

* the unique IDs are distinct (they are namespaced),
* the devices are distinct (device identifiers are namespaced), and
* the suggested object IDs collide at the name level, so Home Assistant
  disambiguates the second entity by suffixing its entity ID.

The suggested-object-ID case is the interesting one: it derives from the
display name, not from the namespace, so both accounts genuinely propose
the same object ID. The test asserts what HA actually does with that
collision rather than assuming; if HA silently dropped one entity instead
of disambiguating, that would be a real defect for T122.

This asserts no new production behavior. Per Principle XII Exemptions it
is test-only strengthening and carries no red-phase commit.
"""

from __future__ import annotations

from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from custom_components.hospitable.entity import build_unique_id
from tests.helpers import load_fixture, paginator_envelope

_SHARED_NAME = "Example Shared Villa"


def _property_item(property_id: str, name: str) -> dict[str, Any]:
    """Return a property payload with the given id and display name."""
    item = dict(load_fixture("properties_page1.json")["data"][0])
    item["id"] = property_id
    item["name"] = name
    item["public_name"] = name
    return item


def _install_api(respx_router: Any, base_url: str, state: dict[str, Any]) -> None:
    """Serve whichever property page ``state`` currently points at."""

    def _properties(request: httpx.Request) -> httpx.Response:
        """Return the property page currently selected in shared state."""
        return httpx.Response(200, json=state["properties"])

    def _reservations(request: httpx.Request) -> httpx.Response:
        """Return an empty reservation page regardless of the caller."""
        return httpx.Response(
            200,
            json=paginator_envelope(
                [], path="http://public.api.hospitable.com/v2/reservations"
            ),
        )

    respx_router.get(f"{base_url}/properties").mock(side_effect=_properties)
    respx_router.get(f"{base_url}/reservations").mock(side_effect=_reservations)


async def _setup_account(
    hass: Any,
    state: dict[str, Any],
    *,
    namespace: str,
    property_id: str,
    token: str,
) -> MockConfigEntry:
    """Set up one account serving a single identically named property."""
    state["properties"] = paginator_envelope(
        [_property_item(property_id, _SHARED_NAME)]
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: token,
            CONF_ACCOUNT_NAMESPACE: namespace,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={CONF_SELECTED_PROPERTIES: [property_id]},
        unique_id=namespace,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


async def test_identically_named_properties_stay_distinct(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """Same-name properties in two accounts keep distinct ids and devices."""
    from custom_components.hospitable.api.const import BASE_URL

    state: dict[str, Any] = {}
    _install_api(respx_router, BASE_URL, state)

    entry_a = await _setup_account(
        hass,
        state,
        namespace="acct-name-a",
        property_id="prop-a-0001",
        token=f"{synthetic_token}-a",
    )
    entry_b = await _setup_account(
        hass,
        state,
        namespace="acct-name-b",
        property_id="prop-b-0001",
        token=f"{synthetic_token}-b",
    )

    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)

    # Distinct unique IDs: the reservation_status sensors differ by namespace
    # and property id even though the properties share a display name.
    uid_a = build_unique_id("acct-name-a", "prop-a-0001", "reservation_status")
    uid_b = build_unique_id("acct-name-b", "prop-b-0001", "reservation_status")
    assert uid_a != uid_b
    entity_id_a = entity_registry.async_get_entity_id("sensor", DOMAIN, uid_a)
    entity_id_b = entity_registry.async_get_entity_id("sensor", DOMAIN, uid_b)
    assert entity_id_a is not None
    assert entity_id_b is not None

    # Distinct devices: device identifiers are namespaced per account.
    entry_a_entity = entity_registry.async_get(entity_id_a)
    entry_b_entity = entity_registry.async_get(entity_id_b)
    assert entry_a_entity is not None
    assert entry_b_entity is not None
    assert entry_a_entity.device_id is not None
    assert entry_b_entity.device_id is not None
    assert entry_a_entity.device_id != entry_b_entity.device_id

    device_a = device_registry.async_get(entry_a_entity.device_id)
    device_b = device_registry.async_get(entry_b_entity.device_id)
    assert device_a is not None
    assert device_b is not None
    assert (DOMAIN, "acct-name-a_prop-a-0001") in device_a.identifiers
    assert (DOMAIN, "acct-name-b_prop-b-0001") in device_b.identifiers
    assert device_a.identifiers.isdisjoint(device_b.identifiers)

    # Distinct suggested entity IDs: both accounts propose the SAME object id
    # from the shared display name, so exactly one entity keeps the base id
    # and the other is disambiguated with a numeric suffix by Home Assistant.
    # Neither is silently dropped: both are registered and both resolve.
    #
    # Observed behaviour worth recording: because ``_attr_has_entity_name`` is
    # True, the registered object id is derived from the device (property)
    # name and the entity name -- ``example_shared_villa_reservation_status``
    # -- NOT from the ``hospitable_``-prefixed ``build_suggested_object_id``
    # output. The name-level collision between the two accounts is resolved by
    # HA appending ``_2`` to the later entity; both entities survive.
    assert entity_id_a != entity_id_b
    base, suffixed = sorted((entity_id_a, entity_id_b), key=len)
    assert suffixed == f"{base}_2"
    assert base == "sensor.example_shared_villa_reservation_status"

    for entry in (entry_a, entry_b):
        assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
