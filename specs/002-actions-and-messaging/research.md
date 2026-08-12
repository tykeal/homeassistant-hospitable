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
Nothing in this document upgrades a tier by reasoning. Where a tier
changed (message pagination and the messages-endpoint rate limit,
recorded in D-03, D-06, D-07, and the assumption table), it changed
because a live read-only probe on 2026-08-12 observed the behaviour
directly, and the exact bound of what was observed is stated with it.

## Decision index

| ID | Decision | Governing requirements |
| --- | --- | --- |
| D-01 | Write isolation via module path: `actions/` package | FR-001, FR-003 |
| D-02 | Table-driven HA service registration, Hostaway pattern | FR-005, FR-006 |
| D-03 | Rate-limit accounting keyed on token value | FR-017, FR-018, FR-019, OQ-007 |
| D-04 | Task coordinator with 15-minute default, 5-minute floor | FR-030, FR-034, OQ-004 |
| D-05 | `include=guest` on existing reservation poll | FR-039, FR-040 |
| D-06 | Awaiting-host-reply as opt-in per-property message fetch | FR-037, FR-038, FR-038a, OQ-007 |
| D-07 | Single-request thread fetch; no pagination loop | FR-023, OQ-002 |
| D-08 | Defensive 202 response parsing | FR-012, OQ-001 |
| D-09 | Service text in strings.json and translations | FR-007 |
| D-10 | Reservation target: entity_id OR reservation_uuid | FR-044 |
| D-11 | Guest attributes as unrecorded | FR-039e, FR-042 |
| D-12 | PII redaction for guest and message fields | FR-041, FR-042, FR-024 |
| D-13 | Task type vs service_id explicit mapping | FR-033, FR-035 |
| D-14 | `SupportsResponse.ONLY` on all services including send | FR-011a, FR-021, FR-025 to FR-027 |
| D-15 | No event firing, no OPTIONAL response mode | FR-021, anti-pattern avoidance |
| D-16 | Single response-builder chokepoint for guest and sender PII | FR-046, FR-047, FR-047a, FR-048 |
| D-17 | `/tasks` live constraints and pagination behaviour | FR-030, FR-031, FR-034 |

## D-01: Write isolation via module path {#d-01}

**Decision**: Introduce a new `actions/` package (sibling to `api/`
and `services/`) containing all Home Assistant service-call handlers.
The `api/client.py` gains a `_post` method, but the `_post` method is
defined on a subclass or mixin (`HospitableWriteClient`) that is
instantiated ONLY by `actions/` code, never by coordinators. The
coordinator code path uses the existing `HospitableApiClient` which
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
`DELETE` requests are captured.

**Four independent enforcement gates** (compensating for the reduction
from spec 001's structural impossibility to test-enforced guarantee):

1. **Type-level (mypy, CI-enforced)**: The coordinator's client
   attribute MUST be annotated as the base `HospitableApiClient`. Since
   `HospitableApiClient` has no `_post` method, any `coordinator.client.
   _post(...)` call is a mypy error caught in CI.
2. **Instance-level (runtime test)**: Coordinators MUST be constructed
   with a base `HospitableApiClient` instance, NOT a
   `HospitableWriteClient`. A test asserts
   `not isinstance(coordinator.client, HospitableWriteClient)` for
   every coordinator class. The `HospitableWriteClient` is a separate
   instance created per service call (or once per `actions/` handler
   context), never shared with coordinators.
3. **Import-level (static test)**: A test scans the AST of
   `coordinator.py`, `sensor/`, and `config_flow.py` and fails if any
   module imports `HospitableWriteClient`, imports from `actions/`, or
   references `_post`.
4. **Lifecycle-level (respx assertion)**: The narrowed
   `test_no_writes.py` asserts zero non-GET requests during the full
   polling lifecycle (setup → refresh → options change → reload →
   unload).

**Honest characterisation**: This guarantee is TEST-ENFORCED, not
structurally impossible. A future contributor CAN violate it — but
four independent gates (type checker, runtime isinstance, static
import scan, and lifecycle assertion) must all be defeated
simultaneously for a write to escape the polling path into production.
The tradeoff was accepted because the structurally-impossible
alternative (completely separate HTTP client) would duplicate
connection pooling, auth header injection, and retry logic across two
independent client classes, creating a maintenance burden
disproportionate to the risk.

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

- We use `SupportsResponse.ONLY` on all services (D-14/D-15).
- We MUST have service text in `strings.json`/`translations/en.json`.
  Hostaway omits this and relies solely on `services.yaml`.
- We do NOT fire events alongside responses (Hostaway's
  `get_reservations` uses OPTIONAL and fires an event — we reject
  this as confusing).

## D-03: Rate-limit accounting keyed on token value {#d-03}

**Decision**: A module-level `RateLimitTracker` class keyed on the
SHA-256 hash of the token string. Two independent sliding windows:

1. Per-reservation: 2 requests per 60 seconds, keyed on
   `(token_hash, reservation_uuid)`. Sends and message fetches share
   this one window (see the header-feedback note below and OQ-007).
2. Per-token: 50 messages per 300 seconds, keyed on `token_hash`.

The tracker is a singleton (module-level dict) so that two config
entries sharing the same PAT share one budget without explicit
cross-entry communication. Both the send path and the
awaiting-host-reply message fetch route through this ONE tracker
rather than keeping separate counters (see D-06 and OQ-007).

**Evidence tiers, which MUST NOT be conflated** (FR-017):

- **2 requests per 60 seconds per reservation: CONFIRMED-BY-TEST** on
  `GET /reservations/{uuid}/messages` by a read-only probe on
  2026-08-12. The endpoint returns `x-ratelimit-limit: 2` and
  `x-ratelimit-remaining: <n>` on success; on HTTP 429 it also returns
  `retry-after` (59–60 observed) and `x-ratelimit-reset` (unix epoch).
  The buckets are independent per reservation: reservation A was
  burned to `remaining: 0` and returned 429, and reservation B
  immediately returned HTTP 200 with a fresh `remaining: 1`. The 429
  body is the Laravel envelope with NO `errors` key,
  `{"status_code": 429, "reason_phrase": "Too Many Attempts."}`, so
  the shared envelope parser must tolerate the missing key.
- **50 per 5 minutes per PAT/vendor: DOCUMENTED only**, never tested.
- The same 2-per-minute-per-reservation figure for the SEND endpoint
  is **DOCUMENTED only** — no POST has ever been executed.

**Scope of the throttling**: `/properties`, `/reservations`, and
`/tasks` were re-checked in the same session and expose NO
`x-ratelimit-*` and NO `retry-after` headers. Spec 001's recorded
finding (only `x-hospitable-trace`; no `X-RateLimit-*`, no
`Retry-After`) therefore remains CORRECT for the endpoints spec 001
tested. The messages endpoint is simply a different, throttled
endpoint. This is not a spec 001 defect and spec 001 is not edited.

**Header feedback**: where `x-ratelimit-limit`,
`x-ratelimit-remaining`, and `x-ratelimit-reset` are present on a
messages-endpoint response, they are fed back into the tracker in
preference to its own count; their absence is tolerated. An upstream
429 is handled as retryable-with-backoff driven by `retry-after`, as
distinct from the local pre-send refusal in FR-019, which is immediate
and never retried.

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
minutes).

The poll fans out to one request per property (FR-030), so a 15-minute
default costs 13 requests per poll at reference scale — 52 per hour,
1,248 per day — plus one extra request for any property deep enough to
paginate. The 5-minute floor triples that to ~3,744 requests/day for
tasks alone, which is acceptable but worth documenting.

`/tasks` publishes no rate limit and returns no `x-ratelimit-*` or
`retry-after` headers (CONFIRMED-BY-TEST), which is what makes fan-out
affordable. The per-property failure isolation it buys is worth far
more than the saved requests: a batched call has one outcome for all 13
properties, so a single failure blanks every task sensor at once.

An earlier revision of this decision quoted 2,496 requests/day from
"13 properties and 2 pages per poll". That arithmetic was wrong for the
batched design it described — a batched poll of 2 pages is 2 requests,
not 26 — and the corrected fan-out figures above supersede it.

For comparison, spec 001's reservation coordinator at default 5
minutes with 13 properties costs ~1,704 requests/day. Adding tasks at
15 minutes adds ~1,248, keeping the combined total near 3,000/day at
reference scale.

**Alternatives considered**:

- *30 minutes*: Too slow for cleaning coordination use cases where a
  manager wants near-real-time task progress.
- *5 minutes (same as reservations)*: Wasteful. Tasks rarely change
  within 5 minutes.
- *One batched request naming every property*: Rejected. It is cheaper
  (2 requests per poll rather than 13) but it destroys per-property
  failure isolation, which FR-034 requires and which spec 001 D-15
  establishes as the house pattern. The saving is not worth the
  coupling on an endpoint with no published rate limit.
- *10 minutes*: Reasonable but 15 gives better economy with
  acceptable latency for the typical use case.
- *Sharing the reservation interval*: Rejected. Tasks and
  reservations have genuinely different change frequencies, and the
  spec (FR-034) explicitly calls for a separate cadence.

## D-05: `include=guest` on existing reservation poll {#d-05}

**Decision**: Add `include=guest,properties` (comma-separated) to the
existing reservation request's query parameters. Multi-include
stacking is CONFIRMED-BY-TEST: each named include contributes its own
top-level key independently.

**Evidence** (CONFIRMED-BY-TEST, live account):

- baseline (no include) → 21 keys
- `include=guest` → 22 keys (adds `guest`)
- `include=guest,properties` → 23 keys (adds `guest` AND `properties`)
- `include=guest,listings` → 23 keys (adds `guest` AND `listings`)
- `include=guest,properties,listings` → 24 keys (adds all three)
- URL-encoding the comma (`%2C`) behaves identically

**Rationale**: The existing reservation poll already sends
`include=properties` (spec 001 D-06). Adding `guest` to the same
parameter via comma-separation costs zero additional requests and
enriches the payload with guest data for FR-039/FR-039a attributes.
Population is good (29/29 non-null guest objects, first_name 29/29).

**Post-condition (spec 001 FR-075)**: Because unrecognised include
names are silently ignored — one of the silent-ignore behaviours spec
001 FR-075 enumerates — the implementation
MUST assert the `guest` key is actually present on every response
item. A missing key when `include=guest` was requested raises
`HospitableIncludeMissingError`. This is the same pattern applied to
`include=listings` and `include=properties` in spec 001.

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
It routes through the D-03 tracker rather than a second counter.

**The 60-second per-reservation fetch floor is a conservative choice,
not a derivation.** The effective per-reservation message-fetch
interval is floored at 60 seconds, enforced independently of the
configured reservation poll interval (whose floor is 1 minute, so an
aggressively configured entry could otherwise reach the upstream
limit). The confirmed upstream limit of 2 requests per 60 seconds per
reservation would mathematically permit a 30-second interval. The
floor is set at 60 seconds deliberately so that a poll consumes at
most ONE of the two slots, leaving the other free for a user-initiated
send. That is the OQ-007 hedge: if reads and writes share one bucket,
polling at the mathematical maximum would starve the send path. This
rationale must not be restated anywhere as the floor being "derived
from" or "required by" the rate limit.

**429 on the optional fetch**: handled without failing the whole
reservation update. The previous indicator value is retained,
`retry-after` is respected, and the entity is NOT marked unavailable —
a throttle is not an outage. This needs its own handling rather than
inheriting the existing coordinator path, which logs a 429 and does
not reschedule.

## D-07: Single-request thread fetch on the messages endpoint {#d-07}

**Decision**: `GET /reservations/{uuid}/messages` is consumed in ONE
request. No pagination loop is written, and `page`/`per_page` are
never sent. A `meta` or `links` block, if one ever appears, is
tolerated without crashing.

**Evidence** (CONFIRMED-BY-TEST, read-only probe 2026-08-12):

- The envelope is `{data}` only — no `meta`, no `links` — unlike
  `/reservations` and `/tasks`, which carry all three.
- `per_page=1`, `per_page=2`, `page=1`, `page=2`, and
  `per_page=1&page=2` ALL returned the identical full set of 10 items.
  Both parameters are therefore silently ignored on this endpoint.

**Rationale**: Sending `page`/`per_page` would create a false
impression that the payload is bounded. It is not: there is no
upstream mechanism to bound this response, so a very long conversation
arrives in full and no code may assume a small list.

**Relationship to spec 001's register**: spec 001 records `page` and
`per_page` as CONFIRMED honored, with a `meta.current_page`
post-condition. That entry remains correct for the endpoints spec 001
tested (`/properties`, `/reservations`, `/tasks`). The silent-ignore
behaviour is endpoint-scoped to the messages endpoint and is an
addition to spec 001's set of silent-ignore instances, not a
correction of it. Spec 001 is not edited.

**Scope caveat, stated honestly**: the busiest conversation on the
reference account holds only 10 messages, so behaviour above that
volume was NOT observed. Pagination may appear above some unobserved
threshold. The forward-compatibility tolerance above exists for that
reason and must not be written as though pagination were the expected
behaviour. OQ-002 is closed only to the extent of the observed range.

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
the `reservation_id` attribute — the name the reservation sensor
already ships. If the entity is unavailable or the attribute is absent,
raise `ServiceValidationError`. The SERVICE FIELD remains
`reservation_uuid`; only the attribute read differs.

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

- `TASK_TYPE_MAP: dict[int, str]` — e.g., `{1: "Cleaning", ..., 5: "Maintenance"}`
- `SERVICE_TYPE_MAP: dict[int, str]` — e.g., `{1: "Cleaning", ..., 8: "Maintenance"}`

The sensor displays the task_type label. The service_id is available
as an attribute for automations that need it but is never conflated
with task_type.

**Rationale**: FR-033. Maintenance is task_type 5 but service_id 8.
Conflating them would mislabel maintenance tasks. The live meta
vocabulary shows the precise trap: task_type 5 is Maintenance with
service_id 8, while service_type 5 is Owner. No divergent task row was
observed live; all 153 observed tasks carried task_type 1 with
service_id 1. The evidence is the meta vocabulary
(CONFIRMED-BY-TEST).

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

**Rationale**: each service's response mode rests on its own
requirement, and the citations must not be widened past their scope.
FR-021 specifies ONLY for `get_messages` alone. The three lookup
services carry it individually in FR-025, FR-026, and FR-027. An
earlier revision of this decision cited FR-021 for "lookups"
generally, which FR-021 does not say.

For `send_message`, FR-011a is the governing requirement. ONLY is
appropriate there because the caller needs the acceptance confirmation
(and any correlation identifier) as structured data. There is no use
case for firing an event on send — the caller already has the
result.

**Revision from initial consideration**: Initially considered
`SupportsResponse.OPTIONAL` for send_message (to allow fire-and-forget
from automations that do not need the response). Rejected because
FR-011 requires reporting "accepted for delivery" — if the automation
does not consume the response, it has no way to know acceptance
occurred. FR-011a records that conclusion as a requirement. `ONLY`
forces the caller to handle the response, which is the correct
contract for a write operation.

## D-15: No event firing, no OPTIONAL response mode {#d-15}

**Decision**: No service fires a Home Assistant event. No service uses
`SupportsResponse.OPTIONAL`.

**Rationale**: The spec explicitly names Hostaway's
OPTIONAL-response-plus-event dual mode as an anti-pattern to avoid.
Events create a parallel notification channel that is confusing when
the service already returns structured data. `ONLY` is the clean
contract: you call the service, you get the data back, done.

## Assumptions on UNVERIFIED upstream behavior

Every row below carries its own tier and a concrete fallback. Rows
below CONFIRMED-BY-TEST are never treated as confirmed anywhere in the
design. Two rows (A-03, A-05) were upgraded to CONFIRMED-BY-TEST by
the read-only probe of 2026-08-12 and are stated with the exact bound
of what was observed; their neighbours (A-05a, A-05b) deliberately
remain DOCUMENTED and UNVERIFIED so the tiers are not blurred.

| ID | Assumption | Tier | Fallback |
| --- | --- | --- | --- |
| A-01 | `POST /reservations/{uuid}/messages` returns HTTP 202 on success | DOCUMENTED | If it returns 200 or 201, treat as success equally |
| A-02 | The 202 body may contain `sent_reference_id` | UNVERIFIED | Return `null` for correlation ID if absent |
| A-03 | `GET /reservations/{uuid}/messages` does not paginate and silently ignores `page`/`per_page` | CONFIRMED-BY-TEST, bounded to a 10-message thread | Single request; tolerate a `meta`/`links` block appearing later rather than crash |
| A-04 | Messaging may require a scope the current token lacks | UNVERIFIED | Handle 403 as capability limitation per existing classifier |
| A-05 | The messages GET is limited to 2 per 60s per reservation, with independent per-reservation buckets and `x-ratelimit-*`/`retry-after` headers | CONFIRMED-BY-TEST | Feed headers back into the tracker; tolerate their absence |
| A-05a | The SEND limits are 2/min/reservation and 50/5min/token | DOCUMENTED (never tested; no POST has been executed) | Enforce locally; if the API enforces differently, the local guard is conservative |
| A-05b | Reads and writes may or may not share one per-reservation bucket | UNVERIFIED and untestable without a real send (OQ-007) | Assert neither; 60s fetch floor leaves one slot free, and send treats 429 as retryable-with-backoff |
| A-06 | `sender_id` is Airbnb-only | DOCUMENTED | Reject client-side for non-Airbnb reservations |
| A-07 | Task vocabularies in `meta` are stable | CONFIRMED-BY-TEST (structure) | Fall back to hard-coded map if meta absent |

## D-16: Single response-builder chokepoint for PII {#d-16}

**Decision**: One shared serialiser — `actions/response.py` — is the
only code that converts an upstream reservation, guest, or message
payload into a service response. It strips `profile_picture`
unconditionally, strips `email` and `phone_numbers` unless the
guest-contact-details option is enabled on the config entry serving the
call, strips the opaque message `sender` object unconditionally, and
emits an explicit ALLOWLIST of keys so that an unrecognised upstream key
is dropped rather than passed through. Every handler returns the output
of this serialiser; no handler serialises a payload itself.

**Why this decision exists**: the analyze gate found that
`find_reservation` and `get_reservations` were specified to return the
raw reservation payload "with guest". The guest object carries
`profile_picture`, `email`, and `phone_numbers`. FR-039c and FR-039d
appeared to cover this, but both were written in terms of ENTITY
ATTRIBUTES, so neither reached the service-response surface. No
requirement and no task constrained what a service returned. The defect
was not a missing control; it was a control scoped to the wrong
surface — which is why it looked covered and was not, and why no CI
gate could have caught it. FR-046 states the general principle so the
same shape is recognisable next time.

**Why a chokepoint rather than per-handler filtering**: per-handler
filtering is correct exactly as long as every author remembers it. The
defect being fixed here is a forgetting defect, so the fix must not
depend on remembering. A single serialiser means a sixth service added
in a later specification inherits the filter by construction, and the
red-phase test enumerates registered services rather than a hard-coded
list, so a new service that bypasses the serialiser fails the audit.

**Why an allowlist rather than a denylist**: a denylist protects only
the keys known when it was written. Hospitable adds keys silently — the
`guest` include itself was discovered late — so a denylist would leak
the next PII field by default. The allowlist is `first_name`,
`last_name`, `location`, `language`, plus `email` and `phone_numbers`
when the option is on.

**Alternatives considered**:

- *Return the raw payload and document the risk*: Rejected. Service
  responses appear in automation traces and template debug output; the
  user cannot opt out of a payload they did not ask for.
- *Gate the whole of `find_reservation` behind the contact-details
  option*: Rejected. Names and dates are the useful part and carry no
  contact exposure; gating everything would push users to enable the
  contact option for unrelated reasons, which is the opposite of the
  intent.
- *Filter in the schema layer*: Rejected. Voluptuous schemas validate
  service INPUT. The response path does not pass through them.

## D-17: `/tasks` live constraints and pagination behaviour {#d-17}

**Decision**: Keep the US4 task coordinator's default request shape as
one fan-out `GET /tasks` request per property with no date parameters,
while recording the live constraints discovered by the 2026-08-12
read-only probes.

**Live-probe confirmations**:

- Bare `/tasks` with no `properties[]` returns HTTP 400 with a Laravel
  envelope whose reason phrase is "The properties field is required."
- `/tasks` exposes no `x-ratelimit-*` or `retry-after` headers, unlike
  the messages endpoint.
- Default `per_page` is 10.
- Pagination is real and honoured: `per_page=1` on a three-task
  property yielded `last_page: 3`, and `page=2` returned the second
  task. This contrasts with the messages endpoint, which silently
  ignores both parameters.
- With no date parameters, one property returned only tasks from
  2026-08-12 through 2026-08-24, an upstream default forward window of
  roughly 14 days. A wide explicit window returned 153 tasks across
  the five properties that had any tasks, versus 12 tasks across all
  13 properties with no date filter.
- An `end_date` more than three years in the future returns HTTP 400
  with the Laravel envelope reason phrase "You cannot fetch tasks more
  than 3 years in the future." Future configurable task windows must
  validate or cap this bound before sending requests.
- A batched multi-property request does work: three properties in one
  request returned HTTP 200 with `total: 7`. Fan-out remains a repo
  owner failure-isolation choice, not an upstream limitation.

**Rationale**: These facts define the polling window and future window
constraints without changing US4's decision to omit date parameters by
default. They also keep the task endpoint's pagination and rate-header
behaviour distinct from the messages endpoint, where pagination
parameters were observed to be ignored.
