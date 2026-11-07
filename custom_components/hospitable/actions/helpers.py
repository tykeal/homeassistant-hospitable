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
from homeassistant.helpers.httpx_client import get_async_client

from custom_components.hospitable.api.auth import StaticTokenProvider
from custom_components.hospitable.api.client import HospitableApiClient
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_GUEST_CONTACT_DETAILS,
    CONF_TOKEN,
    DEFAULT_GUEST_CONTACT_DETAILS,
    DOMAIN,
)

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


def guest_contact_enabled(entry: ConfigEntry) -> bool:
    """Return whether the guest-contact opt-in is on for this account.

    Args:
        entry: The config entry serving the call.

    Returns:
        True when contact details may be released to a caller.
    """
    return bool(
        entry.options.get(CONF_GUEST_CONTACT_DETAILS, DEFAULT_GUEST_CONTACT_DETAILS)
    )


def read_client(hass: HomeAssistant, entry: ConfigEntry) -> HospitableApiClient:
    """Return the GET-only client the read services use.

    Reusing the entry's own client is the point: it is the base
    ``HospitableApiClient``, which has no ``_post``, so a read service
    physically cannot write. Constructing a fresh one when runtime data
    is unexpectedly absent keeps that same GET-only type.

    Args:
        hass: Home Assistant instance.
        entry: The config entry serving the call.

    Returns:
        A GET-only API client bound to this account's token.
    """
    runtime = getattr(entry, "runtime_data", None)
    if isinstance(runtime, dict):
        client = runtime.get("client")
        if isinstance(client, HospitableApiClient):
            return client
    return HospitableApiClient(
        StaticTokenProvider(str(entry.data[CONF_TOKEN])), get_async_client(hass)
    )


def known_property_ids(entry: ConfigEntry) -> set[str]:
    """Return the property identifiers this account is known to hold.

    Args:
        entry: The config entry serving the call.

    Returns:
        Known property identifiers, empty when runtime data is absent.
    """
    runtime = getattr(entry, "runtime_data", None)
    if not isinstance(runtime, dict):
        return set()
    known = runtime.get("known_property_ids") or []
    selected = runtime.get("selected_property_ids") or []
    return {str(item) for item in [*known, *selected]}


def resolve_property_id(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    property_id: str | None,
    target: dict[str, Any] | None,
) -> str:
    """Resolve the property a service call targets (FR-019).

    Accepts an explicit ``property_id``, a device/entity target, or
    both. When both are supplied and they agree, the call proceeds.
    When they disagree, a ``ServiceValidationError`` is raised
    (FR-017). When neither is supplied, a ``ServiceValidationError``
    is raised (FR-018).

    Args:
        hass: Home Assistant instance.
        entry: The selected config entry.
        property_id: A directly supplied property ID.
        target: Target dict with optional ``entity_id`` and
            ``device_id`` lists, as merged by HA from the service
            call target.

    Returns:
        The resolved property ID.

    Raises:
        ServiceValidationError: The inputs conflict, neither is
            supplied, or the target cannot be resolved.
    """
    from homeassistant.helpers import (
        device_registry as dr_mod,
    )

    from custom_components.hospitable.entity import (
        parse_device_identifier,
    )

    target_property_id = _resolve_target(
        hass,
        entry,
        target or {},
        dr_mod,
        parse_device_identifier,
    )

    if property_id is not None and target_property_id is not None:
        if property_id != target_property_id:
            raise ServiceValidationError(
                f"The property_id '{property_id}' and the "
                f"target device resolve to different "
                f"properties ('{target_property_id}'). "
                "Remove one or correct the mismatch."
            )
        return property_id

    if property_id is not None:
        return property_id

    if target_property_id is not None:
        return target_property_id

    raise ServiceValidationError(
        "Provide a property_id or select a Hospitable device or entity as target."
    )


def _resolve_target(
    hass: HomeAssistant,
    entry: ConfigEntry,
    target: dict[str, Any],
    dr_mod: Any,
    parse_device_identifier: Any,
) -> str | None:
    """Extract a property ID from a target dict.

    Args:
        hass: Home Assistant instance.
        entry: The selected config entry.
        target: Target dict with entity_id / device_id.
        dr_mod: The device_registry module.
        parse_device_identifier: Identifier parser function.

    Returns:
        The property ID, or None when no target is supplied.

    Raises:
        ServiceValidationError: The target is invalid.
    """
    entity_ids = target.get("entity_id")
    device_ids = target.get("device_id")
    if not entity_ids and not device_ids:
        return None

    device_reg = dr_mod.async_get(hass)

    if entity_ids:
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        return _resolve_entity_target(
            hass,
            entry,
            entity_ids[0],
            device_reg,
            parse_device_identifier,
        )

    if isinstance(device_ids, str):
        device_ids = [device_ids]
    dev_list: list[str] = list(device_ids) if device_ids else []
    if not dev_list:
        return None
    return _resolve_device_target(
        entry,
        dev_list[0],
        device_reg,
        parse_device_identifier,
    )


def _resolve_entity_target(
    hass: HomeAssistant,
    entry: ConfigEntry,
    entity_id: str,
    device_reg: Any,
    parse_device_identifier: Any,
) -> str:
    """Resolve a property ID from an entity target.

    Args:
        hass: Home Assistant instance.
        entry: The selected config entry.
        entity_id: The target entity ID.
        device_reg: Device registry instance.
        parse_device_identifier: Identifier parser.

    Returns:
        The resolved property ID.

    Raises:
        ServiceValidationError: The entity cannot be resolved.
    """
    ent_registry = er.async_get(hass)
    ent_entry = ent_registry.async_get(entity_id)
    if ent_entry is None or ent_entry.platform != DOMAIN:
        raise ServiceValidationError(
            f"Entity {entity_id} is not a Hospitable "
            "entity, so it cannot identify a property."
        )
    if ent_entry.config_entry_id != entry.entry_id:
        raise ServiceValidationError(
            f"Entity {entity_id} belongs to a different "
            "Hospitable account than the one selected."
        )
    if ent_entry.device_id is None:
        raise ServiceValidationError(
            f"Entity {entity_id} has no device and cannot identify a property."
        )
    return _resolve_device_target(
        entry,
        ent_entry.device_id,
        device_reg,
        parse_device_identifier,
    )


def _resolve_device_target(
    entry: ConfigEntry,
    device_id: str,
    device_reg: Any,
    parse_device_identifier: Any,
) -> str:
    """Resolve a property ID from a device target.

    Args:
        entry: The selected config entry.
        device_id: The target device ID.
        device_reg: Device registry instance.
        parse_device_identifier: Identifier parser.

    Returns:
        The resolved property ID.

    Raises:
        ServiceValidationError: The device cannot be resolved.
    """
    device_entry = device_reg.async_get(device_id)
    if device_entry is None:
        raise ServiceValidationError(f"Device {device_id} is not registered.")
    if entry.entry_id not in (device_entry.config_entries or set()):
        raise ServiceValidationError(
            f"Device {device_id} belongs to a different "
            "Hospitable account than the one selected."
        )

    namespace = str(entry.data.get(CONF_ACCOUNT_NAMESPACE, ""))

    for identifier in device_entry.identifiers:
        prop_id = parse_device_identifier(
            identifier,
            namespace,
        )
        if prop_id is not None:
            return str(prop_id)

    raise ServiceValidationError(
        f"Device {device_id} is not a Hospitable property device."
    )
