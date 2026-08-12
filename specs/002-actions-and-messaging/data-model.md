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

Built from an item of the `GET /tasks` response `data` array.
A live read-only capture on 2026-08-12 observed exactly these fourteen
upstream keys on all 153 captured task objects: `duration_hours`,
`end_date`, `id`, `name`, `note`, `progress_status`, `property`,
`reservation`, `service_id`, `start_date`, `task_assignment`,
`task_type`, `teammate`, and `timezone`.

| Field | Type | Source key | Tier | Notes |
| --- | --- | --- | --- | --- |
| `task_id` | `str` | `id` | CONFIRMED-BY-TEST | UUID string, not an integer |
| `name` | `str` | `name` | CONFIRMED-BY-TEST | Short upstream task code |
| `property_id` | `str` | `property.id` | CONFIRMED-BY-TEST | Association key resolved by live capture |
| `property_name` | `str` | `property.name` | CONFIRMED-BY-TEST | Operational label; review exposure before surfacing |
| `reservation_id` | `str` | `reservation.id` | CONFIRMED-BY-TEST | Opaque reservation identifier |
| `teammate_id` | `str` | `teammate.id` | CONFIRMED-BY-TEST | Opaque teammate identifier; teammate name is excluded |
| `task_type` | `int` | `task_type` | CONFIRMED-BY-TEST | 1-5; maps via `meta.task_types` |
| `service_id` | `int` | `service_id` | CONFIRMED-BY-TEST | 1-8; NOT interchangeable with task_type |
| `assignment_status` | `str` | `task_assignment.status` | CONFIRMED-BY-TEST | From meta vocabulary |
| `assignment_updated_at` | `str` | `task_assignment.updated_at` | CONFIRMED-BY-TEST | ISO-8601 timestamp with offset |
| `progress_status` | `str \| None` | `progress_status` | CONFIRMED-BY-TEST | Null was observed on 54/153 live tasks |
| `start_date` | `str` | `start_date` | CONFIRMED-BY-TEST | ISO-8601 datetime with offset |
| `end_date` | `str` | `end_date` | CONFIRMED-BY-TEST | ISO-8601 datetime with offset |
| `timezone` | `str` | `timezone` | CONFIRMED-BY-TEST | IANA timezone name |
| `duration_hours` | `int` | `duration_hours` | CONFIRMED-BY-TEST | Numeric duration |
| `task_type_label` | `str` | derived from `meta.task_types` | DERIVED | Human-readable; not an upstream field |
| `service_type_label` | `str` | derived from `meta.service_types` | DERIVED | Human-readable; not an upstream field |

**On tiers**: DERIVED is not an evidence tier and does not claim
upstream confirmation. These two labels are computed by the
integration by looking a code up in the corresponding meta vocabulary.
What is CONFIRMED-BY-TEST is that the vocabularies exist in `meta` and
that the two are distinct.

**Resolved property association key**: the live task capture resolves
the earlier open question. Tasks carry `property` as a nested object
with `id` and `name`; no flat `property_id` key was present on any of
the 153 observed objects. The implementation MUST read `property.id`
and MUST NOT accept both `property.id` and `property_id` silently,
since a permissive reader would hide a future upstream drift.

**Privacy and exposure**: `teammate.name` is a person's name and MUST
NOT be parsed into the model at all. Follow the US3 `profile_picture`
precedent in `custom_components/hospitable/api/guest.py`: a field with
no permitted exposure surface is simply not a model field, so it cannot
leak onto an entity attribute, service response, diagnostic, log, or
exception path someone forgets to guard. `teammate.id` is an opaque
identifier and MAY be retained.

`note` and `reservation.code` are dropped from the model on the same
grounds, superseding an earlier draft of this document that kept both
as fields "protected" at the entity surface. Scoping a control to one
surface while the data sits parsed and available on another is the
exact defect shape this project has hit repeatedly, and neither value
has a consumer in US4: `note` is free text a host may have typed
anything into, and `reservation.code` is guest-adjacent. The opaque
`reservation.id` is retained, because linking a task to a reservation
is genuinely useful.

**Meta vocabularies**: live `/tasks` responses carry object-valued
vocabularies in `meta.task_types`, `meta.service_types`,
`meta.assignment_statuses`, and `meta.progress_statuses`. The task and
service namespaces are distinct. The Maintenance trap is confirmed by
the meta vocabulary: `meta.task_types["5"]` is `{"label":
"Maintenance", "service_id": 8}` while `meta.service_types["5"]` is
`{"label": "Owner"}`. Looking up task_type 5 in the service-type table
therefore yields the wrong label, `Owner`. No divergent task-level row
was observed live; all 153 captured tasks had `task_type: 1` and
`service_id: 1`. The synthetic fixture includes a Maintenance row only
to exercise this confirmed vocabulary trap.

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
| Attributes | `task_type`, `service_type`, `assignment_status`, `assignment_updated_at`, `progress_status`, `start_date`, `end_date`, `timezone`, `duration_hours`, `task_id`, `reservation_id`, `teammate_id` |
| Unrecorded attributes | Every task detail attribute. Task scheduling detail changes on every poll and has no value as recorder history. `teammate.name`, `note` and `reservation.code` cannot appear at all: none is a model field |

### `task_count` sensor

| Property | Value |
| --- | --- |
| State | Integer count of tasks in the polling window for this property |
| Attributes | `pending_count`, `in_progress_count`, `completed_count` |

**On the breakdown buckets**: `progress_status` is nullable upstream
and was null on 54 of 153 live tasks, so a null counts as pending
rather than being dropped, which would otherwise make the breakdown
disagree with the state for a third of real tasks. `on_the_way`,
`arrived` and `in_progress` all count as in progress. A `cancelled`
task falls in NO bucket, so the three counts deliberately need not sum
to the state: counting cancelled work as pending would overstate what
is outstanding.

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
| `reservation_id` | `str` | Yes | No | No |

`reservation_id` is a non-PII attribute supporting the entity_id-based
service target pattern (D-10). It is ALREADY SHIPPED by the reservation
sensor; earlier drafts of this table named it `reservation_uuid`, which
was never the shipped name. The SERVICE FIELD is still
`reservation_uuid`.

## Config entry changes

### New options (added to options flow)

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `awaiting_host_reply` | `bool` | `False` | FR-038a |
| `guest_contact_details` | `bool` | `False` | FR-038b |
| `task_interval_minutes` | `int` | `15` | FR-034; floor 5 |
| `task_window_days` | `int` | `14` | FR-030; forward-only lookahead, range 1-730 |

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
| Key | `property_id` from `property.id` |
| Interval option | `task_interval_minutes` |
| Window option | `task_window_days` (default 14, range 1-730) |
| Default | 15 min |
| Floor | 5 min |
| Request shape | Fan-out: ONE request per selected property (FR-030) |
| Upstream cost | One request per property per refresh, plus one per additional page; 13 at reference scale |
| Required params | `properties[]` — upstream-required, carrying exactly one property |
| Always-sent params | `start_date` and `end_date` — derived from `task_window_days`; not upstream-required, sent by our choice (FR-030) |
| Date window | `start_date` = today, `end_date` = today + `task_window_days`; forward-only, no lookback |
| Pagination | Mandatory from day one (FR-031); each property's own `meta.last_page` is followed independently |
| Failure isolation | Per-property by deliberate fan-out. A failing property retains its last-good task data and every other property still updates. Spec 001 D-15, applied exactly as the calendar coordinator applies it. |

**Why fan-out**: a batched multi-property `/tasks` request does work;
a live probe sent three properties in one request and received HTTP 200
with `total: 7`. Fan-out is therefore not an upstream workaround. It is
a deliberate failure-isolation choice made for FR-034: a batched
request has one outcome for all properties, while one request per
property lets one failing property keep its last-good task data without
blocking the others.

**Date-window decision**: the integration sends an EXPLICIT forward
window on every request, derived from the `task_window_days` option
(default 14, range 1-730). `start_date` is today and `end_date` is
today plus the option; nothing looks backward. The default of 14
matches the undocumented upstream default measured on 2026-08-12
(today through 2026-08-24 for one property), so existing behaviour is
preserved, but the meaning of `task_count` is now fixed by OUR
configuration rather than by an upstream default that could change
without notice. A wide explicit window (`start_date=2020-01-01` and
`end_date=2027-12-31`) returned 153 tasks across the five properties
that had any tasks, instead of 12 tasks across all 13 properties with
no dates — so the window materially changes what the sensor counts.
The upper bound of 730 days is set by the upstream constraint that an
`end_date` more than three years (1095 days) in the future returns
HTTP 400; 730 leaves a comfortable margin and matches the existing
`LOOKAHEAD_MAX` precedent from spec 001.

**Wired into setup**: from the phase that introduces task sensors
(US4). Not instantiated until that phase ships.
