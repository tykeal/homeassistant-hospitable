# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for table-driven service registration (T026-T028).

Registration follows the Hostaway reference: one declarative table, an
idempotent ``hass.services.has_service()`` guard, and removal only when
the LAST config entry unloads (FR-005, FR-006).

Observed discrepancy, reported not silently reconciled: this integration
stores per-entry state on ``entry.runtime_data``, NOT on
``hass.data[DOMAIN]``. The Hostaway unload guard
``if not hass.data.get(DOMAIN)`` therefore cannot be copied verbatim;
T028 counts loaded config entries instead.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from tests.actions.conftest import (
    ACCOUNT_NAMESPACE,
    SECOND_ACCOUNT_NAMESPACE,
    SECOND_TOKEN,
)

EXPECTED_SERVICES = {
    "send_message",
    "get_messages",
    "find_reservation",
    "get_reservations",
    "get_property_info",
}


def test_registration_table_is_declarative() -> None:
    """Every service is declared once in a single registration table."""
    from homeassistant.core import SupportsResponse

    from custom_components.hospitable.actions import (
        SERVICE_DEFINITIONS,
    )

    names = [definition.name for definition in SERVICE_DEFINITIONS]

    assert "send_message" in names
    assert len(names) == len(set(names)), "duplicate service in the table"
    for definition in SERVICE_DEFINITIONS:
        assert definition.schema is not None, definition.name
        assert definition.handler is not None, definition.name
        assert definition.supports_response is SupportsResponse.ONLY, definition.name


def test_all_five_services_are_declared_with_their_response_mode() -> None:
    """All five services sit in the one table, each response-only.

    Every service this integration exposes returns structured data and
    fires no event, so ``SupportsResponse.ONLY`` is asserted per row
    rather than assumed for the table as a whole.
    """
    from homeassistant.core import SupportsResponse

    from custom_components.hospitable.actions import (
        SERVICE_DEFINITIONS,
    )

    by_name = {definition.name: definition for definition in SERVICE_DEFINITIONS}

    assert set(by_name) == EXPECTED_SERVICES
    for name, definition in by_name.items():
        assert definition.supports_response is SupportsResponse.ONLY, name


async def test_setup_registers_all_five_services(hass: Any) -> None:
    """Setting up services puts all five on the service bus."""
    from custom_components.hospitable.actions import async_setup_services
    from custom_components.hospitable.const import DOMAIN

    async_setup_services(hass)

    for name in sorted(EXPECTED_SERVICES):
        assert hass.services.has_service(DOMAIN, name), name


async def test_all_five_services_go_with_the_last_entry(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """Unloading the last entry removes every service, not just one."""
    from custom_components.hospitable.const import DOMAIN

    entry = await loaded_config_entry_factory(hass)
    for name in sorted(EXPECTED_SERVICES):
        assert hass.services.has_service(DOMAIN, name), name

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    for name in sorted(EXPECTED_SERVICES):
        assert not hass.services.has_service(DOMAIN, name), name


async def test_setup_registers_every_service_in_the_table(hass: Any) -> None:
    """Setup registers exactly the services the table declares."""
    from custom_components.hospitable.actions import (
        SERVICE_DEFINITIONS,
        async_setup_services,
    )
    from custom_components.hospitable.const import DOMAIN

    async_setup_services(hass)

    for definition in SERVICE_DEFINITIONS:
        assert hass.services.has_service(DOMAIN, definition.name), definition.name


async def test_registration_is_idempotent(hass: Any) -> None:
    """Registering twice does not replace the already-registered handler."""
    from custom_components.hospitable.actions import (
        async_setup_services,
    )
    from custom_components.hospitable.const import DOMAIN

    async_setup_services(hass)
    first = hass.services.async_services_for_domain(DOMAIN)["send_message"]
    async_setup_services(hass)
    second = hass.services.async_services_for_domain(DOMAIN)["send_message"]

    assert first is second


def test_registration_guard_is_an_explicit_has_service_check() -> None:
    """The idempotency guard is an explicit ``has_service`` call."""
    from pathlib import Path

    from custom_components.hospitable.actions import (
        async_setup_services,
    )
    from tests.helpers.ast_isolation import scan_module

    assert async_setup_services is not None
    facts = scan_module(Path("custom_components/hospitable/actions/__init__.py"))

    assert "has_service" in facts.attribute_names


async def test_services_survive_until_the_last_entry_unloads(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """Services persist while any entry is loaded and go with the last."""
    from custom_components.hospitable.const import DOMAIN

    first = await loaded_config_entry_factory(hass)
    assert hass.services.has_service(DOMAIN, "send_message")

    second = await loaded_config_entry_factory(
        hass, token=SECOND_TOKEN, account=SECOND_ACCOUNT_NAMESPACE
    )
    assert first.unique_id == ACCOUNT_NAMESPACE
    assert second.unique_id == SECOND_ACCOUNT_NAMESPACE
    assert hass.services.has_service(DOMAIN, "send_message")

    assert await hass.config_entries.async_unload(first.entry_id)
    await hass.async_block_till_done()
    assert hass.services.has_service(DOMAIN, "send_message"), (
        "services must remain while another entry is still loaded"
    )

    assert await hass.config_entries.async_unload(second.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, "send_message"), (
        "services must be removed when the last entry unloads"
    )
