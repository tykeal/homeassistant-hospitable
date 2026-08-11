# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""End-to-end evidence for SC-010's zero-collision guarantee.

Five config entries are set up through a real ``hass`` with ``respx``
serving the same two properties to every account. Because the mocked
Hospitable API cannot distinguish the accounts by token (the auth header
is redacted before it reaches the wire), all five accounts deliberately
own the *identical* property identifiers. The only thing that keeps their
entity unique IDs apart is the account namespace, so this is the worst
case for collisions and therefore the strongest evidence for SC-010: if
namespacing were not wired through to the entity registry, the fifth
entry would collide with the first.

This asserts no new production behavior; US1 already namespaces every
unique ID by construction. Per Principle XII Exemptions it is a
test-only strengthening that records evidence for a stated success
criterion, so it carries no red-phase commit.
"""

from __future__ import annotations

from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_TOKEN
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    DOMAIN,
)
from tests.helpers import load_fixture, paginator_envelope

_ACCOUNT_NAMESPACES = (
    "acct-multi-0001",
    "acct-multi-0002",
    "acct-multi-0003",
    "acct-multi-0004",
    "acct-multi-0005",
)
_PROPERTY_IDS = ("prop-example-001", "prop-example-002")


def _properties_envelope() -> dict[str, Any]:
    """Return a single-page envelope holding both shared properties."""
    items = [
        load_fixture("properties_page1.json")["data"][0],
        load_fixture("properties_page2.json")["data"][0],
    ]
    return paginator_envelope(items)


def _empty_reservations_envelope() -> dict[str, Any]:
    """Return an empty reservations page (no stays in the window)."""
    return paginator_envelope(
        [], path="http://public.api.hospitable.com/v2/reservations"
    )


def _install_shared_api(respx_router: Any, base_url: str) -> None:
    """Serve identical properties and reservations to every account."""

    def _properties(request: httpx.Request) -> httpx.Response:
        """Return the shared property page regardless of the caller."""
        return httpx.Response(200, json=_properties_envelope())

    def _reservations(request: httpx.Request) -> httpx.Response:
        """Return an empty reservation page regardless of the caller."""
        return httpx.Response(200, json=_empty_reservations_envelope())

    respx_router.get(f"{base_url}/properties").mock(side_effect=_properties)
    respx_router.get(f"{base_url}/reservations").mock(side_effect=_reservations)


async def test_five_accounts_have_zero_unique_id_collisions(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """Five namespaced accounts register with zero unique-ID collisions."""
    from custom_components.hospitable.api.const import BASE_URL

    _install_shared_api(respx_router, BASE_URL)

    entries: list[MockConfigEntry] = []
    for index, namespace in enumerate(_ACCOUNT_NAMESPACES):
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_TOKEN: f"{synthetic_token}-{index}",
                CONF_ACCOUNT_NAMESPACE: namespace,
                CONF_NAMESPACE_SOURCE: "account",
            },
            options={CONF_SELECTED_PROPERTIES: list(_PROPERTY_IDS)},
            unique_id=namespace,
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        entries.append(entry)

    entity_registry = er.async_get(hass)

    all_unique_ids: list[str] = []
    per_entry_counts: list[int] = []
    for entry in entries:
        registry_entries = er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        )
        assert registry_entries, "each entry must register entities"
        entry_unique_ids = [item.unique_id for item in registry_entries]
        per_entry_counts.append(len(entry_unique_ids))
        all_unique_ids.extend(entry_unique_ids)

    # Every account produced the same shape (same properties, same sensors).
    assert len(set(per_entry_counts)) == 1
    assert per_entry_counts[0] > 0

    # The heart of SC-010: no unique ID is shared by any two entities, even
    # though every account owns identically identified properties.
    assert len(all_unique_ids) == len(set(all_unique_ids))
    assert len(all_unique_ids) == per_entry_counts[0] * len(_ACCOUNT_NAMESPACES)

    # Each namespace prefixes exactly its own entities and no others.
    for namespace in _ACCOUNT_NAMESPACES:
        owned = [uid for uid in all_unique_ids if uid.startswith(f"{namespace}_")]
        assert len(owned) == per_entry_counts[0]

    for entry in entries:
        assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
