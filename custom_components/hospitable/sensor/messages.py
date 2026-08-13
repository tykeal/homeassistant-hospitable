# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Message presence sensors for Hospitable properties (US5).

Two per-property entities. The last-message timestamp is ALWAYS
created, because it costs nothing: it reads a field the reservation
poll already returned. The awaiting-host-reply indicator is created
ONLY when its option is on, because it does cost a request per property
per cycle.

Both are ``sensor`` entities. The indicator would read naturally as a
``binary_sensor``, but ``contracts/entities.md`` specifies ``sensor``
and spec 002 introduces no new platform, so a ``binary_sensor`` would
be a platform this integration does not otherwise have. It is also not
strictly binary: an empty thread is genuinely unknown, and a
``binary_sensor`` renders unknown far less clearly.

No attribute here can carry a message body. Not because this module
filters one out, but because ``MessagePresence`` never carries one in
the first place — the same reasoning that keeps ``profile_picture`` off
``HospitableGuest``. The chokepoint in ``actions/response.py`` guards
SERVICE RESPONSES and would not have helped here at all (T138, FR-024,
FR-041).

Nothing here says "unread". The API exposes no read state, so the
indicator reports only who wrote last (FR-037).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from custom_components.hospitable.coordinator import (
    HospitablePropertiesCoordinator,
    HospitableReservationsCoordinator,
)
from custom_components.hospitable.entity import (
    HospitableEntity,
    build_device_identifier,
    build_suggested_object_id,
    build_unique_id,
)
from custom_components.hospitable.services.selection import select_reservation

STATE_AWAITING = "on"
STATE_REPLIED = "off"


class _HospitableMessageEntity(HospitableEntity, SensorEntity):
    """Base for per-property sensors fed by the reservation coordinator."""

    _entity_key: str

    def __init__(
        self,
        coordinator: HospitableReservationsCoordinator,
        *,
        properties_coordinator: HospitablePropertiesCoordinator,
        account_namespace: str,
        property_id: str,
        property_name: str,
    ) -> None:
        """Initialize one message sensor bound to a property.

        Args:
            coordinator: The reservations coordinator feeding this
                sensor. Message presence rides on it rather than on a
                coordinator of its own, because the fetch is driven by
                the reservation the poll just selected.
            properties_coordinator: Backs the shared presence policy.
            account_namespace: Account namespace for unique ids.
            property_id: The property this sensor reports on.
            property_name: Display name used for the suggested id.
        """
        super().__init__(coordinator)
        self._reservations_coordinator = coordinator
        self._property_id = property_id
        self._presence_coordinator = properties_coordinator
        self._presence_property_id = property_id
        self._attr_unique_id = build_unique_id(
            account_namespace, property_id, self._entity_key
        )
        self._attr_suggested_object_id = build_suggested_object_id(
            property_name, self._entity_key
        )
        self._attr_device_info = DeviceInfo(
            identifiers={build_device_identifier(account_namespace, property_id)}
        )


class HospitableLastMessageSensor(_HospitableMessageEntity):
    """When the property's operationally relevant thread last moved."""

    _entity_key = "last_message_at"
    _attr_translation_key = "last_message_at"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Return the reservation's own ``last_message_at`` instant.

        Costs ZERO additional requests: the value arrives on the
        reservation payload the poll already fetched (FR-036, FR-038).

        A property with no reservation, a reservation with a null
        timestamp, and an unparsable timestamp all return ``None``, so
        the sensor reads unknown. None of the three is an error, and
        reporting unavailable would claim the integration had lost
        contact with a property it is polling perfectly well (T134).

        Returns:
            The instant of the last message, or ``None``.
        """
        owned = [
            reservation
            for reservation in (self._reservations_coordinator.data or [])
            if reservation.property_id == self._property_id
        ]
        if not owned:
            return None
        selected, _ = select_reservation(owned, dt_util.utcnow())
        if selected is None or selected.last_message_at is None:
            return None
        instant = dt_util.parse_datetime(selected.last_message_at)
        if instant is None:
            return None
        # A naive instant is tagged UTC EXPLICITLY rather than handed to
        # ``dt_util.as_utc``, which documents that it assumes a naive
        # value is in Home Assistant's configured zone. That assumption
        # is wrong here: every observed value from this endpoint carries
        # a ``Z`` suffix, so a naive one would be a malformed UTC value,
        # not a local one, and reading it as local would shift the
        # timestamp by the installation's offset.
        if instant.tzinfo is None:
            return instant.replace(tzinfo=UTC)
        # An offset-bearing instant is normalised rather than passed
        # through, so the value this entity reports is UTC regardless of
        # which offset the payload happened to use.
        return dt_util.as_utc(instant)


class HospitableAwaitingHostReplySensor(_HospitableMessageEntity):
    """Whether the property's guest wrote the most recent message.

    NOT a read receipt, and never described as one. The upstream API
    exposes no read state at all, so this cannot know whether anybody
    has seen the message in the Hospitable UI, the mobile app, or any
    other client (FR-037).
    """

    _entity_key = "awaiting_host_reply"
    _attr_translation_key = "awaiting_host_reply"
    _attr_device_class = SensorDeviceClass.ENUM
    # A guest-message timestamp changes with the conversation and has no
    # value as long-term recorder history.
    _unrecorded_attributes = frozenset({"last_guest_message_at"})

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the indicator and declare its enum options.

        ``_attr_options`` is set per instance rather than as a class
        attribute because the base class declares it as an INSTANCE
        variable; overriding it with a class variable is a mypy error,
        and a bare class-level list is a shared-mutable-state warning.

        Args:
            *args: Forwarded to the shared message entity base.
            **kwargs: Forwarded to the shared message entity base.
        """
        super().__init__(*args, **kwargs)
        self._attr_options = [STATE_AWAITING, STATE_REPLIED]

    @property
    def native_value(self) -> str | None:
        """Return ``on``, ``off``, or ``None`` for an unknown state.

        Unknown covers a thread that has not been fetched yet, a thread
        that is empty, and a sender label nobody recognises. Reporting
        ``off`` for any of them would assert that the host has replied,
        which none of them supports (T137).

        Returns:
            The indicator state, or ``None``.
        """
        presence = self._reservations_coordinator.message_presence.get(
            self._property_id
        )
        if presence is None or presence.awaiting_host_reply is None:
            return None
        return STATE_AWAITING if presence.awaiting_host_reply else STATE_REPLIED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return when the guest last wrote, and nothing else.

        There is deliberately no body, no sender identity, and no
        message count here. ``MessagePresence`` carries none of them, so
        this cannot expose one even by mistake (T138, FR-024, FR-041).

        Returns:
            The single supporting attribute, ``None`` when unknown, so
            the attribute set stays stable across polls.
        """
        presence = self._reservations_coordinator.message_presence.get(
            self._property_id
        )
        return {
            "last_guest_message_at": (
                presence.last_guest_message_at if presence is not None else None
            )
        }


def build_message_sensors(
    coordinator: HospitableReservationsCoordinator,
    properties_coordinator: HospitablePropertiesCoordinator,
    account_namespace: str,
    property_names: dict[str, str],
    *,
    awaiting_enabled: bool,
) -> list[_HospitableMessageEntity]:
    """Build the message presence sensors for every known property.

    Args:
        coordinator: The reservations coordinator feeding the sensors.
        properties_coordinator: Backs the shared presence policy.
        account_namespace: Account namespace for unique ids.
        property_names: Every known property id and display name.
        awaiting_enabled: Whether the opt-in indicator was enabled. When
            false the indicator is not built at all, so it is absent
            rather than present-and-empty (FR-037, FR-038a).

    Returns:
        Every message sensor for the configuration.
    """
    factories: list[type[_HospitableMessageEntity]] = [HospitableLastMessageSensor]
    if awaiting_enabled:
        factories.append(HospitableAwaitingHostReplySensor)
    return [
        factory(
            coordinator,
            properties_coordinator=properties_coordinator,
            account_namespace=account_namespace,
            property_id=property_id,
            property_name=property_name,
        )
        for property_id, property_name in property_names.items()
        for factory in factories
    ]
