<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Phase 0 Research: Actions and Messaging

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Date**: 2026-08-12

## Purpose

This document records decisions taken before design, reasoning, and
rejected alternatives for spec 002. It also isolates every assumption
the design rests on that the specification does not mark CONFIRMED.

The specification's five-tier evidence legend (CONFIRMED-BY-TEST,
CONFIRMED-BY-SPEC, DOCUMENTED, LIKELY, UNVERIFIED) is used verbatim.
Nothing in this document upgrades a tier.

## Decision index

| ID | Decision | Governing requirements |
| --- | --- | --- |
| D-01 | Write isolation via module path: `actions/` package | FR-001, FR-003 |
| D-02 | Table-driven HA service registration, Hostaway pattern | FR-005, FR-006 |
| D-03 | Rate-limit accounting keyed on token value | FR-017, FR-018, FR-019 |
| D-04 | Task coordinator with 15-minute default, 5-minute floor | FR-030, FR-034, OQ-004 |
| D-05 | `include=guest` on existing reservation poll | FR-039, FR-040 |
| D-06 | Awaiting-host-reply as opt-in per-property message fetch | FR-037, FR-038 |
| D-07 | Defensive pagination on messages endpoint | FR-023, OQ-002 |
| D-08 | Defensive 202 response parsing | FR-012, OQ-001 |
| D-09 | Service text in strings.json and translations | FR-007 |
| D-10 | Reservation target: entity_id OR reservation_uuid | FR-044 |
| D-11 | Guest attributes as unrecorded | FR-039e, FR-042 |
| D-12 | PII redaction for guest and message fields | FR-041, FR-042, FR-024 |
| D-13 | Task type vs service_id explicit mapping | FR-033, FR-035 |
| D-14 | `SupportsResponse.ONLY` on all services including send | FR-021, FR-025 to FR-027 |
| D-15 | No event firing, no OPTIONAL response mode | FR-021, anti-pattern avoidance |

## D-01: Write isolation via module path {#d-01}

**Decision**: Introduce a new `actions/` package (sibling to `api/`
and `services/`) containing all Home Assistant service-call handlers.
The `api/client.py` gains a `_post` method, but the `_post` method is
defined on a subclass or mixin (`HospitableWriteClient`) that is
instantiated ONLY by `actions/` code, never by coordinators. The
coordinator code path uses the existing `HospitableClient` which
exposes only `_get`.

**Rationale**: FR-003 demands architectural enforcement, not
convention. A coordinator importing `HospitableWriteClient` would be
a visible, reviewable violation. The module-path separation means the
polling lifecycle physically cannot reach a POST method without an
import that linters and reviewers can flag.

**Alternatives considered**:

- *Add `_post` to the existing client, guard with a flag*: Rejected.
  A boolean flag is convention, not structure. A coordinator with
  access to the full client can accidentally call `_post` and the
  compiler does not prevent it.
- *Separate HTTP client instance*: Rejected. Would duplicate
  connection pooling, auth header injection, and retry logic. A
  subclass inherits all of that.
- *Runtime assertion in `_post` checking call stack*: Rejected.
  Fragile, not statically verifiable, and would silently break under
  refactoring.

**Structural enforcement test**: `test_no_writes.py` is narrowed to
assert that during the polling lifecycle, zero `POST`/`PUT`/`PATCH`/
`DELETE` requests are captured. Additionally, a static import test
asserts that no module under `coordinator.py` or `sensor/` imports
from `actions/` or from `api.write_client`.

## D-02: Table-driven HA service registration {#d-02}

**Decision**: Follow the Hostaway pattern exactly: a
`SERVICE_DEFINITIONS` tuple of `ServiceDefinition` NamedTuples, each
carrying name, handler, schema, and `SupportsResponse` mode. A single
`async_setup_services(hass)` iterates the table and registers each
service if not already registered (idempotent skip guard).
`async_unload_services(hass)` removes services only when the last
config entry for the domain unloads.

**Rationale**: Proven pattern in a sibling integration maintained by
the same author. Idempotent registration solves the multi-entry
problem naturally: the first `async_setup_entry` registers; subsequent
ones skip; the last `async_unload_entry` removes.

**Differences from Hostaway**:

- We use `SupportsResponse.ONLY` everywhere except `send_message`
  (which uses `SupportsResponse.OPTIONAL` — but see D-15).
- We MUST have service text in `strings.json`/`translations/en.json`.
  Hostaway omits this and relies solely on `services.yaml`.
- We do NOT fire events alongside responses (Hostaway's
  `get_reservations` uses OPTIONAL and fires an event — we reject
  this as confusing).

## D-03: Rate-limit accounting keyed on token value {#d-03}

**Decision**: A module-level `RateLimitTracker` class keyed on the
SHA-256 hash of the token string. Two independent sliding windows:

1. Per-reservation: 2 messages per 60 seconds, keyed on
   `(token_hash, reservation_uuid)`.
2. Per-token: 50 messages per 300 seconds, keyed on `token_hash`.

The tracker is a singleton (module-level dict) so that two config
entries sharing the same PAT share one budget without explicit
cross-entry communication.

**Rationale**: FR-018 requires token-keyed accounting. Hashing avoids
holding the raw token in a second location. A module-level singleton
is the simplest structure that survives across config entries without
threading state through `hass.data`.

**Why SHA-256 hash, not the raw token**: The tracker is long-lived in
memory and may appear in debug repr. Hashing prevents the token from
leaking into logs or diagnostics if the object is ever str()'d.

**Alternatives considered**:

- *Per config-entry accounting*: Rejected. Violates FR-018 — two
  entries with the same PAT would get double the budget.
- *Store tracker in `hass.data[DOMAIN]`*: Rejected. Would require
  cross-entry coordination logic that the module-level approach avoids.
- *Use a token bucket algorithm*: Rejected as over-engineering. The
  windows are small (60s, 300s) and the limits are low (2, 50).
  A simple deque of timestamps per key suffices.

**Reset behavior**: Timestamps older than the window are pruned lazily
on each check. No periodic cleanup task is needed given the small
cardinality (one entry per active reservation target, bounded by user
behavior).

## D-04: Task coordinator polling cadence {#d-04}

**Decision**: Default 15 minutes, floor 5 minutes.

**Rationale**: Tasks change less frequently than reservations (which
default to 5 minutes) but more frequently than properties (60
minutes). A 15-minute default is conservative for API economy: with
13 properties and 2 pages per poll, that is 26 requests per 15
minutes = 104 requests/hour = 2,496 requests/day at the reference
account scale. The 5-minute floor allows users who need faster task
updates (e.g., for cleaning crew coordination) to tighten it at the
cost of ~7,488 requests/day for tasks alone — acceptable but worth
documenting.

For comparison, spec 001's reservation coordinator at default 5
minutes with 13 properties costs ~1,704 requests/day. Adding tasks at
15 minutes adds ~2,496, keeping the combined total under 5,000/day at
reference scale.

**Alternatives considered**:

- *30 minutes*: Too slow for cleaning coordination use cases where a
  manager wants near-real-time task progress.
- *5 minutes (same as reservations)*: Wasteful. Tasks rarely change
  within 5 minutes and the endpoint is 2 pages deep.
- *10 minutes*: Reasonable but 15 gives better economy with
  acceptable latency for the typical use case.
- *Sharing the reservation interval*: Rejected. Tasks and
  reservations have genuinely different change frequencies, and the
  spec (FR-034) explicitly calls for a separate cadence.

## D-05: `include=guest` on existing reservation poll {#d-05}

**Decision**: Add `include=guest` (singular) to the existing
reservation request's query parameters. This adds zero extra API calls
and enriches the reservation payload from 21 to 22 keys.

**Rationale**: CONFIRMED-BY-TEST that `include=guest` works on both
collection and single endpoints. The guest object is needed for
FR-039/FR-039a attributes. Population is good (29/29 non-null guest
objects, first_name 29/29). Cost is zero additional requests.

**Change to spec 001 contract**: This modifies the
`upstream-requests.md` Honored-Request Verification table. Previously
`include=guests` (plural) was listed as a confirmed no-op under
"NEVER SEND." The new entry adds `include=guest` (singular) as a
CONFIRMED valid expansion with a post-condition assertion. The plural
`include=guests` remains prohibited.

## D-06: Awaiting-host-reply as opt-in message fetch {#d-06}

**Decision**: When the `awaiting_host_reply` option is enabled, the
reservation coordinator's `_async_update_data` additionally calls
`GET /reservations/{uuid}/messages` for each property's operationally
relevant reservation (at most one call per property per cycle). The
most recent message's `sender_type` determines the indicator state.

**Rationale**: FR-037 and FR-038 define this precisely. The option
defaults to OFF because it adds ~13 API calls per cycle (one per
property with an active reservation). When OFF, zero message-fetch
calls are made.

**Implementation detail**: The message fetch is triggered from within
the reservation coordinator's update method (not a separate
coordinator), because it needs the just-fetched reservation data to
identify the operationally relevant reservation. The fetch is guarded
by the option check and is a simple supplementary GET, not a write.

## D-07: Defensive pagination on messages endpoint {#d-07}

**Decision**: The `GET /reservations/{uuid}/messages` implementation
checks for `meta` and `links` in the response envelope. If present,
it paginates using the standard `meta.last_page` pattern. If absent
(as observed with 7 messages), it treats `data` as the complete
result set.

**Rationale**: OQ-002 is UNVERIFIED. Only 7 messages were observed
with no pagination metadata. The defensive approach handles both cases
without failing on either.

## D-08: Defensive 202 response parsing {#d-08}

**Decision**: The send-message handler parses the 202 response body
opportunistically. If the body contains JSON with a
`sent_reference_id` (or any correlation key), it is included in the
service response. If the body is empty or contains no recognizable
correlation identifier, the service response reports acceptance
without a correlation ID.

**Rationale**: OQ-001 is UNVERIFIED. The exact 202 body shape has
never been observed. The implementation must not fail on an empty body
or an unexpected shape.

**Service response shape** (always returned):

```json
{
  "accepted": true,
  "reservation_uuid": "<the target>",
  "sent_reference_id": "<if present in 202 body, else null>"
}
```

## D-09: Service text in strings.json and translations {#d-09}

**Decision**: All service names, descriptions, and field labels appear
in both `strings.json` and `translations/en.json`. The `services.yaml`
file references translation keys rather than containing inline text.

**Rationale**: FR-007 is explicit. Hostaway's omission of service text
from translations is identified as an anti-pattern we must not copy.
Home Assistant's modern service architecture supports translation keys
in `services.yaml` via the `name` and `description` fields pointing to
`strings.json` entries.

## D-10: Reservation target: entity_id OR reservation_uuid {#d-10}

**Decision**: Every service that targets a reservation accepts an
`entity_id` field (from which the reservation UUID is extracted from
entity attributes) OR a `reservation_uuid` field. Exactly one must be
provided; both or neither raises `ServiceValidationError`.

**Rationale**: FR-044 requires this pattern. It serves two use cases:
automation authors who have a sensor entity (use `entity_id`) and
script users who know the UUID directly (use `reservation_uuid`).

**Resolution from entity_id**: Read the entity's state attributes for
the `reservation_uuid` attribute. If the entity is unavailable or the
attribute is absent, raise `ServiceValidationError`.

## D-11: Guest attributes as unrecorded {#d-11}

**Decision**: All guest attributes (`guest_first_name`,
`guest_last_name`, `guest_location`, `guest_language`, `guest_email`,
`guest_phone_numbers`) are added to the entity's
`_unrecorded_attributes` frozenset, following the precedent of
`forward_window` on the availability sensor.

**Rationale**: FR-039e requires this. Unrecorded attributes live in
entity state memory only and are never written to the recorder
database. This is the correct Home Assistant mechanism for transient
PII that should be queryable in real time but never persisted.

## D-12: PII redaction for guest and message fields {#d-12}

**Decision**: Extend the existing denylist-based log redaction and
allowlist-based diagnostics redaction to cover all guest fields and
message bodies.

- **Logs**: Guest first_name, last_name, email, phone_numbers,
  location, language, profile_picture, and message `body` fields are
  never logged at any level. The models do not carry these values into
  any `__repr__` or `__str__`.
- **Diagnostics**: Guest fields appear as `"**REDACTED**"` (not
  omitted), per FR-042's requirement that presence be distinguishable
  from absence.

**Rationale**: FR-041 and FR-042. Extends the spec 001 pattern to the
new data domain.

## D-13: Task type vs service_id explicit mapping {#d-13}

**Decision**: Two separate enum mappings, both populated from the
`/tasks` response `meta` vocabularies:

- `TASK_TYPE_MAP: dict[int, str]` — e.g., `{1: "Check-in", ..., 5: "Maintenance"}`
- `SERVICE_TYPE_MAP: dict[int, str]` — e.g., `{1: "Cleaning", ..., 8: "Maintenance"}`

The sensor displays the task_type label. The service_id is available
as an attribute for automations that need it but is never conflated
with task_type.

**Rationale**: FR-033. Maintenance is task_type 5 but service_id 8.
Conflating them would mislabel maintenance tasks. The meta
vocabularies are the authoritative source (CONFIRMED-BY-TEST).

**Implementation**: On first successful task poll, extract the
vocabularies from `meta.task_types` and `meta.service_types`. Cache
them for the lifetime of the coordinator. If meta is absent (defensive
case), fall back to hard-coded mappings derived from the confirmed
observation.

## D-14: `SupportsResponse.ONLY` on all services {#d-14}

**Decision**: All lookup services (`find_reservation`,
`get_reservations`, `get_property_info`, `get_messages`) use
`SupportsResponse.ONLY`. The `send_message` service also uses
`SupportsResponse.ONLY` — it returns the acceptance result as
structured data.

**Rationale**: FR-021 specifies ONLY for lookups. For `send_message`,
ONLY is also appropriate because the caller needs the acceptance
confirmation (and optional `sent_reference_id`) as structured data.
There is no use case for firing an event on send — the caller already
has the result.

**Revision from initial consideration**: Initially considered
`SupportsResponse.OPTIONAL` for send_message (to allow fire-and-forget
from automations that do not need the response). Rejected because
FR-011 requires reporting "accepted for delivery" — if the automation
does not consume the response, it has no way to know acceptance
occurred. `ONLY` forces the caller to handle the response, which is
the correct contract for a write operation.

## D-15: No event firing, no OPTIONAL response mode {#d-15}

**Decision**: No service fires a Home Assistant event. No service uses
`SupportsResponse.OPTIONAL`.

**Rationale**: The spec explicitly names Hostaway's
OPTIONAL-response-plus-event dual mode as an anti-pattern to avoid.
Events create a parallel notification channel that is confusing when
the service already returns structured data. `ONLY` is the clean
contract: you call the service, you get the data back, done.

## Assumptions on UNVERIFIED upstream behavior

Each assumption below rests on a tier below CONFIRMED-BY-TEST. None
is treated as CONFIRMED anywhere in the design, and each has a
concrete fallback.

| ID | Assumption | Tier | Fallback |
| --- | --- | --- | --- |
| A-01 | `POST /reservations/{uuid}/messages` returns HTTP 202 on success | DOCUMENTED | If it returns 200 or 201, treat as success equally |
| A-02 | The 202 body may contain `sent_reference_id` | UNVERIFIED | Return `null` for correlation ID if absent |
| A-03 | `GET /reservations/{uuid}/messages` may paginate for long threads | UNVERIFIED | Handle both paginated and non-paginated responses |
| A-04 | Messaging may require a scope the current token lacks | UNVERIFIED | Handle 403 as capability limitation per existing classifier |
| A-05 | Rate limits are 2/min/reservation and 50/5min/token | DOCUMENTED | Enforce locally; if API enforces differently, our local guard is conservative |
| A-06 | `sender_id` is Airbnb-only | DOCUMENTED | Reject client-side for non-Airbnb reservations |
| A-07 | Task vocabularies in `meta` are stable | CONFIRMED-BY-TEST (structure) | Fall back to hard-coded map if meta absent |
