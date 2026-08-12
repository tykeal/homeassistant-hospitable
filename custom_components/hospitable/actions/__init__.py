# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Table-driven service registration for Hospitable (FR-005, FR-006).

Services are global to the domain, not per config entry, so registration
is idempotent and removal waits for the LAST loaded entry to unload.

Adapted from the Hostaway reference. Its unload guard reads
``if not hass.data.get(DOMAIN)``; this integration keeps per-entry state
on ``entry.runtime_data``, so the guard counts loaded config entries
instead.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any, NamedTuple

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)

from custom_components.hospitable.actions.helpers import loaded_entries
from custom_components.hospitable.actions.schemas import SEND_MESSAGE_SCHEMA
from custom_components.hospitable.actions.send_message import (
    async_handle_send_message,
)
from custom_components.hospitable.const import DOMAIN

ServiceHandler = Callable[
    [HomeAssistant, ServiceCall], Coroutine[Any, Any, ServiceResponse]
]

SERVICE_SEND_MESSAGE = "send_message"


class ServiceDefinition(NamedTuple):
    """One row of the service registration table."""

    name: str
    schema: vol.Schema
    handler: ServiceHandler
    supports_response: SupportsResponse


SERVICE_DEFINITIONS: tuple[ServiceDefinition, ...] = (
    ServiceDefinition(
        name=SERVICE_SEND_MESSAGE,
        schema=SEND_MESSAGE_SCHEMA,
        handler=async_handle_send_message,
        supports_response=SupportsResponse.ONLY,
    ),
)


BoundHandler = Callable[[ServiceCall], Coroutine[Any, Any, ServiceResponse]]


def _bind(handler: ServiceHandler) -> BoundHandler:
    """Adapt a handler to the signature the service registry expects.

    Args:
        handler: Handler taking Home Assistant and the call.

    Returns:
        A callable taking only the call.
    """

    async def _run(call: ServiceCall) -> ServiceResponse:
        """Invoke the bound handler.

        Args:
            call: The service call.

        Returns:
            The handler's response.
        """
        return await handler(call.hass, call)

    return _run


def async_setup_services(hass: HomeAssistant) -> None:
    """Register every declared service, skipping those already present.

    Args:
        hass: Home Assistant instance.
    """
    for definition in SERVICE_DEFINITIONS:
        if hass.services.has_service(DOMAIN, definition.name):
            continue
        hass.services.async_register(
            DOMAIN,
            definition.name,
            _bind(definition.handler),
            schema=definition.schema,
            supports_response=definition.supports_response,
        )


def async_unload_services(hass: HomeAssistant, *, unloading_entry_id: str) -> None:
    """Remove services once no other entry is still loaded.

    The entry being unloaded is still reported as loaded at the time
    ``async_unload_entry`` runs, so it is excluded explicitly.

    Args:
        hass: Home Assistant instance.
        unloading_entry_id: Entry id currently being unloaded.
    """
    remaining = [
        entry for entry in loaded_entries(hass) if entry.entry_id != unloading_entry_id
    ]
    if remaining:
        return
    for definition in SERVICE_DEFINITIONS:
        hass.services.async_remove(DOMAIN, definition.name)
