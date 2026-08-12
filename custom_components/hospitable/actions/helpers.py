# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Target resolution shared by every Hospitable service (FR-008, FR-044).

Adapted from, not copied from, the Hostaway reference: that integration
keeps per-entry state on ``hass.data[DOMAIN]``, while this one uses
``entry.runtime_data``. Resolution therefore enumerates LOADED config
entries for the domain.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.hospitable.const import DOMAIN

# The reservation UUID is published on reservation sensors under this
# attribute. contracts/services.md and D-10 name it ``reservation_uuid``;
# the shipped attribute is ``reservation_id`` (sensor/reservation.py:51).
RESERVATION_ATTRIBUTE = "reservation_id"


def loaded_entries(hass: HomeAssistant) -> list[ConfigEntry]:
    """Return every loaded Hospitable config entry.

    Args:
        hass: Home Assistant instance.

    Returns:
        The loaded entries, in registry order.
    """
    return [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]


def resolve_config_entry(
    hass: HomeAssistant, config_entry_id: str | None
) -> ConfigEntry:
    """Select the Hospitable account a service call acts on.

    Args:
        hass: Home Assistant instance.
        config_entry_id: Explicitly requested entry id, if any.

    Returns:
        The selected config entry.

    Raises:
        ServiceValidationError: No entry is loaded, the requested entry
            is unknown or not loaded, or the choice is ambiguous.
    """
    entries = loaded_entries(hass)
    if config_entry_id is not None:
        for entry in entries:
            if entry.entry_id == config_entry_id:
                return entry
        raise ServiceValidationError(
            f"No loaded Hospitable account matches config entry "
            f"{config_entry_id}. Check the entry is set up and enabled."
        )
    if not entries:
        raise ServiceValidationError(
            "No Hospitable account is loaded. Set up the integration first."
        )
    if len(entries) > 1:
        raise ServiceValidationError(
            "Several Hospitable accounts are loaded, so config_entry_id is "
            "required to say which one to use."
        )
    return entries[0]


def resolve_reservation_uuid(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    reservation_uuid: str | None,
    entity_id: str | None,
) -> str:
    """Resolve the reservation a service call targets.

    Args:
        hass: Home Assistant instance.
        entry: The selected config entry.
        reservation_uuid: A directly supplied reservation UUID.
        entity_id: An entity that carries a reservation UUID.

    Returns:
        The target reservation UUID.

    Raises:
        ServiceValidationError: Neither or both targets were given, the
            entity does not belong to this integration or account, or it
            carries no reservation.
    """
    if (reservation_uuid is None) == (entity_id is None):
        raise ServiceValidationError(
            "Give exactly one of reservation_uuid or entity_id to say which "
            "reservation to act on."
        )
    if reservation_uuid is not None:
        return reservation_uuid
    registry = er.async_get(hass)
    registry_entry = registry.async_get(str(entity_id))
    if registry_entry is None or registry_entry.platform != DOMAIN:
        raise ServiceValidationError(
            f"Entity {entity_id} is not a Hospitable entity, so it cannot "
            "identify a reservation."
        )
    if registry_entry.config_entry_id != entry.entry_id:
        raise ServiceValidationError(
            f"Entity {entity_id} belongs to a different Hospitable account "
            "than the one selected for this call."
        )
    state = hass.states.get(str(entity_id))
    resolved = state.attributes.get(RESERVATION_ATTRIBUTE) if state else None
    if not resolved:
        raise ServiceValidationError(
            f"Entity {entity_id} is not currently reporting a reservation."
        )
    return str(resolved)


def cached_reservation(entry: ConfigEntry, reservation_uuid: str) -> Any | None:
    """Return a reservation from the entry's coordinator cache.

    Args:
        entry: The selected config entry.
        reservation_uuid: Reservation UUID to look for.

    Returns:
        The cached reservation model, or None when not cached.
    """
    runtime = getattr(entry, "runtime_data", None)
    if not isinstance(runtime, dict):
        return None
    coordinators = runtime.get("coordinators")
    if not isinstance(coordinators, dict):
        return None
    coordinator = coordinators.get("reservations")
    for reservation in getattr(coordinator, "data", None) or []:
        if getattr(reservation, "reservation_id", None) == reservation_uuid:
            return reservation
    return None
