<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Data Model: Actions and Messaging

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) |
**Research**: [research.md](./research.md)

**Date**: 2026-08-12

## Scope

This describes the new and modified domain models, new entities, and
config entry changes introduced by spec 002. It does not repeat spec
001 models that remain unchanged.

## New domain models

### `HospitableMessage`

Built from an item of `GET /reservations/{uuid}/messages` response
`data` array.

| Field | Type | Source key | Tier | Notes |
| --- | --- | --- | --- | --- |
| `message_id` | `int` | `id` | CONFIRMED-BY-TEST | |
| `platform` | `str` | `platform` | CONFIRMED-BY-TEST | |
| `conversation_id` | `str` | `conversation_id` | CONFIRMED-BY-TEST | |
| `body` | `str` | `body` | CONFIRMED-BY-TEST | NEVER logged or stored in diagnostics |
| `content_type` | `str` | `content_type` | CONFIRMED-BY-TEST | |
| `sender_type` | `str` | `sender_type` | CONFIRMED-BY-TEST | Key for awaiting-host-reply derivation |
| `sender_role` | `str \| None` | `sender_role` | CONFIRMED-BY-TEST | |
| `sender` | `dict[str, Any] \| None` | `sender` | CONFIRMED-BY-TEST | Opaque; may carry guest identity and contact fields. Never logged, and never returned in a service response — the response chokepoint strips it and keeps only `sender_type`/`sender_role` (FR-047a) |
| `created_at` | `str` | `created_at` | CONFIRMED-BY-TEST | ISO 8601 timestamp |
| `attachments` | `list[dict[str, Any]]` | `attachments` | CONFIRMED-BY-TEST | |
| `source` | `str \| None` | `source` | CONFIRMED-BY-TEST | |

**Deliberately absent**: `reactions`, `integration`,
`sent_reference_id`, `author` — not needed for any FR in this spec.

`sent_reference_id` IS present on read messages: it appears in the
CONFIRMED-BY-TEST key list for `GET /reservations/{uuid}/messages` in
[contracts/upstream-requests.md](contracts/upstream-requests.md). It is
deliberately not modelled because no FR needs it, not because its
presence is in doubt. What remains UNVERIFIED is whether the 202
response body of a SEND carries it — a different question, tracked as
OQ-001, which no read-only probe can answer.

### `HospitableGuest`

Built from the `guest` key on a reservation response when
`include=guest` is specified.

| Field | Type | Source key | Tier | Notes |
| --- | --- | --- | --- | --- |
| `guest_id` | `str` | `id` | CONFIRMED-BY-TEST | |
| `first_name` | `str` | `first_name` | CONFIRMED-BY-TEST | 29/29 populated |
| `last_name` | `str \| None` | `last_name` | CONFIRMED-BY-TEST | 28/29 populated |
| `email` | `str \| None` | `email` | CONFIRMED-BY-TEST | 4/29 populated; opt-in only |
| `phone_numbers` | `list[str]` | `phone_numbers` | CONFIRMED-BY-TEST | 22/29 populated; opt-in only |
| `location` | `str \| None` | `location` | CONFIRMED-BY-TEST | 19/29 populated |
| `language` | `str \| None` | `language` | CONFIRMED-BY-TEST | 3 distinct values observed |
| `profile_picture` | `str \| None` | `profile_picture` | CONFIRMED-BY-TEST | 27/29; NEVER exposed as entity attribute |

All fields are PII. `profile_picture` is parsed into the model for
validation completeness but is never surfaced on ANY exposure surface
— not as an entity attribute (FR-039d), not in a service response
(FR-047), not in logs or diagnostics (FR-041, FR-042). `email` and
`phone_numbers` are surfaced only where the guest-contact-details
option is enabled, on both the attribute surface (FR-039c) and the
service-response surface (FR-047). Surface-by-surface enumeration is
deliberate: a control scoped to one surface does not protect another
(FR-046).

### `HospitableTask`

Built from an item of `GET /tasks` response `data` array.

| Field | Type | Source key | Tier | Notes |
| --- | --- | --- | --- | --- |
| `task_id` | `int` | `id` | CONFIRMED-BY-TEST | |
| `property_id` | `str` | UNRESOLVED — see below | Presence CONFIRMED-BY-TEST; exact key UNVERIFIED | Association key |
| `task_type` | `int` | `task_type` | CONFIRMED-BY-TEST | 1-5; maps via meta vocabulary |
| `service_id` | `int` | `service_id` | CONFIRMED-BY-TEST | 1-8; NOT interchangeable with task_type |
| `assignment_status` | `str` | `assignment_status` | CONFIRMED-BY-TEST | From meta vocabulary |
| `progress_status` | `str` | `progress_status` | CONFIRMED-BY-TEST | From meta vocabulary |
| `scheduled_date` | `str` | `scheduled_date` | CONFIRMED-BY-TEST | ISO date |
| `task_type_label` | `str` | derived from `meta.task_types` | DERIVED | Human-readable; not an upstream field |
| `service_type_label` | `str` | derived from `meta.service_types` | DERIVED | Human-readable; not an upstream field |

**On tiers**: DERIVED is not an evidence tier and does not claim
upstream confirmation. These two labels are computed by the
integration by looking a code up in the corresponding meta vocabulary.
What is CONFIRMED-BY-TEST is that the vocabularies exist in `meta` and
that the two are distinct (Maintenance is task_type 5 but service_id
8). The lookup itself is our code, so it is verified by our tests, not
by the API.

**UNRESOLVED — the property association key**: an earlier revision
recorded the source as "`property_id` or `property.id`" while tiering
it CONFIRMED-BY-TEST. Those cannot both be true: an unresolved
alternation is not a confirmed observation. The task payload is known
to associate each task with a property, but which of the two shapes it
uses has NOT been pinned down from a captured response. The
implementation MUST read whichever key the recorded `/tasks` fixture
actually contains and MUST NOT accept both silently, since a
permissive reader would hide the answer permanently. Resolving this
costs one look at the fixture during US4 and no additional API call.

**Deliberately absent**: assignee details (PII), notes (may contain
PII), custom fields. Only operational status fields are modelled.

## Modified domain models

### `HospitableReservation` (extended)

The existing reservation model gains:

| Field | Type | Source key | Tier | Notes |
| --- | --- | --- | --- | --- |
| `guest` | `HospitableGuest \| None` | `guest` | CONFIRMED-BY-TEST | Present only with `include=guest`; null when no guest data |
| `last_message_at` | `str \| None` | `last_message_at` | CONFIRMED-BY-TEST | Already present on base payload (21 keys) |

`last_message_at` was already present in the API response but not
previously modelled because spec 001 had no use for it.

**No `platform` field is added.** An earlier revision of this document
listed one. It would have been a duplicate: `HospitableReservation`
already declares `channel: str | None`
(`custom_components/hospitable/api/models.py:173`) and `from_api`
populates it from `payload.get("platform")` (same file, in the
positional construction at roughly line 218), with
`channel_confirmation` holding `platform_id`. Verified against source.
The FR-013 Airbnb check MUST read the existing `channel` field.

Because `channel` is `str | None`, the Airbnb check MUST treat `None`
as "not resolved as Airbnb" and reject rather than pass — see FR-013.

## New entities

### Per-property sensors (new)

| Entity key | Platform | State type | Phase |
| --- | --- | --- | --- |
| `last_message_at` | sensor | Timestamp | US5 |
| `awaiting_host_reply` | sensor | Binary (on/off string) | US5 |
| `next_task` | sensor | String (task type label) | US4 |
| `task_count` | sensor | Integer | US4 |

### `last_message_at` sensor

| Property | Value |
| --- | --- |
| State | ISO timestamp of the most recent message on the operationally relevant reservation, or `None` |
| Device class | `timestamp` |
| Source | `HospitableReservation.last_message_at` (no extra API call) |
| Unrecorded attributes | None needed — the timestamp itself is not PII |

### `awaiting_host_reply` sensor

| Property | Value |
| --- | --- |
| State | `on` / `off` / `None` (unknown) |
| Created | Only when `awaiting_host_reply` option is enabled |
| Source | Most recent message's `sender_type` from `GET /reservations/{uuid}/messages` |
| Extra attributes | `last_guest_message_at` (unrecorded) |

**Limitation (MUST be in description)**: This is NOT a read receipt.
It cannot detect messages read in the Hospitable UI, mobile app, or
other clients. It reflects only whether the most recent message in the
thread was sent by the guest.

### `next_task` sensor

| Property | Value |
| --- | --- |
| State | Task type label of the soonest upcoming task, or `None` |
| Attributes | `task_type`, `service_type`, `assignment_status`, `progress_status`, `scheduled_date`, `task_id` |
| Unrecorded attributes | None — task data is operational, not PII |

### `task_count` sensor

| Property | Value |
| --- | --- |
| State | Integer count of tasks in the polling window for this property |
| Attributes | `pending_count`, `in_progress_count`, `completed_count` |

## Modified entities

### `reservation_status` sensor (extended attributes)

New attributes added from guest data:

| Attribute | Type | Default | Opt-in | Unrecorded |
| --- | --- | --- | --- | --- |
| `guest_first_name` | `str \| None` | Yes (FR-039a) | No | Yes |
| `guest_last_name` | `str \| None` | Yes (FR-039a) | No | Yes |
| `guest_location` | `str \| None` | Yes (FR-039a) | No | Yes |
| `guest_language` | `str \| None` | Yes (FR-039a) | No | Yes |
| `guest_email` | `str \| None` | No | Yes (FR-039c) | Yes |
| `guest_phone_numbers` | `list[str] \| None` | No | Yes (FR-039c) | Yes |
| `reservation_uuid` | `str` | Yes | No | No |

`reservation_uuid` is added as a non-PII attribute to support the
entity_id-based service target pattern (D-10). It was implicitly
available but not previously exposed as a named attribute.

## Config entry changes

### New options (added to options flow)

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `awaiting_host_reply` | `bool` | `False` | FR-038a |
| `guest_contact_details` | `bool` | `False` | FR-038b |
| `task_interval_minutes` | `int` | `15` | FR-034; floor 5 |

### Version

Config entry version remains `VERSION = 1`, `MINOR_VERSION = 1`. The
new options have defaults that produce backward-compatible behavior
(no new entities created, no new API calls made). No migration is
needed — the options flow handles absent keys by applying defaults.

## New coordinator

### `HospitableTasksCoordinator`

| Property | Value |
| --- | --- |
| Data type | `dict[str, tuple[HospitableTask, ...]]` |
| Key | `property_id` |
| Interval option | `task_interval_minutes` |
| Default | 15 min |
| Floor | 5 min |
| Request shape | Fan-out: ONE request per selected property (FR-030) |
| Upstream cost | One request per property per refresh, plus one per additional page; 13 at reference scale |
| Required params | `properties[]` — always sent, carrying exactly one property |
| Prohibited params | Date parameters — never sent (FR-030) |
| Pagination | Mandatory from day one (FR-031); each property's own `meta.last_page` is followed independently |
| Failure isolation | Genuinely per-property, because each property has its own request. A failing property retains its last-good task data and every other property still updates. Spec 001 D-15, applied exactly as the calendar coordinator applies it. |

**Why fan-out**: a single batched request naming every property has one
outcome for all of them, so any failure would blank every task sensor at
once. The observed `meta.last_page: 2` came from such a batched request
covering 164 tasks across 13 properties and is NOT a per-property page
count.

**Wired into setup**: from the phase that introduces task sensors
(US4). Not instantiated until that phase ships.
