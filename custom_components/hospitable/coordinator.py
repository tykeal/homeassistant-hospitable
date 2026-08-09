# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Data coordinator classes for Hospitable polling domains."""

from __future__ import annotations


class HospitableReservationsCoordinator:
    """Coordinator for reservation data keyed by property identifier."""

    default_minutes = 5
    floor_minutes = 1


class HospitablePropertiesCoordinator:
    """Coordinator for property data keyed by property identifier."""

    default_minutes = 60
    floor_minutes = 15


class HospitableCalendarCoordinator:
    """Coordinator for calendar data keyed by property identifier."""

    default_minutes = 60
    floor_minutes = 15
