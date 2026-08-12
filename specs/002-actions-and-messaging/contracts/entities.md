<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract: Entity Surface (Spec 002 Additions)

**Feature**: [../spec.md](../spec.md) |
**Data model**: [../data-model.md](../data-model.md)

This document defines entity changes introduced by spec 002. Spec
001's [entities.md](../../001-hospitable-ha-integration/contracts/entities.md)
remains authoritative for the base entity surface.

## Changes to spec 001 entity contract

### Service registration statement (MODIFIED)

Spec 001 stated: "No Home Assistant services are registered."

**Spec 002 replaces this with**: Five Home Assistant services are
registered (`send_message`, `get_messages`, `find_reservation`,
`get_reservations`, `get_property_info`). Registration and removal
follow the table-driven pattern described in
[contracts/services.md](./services.md).

### `reservation_status` sensor (EXTENDED)

The reservation status sensor gains new attributes:

| Attribute | Type | Unrecorded | Default-exposed | Opt-in |
| --- | --- | --- | --- | --- |
| `reservation_uuid` | `str` | No | Yes | — |
| `guest_first_name` | `str \| None` | Yes | Yes | — |
| `guest_last_name` | `str \| None` | Yes | Yes | — |
| `guest_location` | `str \| None` | Yes | Yes | — |
| `guest_language` | `str \| None` | Yes | Yes | — |
| `guest_email` | `str \| None` | Yes | No | `guest_contact_details` option |
| `guest_phone_numbers` | `list[str] \| None` | Yes | No | `guest_contact_details` option |

All guest attributes are **unrecorded** — they exist in entity state
memory only and are never written to the recorder database or
captured in backups (FR-039e).

`reservation_uuid` is NOT unrecorded — it is operational data needed
for the service target pattern and is safe to persist.

**Backward compatibility**: All new attributes are additive. Existing
automations that do not reference these attributes are unaffected.
Guest attributes report `None` when no guest data is available.

## New entities

All new entities follow the existing spec 001 conventions for
identifiers:

| Contract | Format |
| --- | --- |
| Unique ID | `<account_namespace>_<property_id>_<entity_key>` |
| Suggested object ID | `sensor.hospitable_<property_slug>_<entity_key>` |

### `last_message_at` sensor

| Property | Value |
| --- | --- |
| Entity key | `last_message_at` |
| Platform | `sensor` |
| Device class | `timestamp` |
| State class | None |
| State | ISO timestamp or `None` |
| Source | `HospitableReservation.last_message_at` on the operationally relevant reservation |
| Extra API calls | Zero — derived from existing polled data (FR-038) |
| Phase | US5 |

### `awaiting_host_reply` sensor

| Property | Value |
| --- | --- |
| Entity key | `awaiting_host_reply` |
| Platform | `sensor` |
| State | `on` / `off` / `None` |
| Created | ONLY when `awaiting_host_reply` option is enabled |
| Source | Most recent message's `sender_type` from `GET /reservations/{uuid}/messages` |
| Extra API calls | One per property per reservation poll cycle (when enabled) |
| Phase | US5 |
| Unrecorded attributes | `last_guest_message_at` |

**Description MUST state**: "Indicates whether the most recent message
in the reservation thread was sent by the guest. This is NOT a read
receipt — it cannot detect messages read in other clients."

### `next_task` sensor

| Property | Value |
| --- | --- |
| Entity key | `next_task` |
| Platform | `sensor` |
| State | Task type label of soonest upcoming task, or `None` |
| Attributes | `task_type` (int), `service_type` (str), `assignment_status`, `assignment_updated_at`, `progress_status`, `start_date`, `end_date`, `timezone`, `duration_hours`, `task_id`, `reservation_id`, `teammate_id` |
| Phase | US4 |

### `task_count` sensor

| Property | Value |
| --- | --- |
| Entity key | `task_count` |
| Platform | `sensor` |
| State class | `measurement` |
| State | Integer count |
| Attributes | `pending_count`, `in_progress_count`, `completed_count` |
| Phase | US4 |

## Platform scope (updated)

**Sensor only.** Spec 002 does not introduce any new platform. All new
entities are sensors. The sensor platform is extended with four new
entity keys per property.

## Device scope (unchanged)

One device per selected property. No new devices are introduced.
