# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Availability enum sensor for Hospitable properties.

This is the User Story 7 entity: a separate, read-only availability
sensor per property fed by the calendar coordinator. Its state is
``available``, ``booked``, or ``unknown`` — never the Home Assistant
``unavailable`` literal, which is reserved to mean the entity's data
cannot be reached and would conflate a sold night with a broken
integration (FR-058). Nightly rates are converted from integer minor
units to a display float exactly once, here, via
:func:`minor_units_to_float` (FR-060).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from custom_components.hospitable.api.models import (
    HospitableCalendarDay,
    HospitablePropertyCalendar,
)
from custom_components.hospitable.coordinator import (
    HospitableCalendarCoordinator,
    HospitablePropertiesCoordinator,
)
from custom_components.hospitable.entity import (
    HospitableEntity,
    build_device_identifier,
    build_suggested_object_id,
    build_unique_id,
)
from custom_components.hospitable.sensor.helpers import minor_units_to_float

AVAILABILITY_OPTIONS = ["available", "booked", "unknown"]


class HospitableAvailabilitySensor(HospitableEntity, SensorEntity):
    """Enum sensor exposing a property's aggregate availability today."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "availability"
    _attr_options = AVAILABILITY_OPTIONS

    def __init__(
        self,
        coordinator: HospitableCalendarCoordinator,
        *,
        properties_coordinator: HospitablePropertiesCoordinator,
        account_namespace: str,
        property_id: str,
        property_name: str,
    ) -> None:
        """Initialize one availability sensor bound to a property."""
        super().__init__(coordinator)
        self._property_id = property_id
        self._presence_coordinator = properties_coordinator
        self._presence_property_id = property_id
        self._attr_unique_id = build_unique_id(
            account_namespace, property_id, "availability"
        )
        self._attr_suggested_object_id = build_suggested_object_id(
            property_name, "availability"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={build_device_identifier(account_namespace, property_id)}
        )

    def _calendar(self) -> HospitablePropertyCalendar | None:
        """Return this property's calendar from coordinator data."""
        data = self.coordinator.data or {}
        return data.get(self._property_id)

    def _today(self) -> HospitableCalendarDay | None:
        """Return today's calendar day for this property, or ``None``."""
        calendar = self._calendar()
        if calendar is None:
            return None
        today = dt_util.utcnow().date().isoformat()
        for day in calendar.days:
            if day.date == today:
                return day
        return None

    @property
    def available(self) -> bool:
        """Return availability, degrading only when this property failed.

        A calendar fetch failure for a single property leaves no data for
        it while other properties refresh normally, so this property's
        availability sensor is the only entity that degrades (Research
        D-15). The shared three-strike and presence policy still applies.
        """
        if not super().available:
            return False
        return self._property_id in (self.coordinator.data or {})

    @property
    def native_value(self) -> str | None:
        """Return today's availability state, or ``None`` if absent."""
        day = self._today()
        return day.availability if day is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the nightly rate, currency, and a forward window."""
        calendar = self._calendar()
        day = self._today()
        return {
            "nightly_rate": (
                minor_units_to_float(day.price_minor_units, day.currency)
                if day is not None
                else None
            ),
            "currency": day.currency if day is not None else None,
            "min_stay": day.min_stay if day is not None else None,
            "closed_for_checkin": (day.closed_for_checkin if day is not None else None),
            "closed_for_checkout": (
                day.closed_for_checkout if day is not None else None
            ),
            "forward_window": [
                {
                    "date": window_day.date,
                    "availability": window_day.availability,
                    "nightly_rate": minor_units_to_float(
                        window_day.price_minor_units, window_day.currency
                    ),
                    "currency": window_day.currency,
                }
                for window_day in (calendar.days if calendar is not None else ())
            ],
        }


def build_availability_sensors(
    coordinator: HospitableCalendarCoordinator,
    properties_coordinator: HospitablePropertiesCoordinator,
    account_namespace: str,
    property_names: dict[str, str],
) -> list[HospitableAvailabilitySensor]:
    """Build exactly one availability sensor per property."""
    return [
        HospitableAvailabilitySensor(
            coordinator,
            properties_coordinator=properties_coordinator,
            account_namespace=account_namespace,
            property_id=property_id,
            property_name=property_name,
        )
        for property_id, property_name in property_names.items()
    ]
