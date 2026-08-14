# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Task sensors for Hospitable properties.

These are the User Story 4 entities: a per-property next-task sensor and
a per-property task-count sensor, both fed by the tasks coordinator
(FR-032).

No attribute here carries a teammate's personal name, a task note, or a
reservation code. That is not enforced at this surface: none of the
three is a field on ``HospitableTask`` at all, so there is nothing here
to guard (FR-042).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import dt as dt_util

from custom_components.hospitable.api.models import HospitableTask
from custom_components.hospitable.coordinator import HospitablePropertiesCoordinator
from custom_components.hospitable.coordinator_tasks import HospitableTasksCoordinator
from custom_components.hospitable.entity import (
    MAX_CONSECUTIVE_FAILURES,
    HospitableEntity,
    build_device_identifier,
    build_suggested_object_id,
    build_unique_id,
)

_LOGGER = logging.getLogger(__name__)

# Progress buckets for the count sensor's breakdown. ``progress_status``
# is NULLABLE upstream and was null on 54 of 153 observed tasks, so null
# is treated as not-yet-started rather than dropped, which would make
# the breakdown quietly disagree with the count for a third of tasks.
#
# The four buckets cover the full six-value ``progress_status``
# vocabulary documented by ``meta.progress_statuses``. While all tasks
# carry a status from this vocabulary (or null, treated as pending),
# the four bucket counts sum to ``task_count``.
#
# ``cancelled`` is keyed on ``progress_status``, NOT
# ``assignment_status``. Both vocabularies contain ``cancelled`` but
# they are different dimensions: a task can be assignment-cancelled
# (teammate withdrew) while still progress-in_progress (work ongoing).
PENDING_STATUSES = frozenset({"not_started"})
IN_PROGRESS_STATUSES = frozenset({"on_the_way", "arrived", "in_progress"})
COMPLETED_STATUSES = frozenset({"completed"})
CANCELLED_STATUSES = frozenset({"cancelled"})

TASK_DETAIL_ATTRIBUTES = frozenset(
    {
        "task_id",
        "task_type",
        "service_id",
        "service_type",
        "assignment_status",
        "assignment_updated_at",
        "progress_status",
        "start_date",
        "end_date",
        "timezone",
        "duration_hours",
        "reservation_id",
        "teammate_id",
    }
)


def _start_instant(task: HospitableTask) -> datetime | None:
    """Return a task's offset-aware start instant, if parsable.

    Args:
        task: The task to read.

    Returns:
        The start instant, or ``None`` when absent, unparsable, or
        naive. A naive instant is skipped rather than compared, because
        comparing it against an aware ``now`` raises ``TypeError``.
    """
    if task.start_date is None:
        return None
    instant = dt_util.parse_datetime(task.start_date)
    if instant is None or instant.tzinfo is None:
        return None
    return instant


class _HospitableTaskEntity(HospitableEntity, SensorEntity):
    """Base for per-property sensors driven by tasks coordinator data."""

    _entity_key: str

    def __init__(
        self,
        coordinator: HospitableTasksCoordinator,
        *,
        properties_coordinator: HospitablePropertiesCoordinator,
        account_namespace: str,
        property_id: str,
        property_name: str,
    ) -> None:
        """Initialize one task sensor bound to a property.

        Args:
            coordinator: The tasks coordinator feeding this sensor.
            properties_coordinator: Backs the shared presence policy.
            account_namespace: Account namespace for unique ids.
            property_id: The property this sensor reports on.
            property_name: Display name used for the suggested id.
        """
        super().__init__(coordinator)
        self._tasks_coordinator = coordinator
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

    def _tasks(self) -> tuple[HospitableTask, ...]:
        """Return this property's tasks from coordinator data.

        Returns:
            The tasks, or an empty tuple when the property has none.
        """
        data = self.coordinator.data or {}
        return tuple(data.get(self._property_id, ()))

    @property
    def available(self) -> bool:
        """Return availability, degrading only when this property failed.

        A task fetch failure for one property leaves the others fresh, so
        only this property's sensors degrade, and only after
        ``MAX_CONSECUTIVE_FAILURES`` consecutive strikes. Fewer strikes
        retain last-good data (research D-15, FR-057).

        Returns:
            Whether this sensor has trustworthy data.
        """
        if not super().available:
            return False
        if self._property_id not in (self.coordinator.data or {}):
            return False
        return (
            self._tasks_coordinator.property_failure_count(self._property_id)
            < MAX_CONSECUTIVE_FAILURES
        )


class HospitableNextTaskSensor(_HospitableTaskEntity):
    """The soonest upcoming task for one property."""

    _entity_key = "next_task"
    _attr_translation_key = "next_task"
    # Task scheduling detail changes on every poll and has no value as
    # recorder history, so it is never written to long-term storage.
    _unrecorded_attributes = frozenset(TASK_DETAIL_ATTRIBUTES)

    def _next_task(self) -> HospitableTask | None:
        """Return the soonest task starting now or later.

        Returns:
            The soonest upcoming task, or ``None`` when there is none.
        """
        now = dt_util.utcnow()
        upcoming: list[tuple[datetime, HospitableTask]] = []
        for task in self._tasks():
            instant = _start_instant(task)
            if instant is None or instant < now:
                continue
            upcoming.append((instant, task))
        if not upcoming:
            return None
        return min(upcoming, key=lambda pair: pair[0])[1]

    @property
    def native_value(self) -> str | None:
        """Return the soonest upcoming task's TYPE label.

        The label comes from the response's own ``meta.task_types``
        table, never from a hardcoded one, and never from the
        service-type table, which disagrees with it (FR-033).

        Returns:
            The task type label, or ``None`` when nothing is upcoming.
        """
        task = self._next_task()
        return task.task_type_label if task is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the soonest upcoming task's scheduling detail.

        Returns:
            The task's attributes, all ``None`` when nothing is
            upcoming, so the attribute set stays stable rather than
            appearing and vanishing between polls.
        """
        task = self._next_task()
        return {
            "task_id": task.task_id if task is not None else None,
            "task_type": task.task_type if task is not None else None,
            "service_id": task.service_id if task is not None else None,
            "service_type": task.service_type_label if task is not None else None,
            "assignment_status": task.assignment_status if task is not None else None,
            "assignment_updated_at": (
                task.assignment_updated_at if task is not None else None
            ),
            "progress_status": task.progress_status if task is not None else None,
            "start_date": task.start_date if task is not None else None,
            "end_date": task.end_date if task is not None else None,
            "timezone": task.timezone if task is not None else None,
            "duration_hours": task.duration_hours if task is not None else None,
            "reservation_id": task.reservation_id if task is not None else None,
            "teammate_id": task.teammate_id if task is not None else None,
        }


class HospitableTaskCountSensor(_HospitableTaskEntity):
    """How many tasks fall in one property's configured window."""

    _entity_key = "task_count"
    _attr_translation_key = "task_count"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _unrecorded_attributes = frozenset(
        {
            "pending_count",
            "in_progress_count",
            "completed_count",
            "cancelled_count",
        }
    )

    @property
    def native_value(self) -> int:
        """Return the number of tasks in the configured window.

        The count spans EVERY page: a single-page fetch would silently
        under-report (FR-031).

        Returns:
            The task count.
        """
        return len(self._tasks())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return a breakdown of the tasks by progress status.

        The four buckets sum to ``task_count`` while all tasks carry a
        ``progress_status`` from the known six-value vocabulary (or
        null, treated as pending). An unknown status triggers a warning
        and is counted in no bucket.

        Returns:
            Counts per progress bucket.
        """
        tasks = self._tasks()
        all_known = (
            PENDING_STATUSES
            | IN_PROGRESS_STATUSES
            | COMPLETED_STATUSES
            | CANCELLED_STATUSES
        )
        pending = sum(
            1
            for task in tasks
            if task.progress_status is None or task.progress_status in PENDING_STATUSES
        )
        cancelled = sum(
            1 for task in tasks if task.progress_status in CANCELLED_STATUSES
        )
        for task in tasks:
            if (
                task.progress_status is not None
                and task.progress_status not in all_known
            ):
                _LOGGER.warning(
                    "Unknown progress_status %r on task %s",
                    task.progress_status,
                    task.task_id,
                )
        return {
            "pending_count": pending,
            "in_progress_count": sum(
                1 for task in tasks if task.progress_status in IN_PROGRESS_STATUSES
            ),
            "completed_count": sum(
                1 for task in tasks if task.progress_status in COMPLETED_STATUSES
            ),
            "cancelled_count": cancelled,
        }


def build_task_sensors(
    coordinator: HospitableTasksCoordinator,
    properties_coordinator: HospitablePropertiesCoordinator,
    account_namespace: str,
    property_names: dict[str, str],
) -> list[_HospitableTaskEntity]:
    """Build one next-task and one task-count sensor per property.

    Args:
        coordinator: The tasks coordinator feeding the sensors.
        properties_coordinator: Backs the shared presence policy.
        account_namespace: Account namespace for unique ids.
        property_names: Every known property id and display name.

    Returns:
        Every task sensor for the configuration.
    """
    sensors: list[_HospitableTaskEntity] = []
    for property_id, property_name in property_names.items():
        for factory in (HospitableNextTaskSensor, HospitableTaskCountSensor):
            sensors.append(
                factory(
                    coordinator,
                    properties_coordinator=properties_coordinator,
                    account_namespace=account_namespace,
                    property_id=property_id,
                    property_name=property_name,
                )
            )
    return sensors
