# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Task model and response vocabularies for the Hospitable API.

Defined here rather than in ``api/models`` so that module stays within
the project's file-size budget; ``api.models`` re-exports both names so
the documented import path still works.

The shape below is the LIVE-confirmed one. Three details are load
bearing and are asserted by tests rather than assumed:

- the property association is nested ``property.id``; there is no flat
  ``property_id`` key, and this parser deliberately does not accept one,
  because a permissive reader would hide a future upstream drift;
- there is no ``scheduled_date``: scheduling is ``start_date`` and
  ``end_date`` as offset-aware ISO-8601 strings, plus a separate IANA
  ``timezone`` and an integer ``duration_hours``;
- ``progress_status`` is NULLABLE, and was null on 54 of 153 observed
  tasks, so anything assuming a string breaks on a third of real data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskTypeEntry:
    """One entry from the ``meta.task_types`` vocabulary.

    A task type carries BOTH a label and the service it maps to, which
    is precisely why the two vocabularies must not be interchanged.
    """

    label: str
    service_id: int | None


@dataclass(frozen=True, slots=True)
class TaskVocabularies:
    """The enum vocabularies a ``/tasks`` response carries in ``meta``.

    Labels are read from the response, never hardcoded, because the
    account's own vocabulary is what the user sees in Hospitable
    (FR-033).

    ``task_types`` and ``service_types`` are kept as SEPARATE structures
    with distinct names and DIFFERENT value types so conflating them is
    a type error rather than a silent mislabel. That matters because the
    two tables overlap numerically while disagreeing: ``task_types["5"]``
    is Maintenance with ``service_id`` 8, while ``service_types["5"]`` is
    **Owner**. Looking a task type up in the service table therefore
    yields a WRONG LABEL rather than an error.
    """

    task_types: dict[str, TaskTypeEntry] = field(default_factory=dict)
    service_types: dict[str, str] = field(default_factory=dict)
    assignment_statuses: dict[str, str] = field(default_factory=dict)
    progress_statuses: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_meta(cls, meta: Any) -> TaskVocabularies:
        """Build the vocabularies from a response ``meta`` block.

        Args:
            meta: The response ``meta`` object, of any shape.

        Returns:
            The parsed vocabularies; missing tables become empty rather
            than raising, so an unfamiliar response still yields tasks.
        """
        if not isinstance(meta, dict):
            meta = {}
        task_types: dict[str, TaskTypeEntry] = {}
        raw_task_types = meta.get("task_types")
        if isinstance(raw_task_types, dict):
            for key, value in raw_task_types.items():
                if not isinstance(value, dict):
                    continue
                raw_service = value.get("service_id")
                task_types[str(key)] = TaskTypeEntry(
                    label=str(value.get("label", "")),
                    service_id=(
                        int(raw_service) if isinstance(raw_service, int) else None
                    ),
                )
        return cls(
            task_types=task_types,
            service_types=_label_table(meta.get("service_types")),
            assignment_statuses=_label_table(meta.get("assignment_statuses")),
            progress_statuses=_label_table(meta.get("progress_statuses")),
        )

    def task_type_label(self, task_type: int | None) -> str | None:
        """Return a task type's label from the TASK TYPE table.

        Args:
            task_type: The task's ``task_type`` identifier.

        Returns:
            The label, or ``None`` when the vocabulary omits it.
        """
        if task_type is None:
            return None
        entry = self.task_types.get(str(task_type))
        return entry.label if entry is not None else None

    def service_type_label(self, service_id: int | None) -> str | None:
        """Return a service's label from the SERVICE TYPE table.

        Keyed on ``service_id``, never on ``task_type``: the two
        identifier spaces overlap while disagreeing, so keying on the
        wrong one produces a plausible but wrong label.

        Args:
            service_id: The task's ``service_id`` identifier.

        Returns:
            The label, or ``None`` when the vocabulary omits it.
        """
        if service_id is None:
            return None
        return self.service_types.get(str(service_id))


def _label_table(raw: Any) -> dict[str, str]:
    """Flatten an object-valued vocabulary table to key-to-label.

    Args:
        raw: A ``meta`` vocabulary, of any shape.

    Returns:
        Each key mapped to its label, skipping malformed entries.
    """
    if not isinstance(raw, dict):
        return {}
    return {
        str(key): str(value.get("label", ""))
        for key, value in raw.items()
        if isinstance(value, dict)
    }


def _optional_int(value: Any) -> int | None:
    """Return an integer value, or ``None`` when absent or malformed.

    Args:
        value: A raw payload value.

    Returns:
        The integer, or ``None``.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


@dataclass(frozen=True, slots=True)
class HospitableTask:
    """One Hospitable task (FR-035).

    Three upstream fields are deliberately NOT fields here, following
    the precedent ``HospitableGuest`` set for ``profile_picture``: a
    value with no permitted exposure surface is never read into the
    model at all, so it cannot leak onto an entity attribute, a service
    response, a diagnostic, a log, or an exception path someone forgets
    to guard.

    - ``teammate.name`` is a person's name and is PII (FR-042). The
      opaque ``teammate.id`` is retained.
    - ``note`` is free text a host may have typed anything into, and has
      no consumer in this user story.
    - ``reservation.code`` is guest-adjacent and has no consumer either.
      The opaque ``reservation.id`` is retained because linking a task
      to a reservation is genuinely useful.

    Scoping those to one surface while leaving them parsed and available
    on another is the exact defect shape this project has hit before, so
    the control is placed at the parser instead.
    """

    task_id: str
    name: str | None
    property_id: str
    property_name: str | None
    reservation_id: str | None
    teammate_id: str | None
    task_type: int | None
    service_id: int | None
    task_type_label: str | None
    service_type_label: str | None
    assignment_status: str | None
    assignment_updated_at: str | None
    progress_status: str | None
    start_date: str | None
    end_date: str | None
    timezone: str | None
    duration_hours: int | None

    @classmethod
    def from_api(
        cls, payload: dict[str, Any], vocabularies: TaskVocabularies
    ) -> HospitableTask:
        """Build a task from one API object and the response vocabulary.

        Args:
            payload: One raw task object.
            vocabularies: Vocabularies from the SAME response, so labels
                reflect the account's own configuration.

        Returns:
            The parsed task.
        """
        if not isinstance(payload, dict):
            payload = {}
        # ONLY the nested object is read. A flat ``property_id`` is not
        # accepted even as a fallback: no observed task carried one, and
        # tolerating both shapes would hide upstream drift permanently.
        property_payload = payload.get("property")
        if not isinstance(property_payload, dict):
            property_payload = {}
        reservation = payload.get("reservation")
        if not isinstance(reservation, dict):
            reservation = {}
        teammate = payload.get("teammate")
        if not isinstance(teammate, dict):
            teammate = {}
        assignment = payload.get("task_assignment")
        if not isinstance(assignment, dict):
            assignment = {}

        task_type = _optional_int(payload.get("task_type"))
        service_id = _optional_int(payload.get("service_id"))
        progress = payload.get("progress_status")
        return cls(
            task_id=str(payload.get("id", "")),
            name=_optional_str(payload.get("name")),
            property_id=str(property_payload.get("id", "")),
            property_name=_optional_str(property_payload.get("name")),
            reservation_id=_optional_str(reservation.get("id")),
            teammate_id=_optional_str(teammate.get("id")),
            task_type=task_type,
            service_id=service_id,
            task_type_label=vocabularies.task_type_label(task_type),
            service_type_label=vocabularies.service_type_label(service_id),
            assignment_status=_optional_str(assignment.get("status")),
            assignment_updated_at=_optional_str(assignment.get("updated_at")),
            # Nullable upstream and left null here: substituting a
            # default would report a third of real tasks as started.
            progress_status=_optional_str(progress),
            start_date=_optional_str(payload.get("start_date")),
            end_date=_optional_str(payload.get("end_date")),
            timezone=_optional_str(payload.get("timezone")),
            duration_hours=_optional_int(payload.get("duration_hours")),
        )


def _optional_str(value: Any) -> str | None:
    """Return a string value, or ``None`` when absent.

    Args:
        value: A raw payload value.

    Returns:
        The string, or ``None``.
    """
    return None if value is None else str(value)
