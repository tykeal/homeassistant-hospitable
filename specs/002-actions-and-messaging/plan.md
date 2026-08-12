<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Implementation Plan: Actions and Messaging

**Branch**: `plan/002-actions-and-messaging` | **Date**: 2026-08-12 |
**Spec**: [spec.md](./spec.md)

**Input**: Feature specification from
`specs/002-actions-and-messaging/spec.md`

## Summary

Extend the Hospitable Home Assistant integration with its first write
capability (guest messaging), four lookup services, a task coordinator
with per-property sensors, message-presence indicators, and guest
identity on reservation entities — delivered across six independently
shippable phases.

The technical approach is shaped by three forces:

1. **The write boundary must be structural, not conventional.** A
   `_post` method is available only on a write-capable subclass
   (`HospitableWriteClient`) that coordinators physically cannot reach
   without an import that reviewers and linters can flag. The polling
   lifecycle test (`test_no_writes.py`) remains a hard gate.
2. **Rate limits key on the token, not the entry.** Two config entries
   sharing a PAT share one budget. The tracker uses a SHA-256 hash of
   the token as its key, stored in a module-level singleton.
3. **Guest PII is transient, and every exposure surface needs its own
   control.** Every guest attribute is unrecorded (never persisted to
   the recorder database) and redacted from diagnostics. Service
   responses are a first-class exposure surface alongside entity
   attributes, so they pass through one allowlist serialiser that
   drops `profile_picture` unconditionally and gates contact details
   behind the same opt-in the attributes use. The model never surfaces
   `profile_picture` anywhere. Message bodies are never logged, and the
   opaque message `sender` object is never returned.

## Technical Context

**Language/Version**: Python 3.14, fully type annotated, `mypy` zero
errors. (Unchanged from spec 001.)

**Primary Dependencies**: `httpx` — no new runtime dependencies.
The `hashlib` module (standard library) is used for token hashing in
the rate-limit tracker.

**Storage**: Home Assistant config entry storage only. New options
(`awaiting_host_reply`, `guest_contact_details`,
`task_interval_minutes`, `task_window_days`)
have backward-compatible defaults. No config entry migration needed.

**Testing**: Same stack as spec 001. New test directory `tests/actions/`
for service-call handler tests. Existing `tests/test_no_writes.py` is
narrowed (not deleted). All HTTP mocked with `respx`.

**Target Platform**: Home Assistant 2026.8.0+ (unchanged).

**Scale**: Five new services, four new sensors per property, one new
coordinator, ~15 new production modules.

**Unknowns resolved in planning**:

- OQ-004 (task polling cadence): 15-minute default, 5-minute floor,
  with the poll fanned out one request per property.
  See [research.md D-04](./research.md#d-04).
- OQ-002 (message pagination): CLOSED by live probe. The endpoint is
  NOT paginated and silently ignores `page`/`per_page`; the thread is
  consumed in a single request. Bounded to a 10-message observation,
  so a `meta`/`links` block appearing later is tolerated but not
  expected. See [research.md D-07](./research.md#d-07).

**Unknowns planned around** (not resolved):

- OQ-001 (202 response body shape): Defensive parsing handles both
  presence and absence of `sent_reference_id`.
- OQ-005 (messaging scope requirement): 403 handled as capability
  limitation per existing classifier.
- OQ-007 (do message reads and writes share one per-reservation rate
  bucket?): not testable without a real send. Both sides are designed
  defensively — the awaiting-host-reply fetch floor is 60 seconds so a
  poll consumes at most one of the two slots, and send treats a 429 as
  retryable-with-backoff. Neither answer is asserted.

## Constitution Check

**Result: PASS. No constitutional principle is violated or waived.**

| Principle | Status | How this design satisfies it |
| --- | --- | --- |
| I. Code Quality & Testing | PASS | TDD red-phase protocol applied to every phase. All new modules fully typed and docstring-complete. `interrogate --fail-under=100` maintained |
| II. API Client Design | PASS | POST isolated in `HospitableWriteClient` subclass under `api/`. Coordinators use only the GET-only base client. New endpoints follow existing error taxonomy, pagination pattern, and post-condition assertions. 403 classifier unchanged. Rate-limit awareness extended with local pre-send enforcement (DOCUMENTED limits) |
| III. Atomic Commits | PASS | One PR per user story. Red-phase commits separate from green. `tasks.md` commits separate from code |
| IV. Licensing | PASS | All new files carry inline SPDX headers. New test fixtures covered by existing `REUSE.toml` annotation |
| V. Pre-Commit Integrity | PASS | No `--no-verify`. `markdownlint` covers new spec files. `check-fixture-pii` guards new fixtures |
| VI. Agent Co-Authorship & DCO | PASS | All commits `git commit -s` with `Co-authored-by: Copilot` trailer |
| VII. User Experience Consistency | PASS | Service names follow `hospitable.<verb>_<noun>`. Error messages name the remedy. Awaiting-host-reply description explicitly states the read-receipt limitation. Options describe API cost implications |
| VIII. Performance | PASS | All I/O async. Rate-limit check is O(1) deque lookup. Task coordinator on separate interval. Awaiting-host-reply adds at most one GET per property per cycle (opt-in, default OFF) |
| IX. Phased Development | PASS | Six phases, independently shippable. Service infrastructure in US1 before any service depends on it. Each phase has defined exit criteria |
| X. Security & Credentials | PASS | Token never in a second location (hashed for tracker key). Guest PII unrecorded and redacted from diagnostics. Message bodies never logged. Service responses pass through one allowlist serialiser so `profile_picture` never leaves the integration and contact details honour the opt-in on every surface (FR-046 to FR-048, D-16). No credential in fixtures |
| XI. Webhooks & Real-Time Events | NOT APPLICABLE | No webhooks introduced. Message delivery confirmation deferred to webhooks spec |
| XII. Red-Phase Commit Protocol | PASS | Every phase opens with `@pytest.mark.xfail(raises=..., strict=True)` tests. Imports deferred into test bodies. `--runxfail` scoped to new nodes before red commit |

## Project Structure

### Documentation (this feature)

```text
specs/002-actions-and-messaging/
├── spec.md                          # Input (merged, authoritative)
├── plan.md                          # This file
├── research.md                      # Phase 0: decisions
├── data-model.md                    # Phase 1: models and entities
├── quickstart.md                    # Phase 1: validation guide
└── contracts/
    ├── services.md                  # Service definitions and error mapping
    ├── upstream-requests.md         # New API requests
    └── entities.md                  # New/modified entities
```

### Source Code (new and modified modules)

```text
custom_components/hospitable/
├── api/
│   ├── client.py              # (MODIFIED) base remains GET-only
│   ├── write_client.py        # (NEW) HospitableWriteClient subclass with _post
│   ├── messages.py            # (NEW) message endpoint helpers
│   ├── tasks.py               # (NEW) task endpoint helpers
│   └── models.py              # (MODIFIED) HospitableMessage, HospitableGuest, HospitableTask
├── actions/                   # (NEW) HA service-call handlers
│   ├── __init__.py            # Table-driven registration/removal
│   ├── schemas.py             # Voluptuous schemas per service
│   ├── helpers.py             # Multi-entry resolution, reservation target resolution
│   ├── response.py            # (NEW) single PII-filtering response serialiser (D-16)
│   ├── send_message.py        # send_message handler
│   ├── get_messages.py        # get_messages handler
│   ├── find_reservation.py    # find_reservation handler
│   ├── get_reservations.py    # get_reservations handler
│   ├── get_property_info.py   # get_property_info handler
│   └── rate_limit.py          # Token-keyed rate-limit tracker
├── coordinator.py             # (MODIFIED) task coordinator added; reservation coordinator adds include=guest and optional message fetch
├── sensor/
│   ├── reservation.py         # (MODIFIED) guest attributes (reservation_id attribute already ships)
│   ├── tasks.py               # (NEW) next_task, task_count sensors
│   └── messages.py            # (NEW) last_message_at, awaiting_host_reply sensors
├── const.py                   # (MODIFIED) new option keys, task defaults
├── config_flow.py             # (MODIFIED) new options in options flow
├── strings.json               # (MODIFIED) service text, new option labels
├── translations/en.json       # (MODIFIED) same additions
└── diagnostics.py             # (MODIFIED) guest field redaction

tests/
├── actions/                   # (NEW) service handler tests
│   ├── conftest.py
│   ├── test_send_message.py
│   ├── test_get_messages.py
│   ├── test_lookups.py
│   ├── test_rate_limit.py
│   ├── test_response_privacy.py
│   └── test_disambiguation.py
├── sensor/
│   └── test_tasks.py          # (NEW) task sensor tests
├── fixtures/                  # (NEW fixtures)
│   ├── messages_thread.json
│   ├── messages_empty.json
│   ├── tasks_page1.json
│   ├── tasks_page2.json
│   ├── reservation_with_guest.json
│   └── send_message_202.json
├── test_no_writes.py          # (MODIFIED) narrowed, not deleted
└── test_privacy.py            # (MODIFIED) guest PII audit added
```

## Architecture: Write Isolation

The most important architectural decision in this feature.

```text
┌─────────────────────────────────────────┐
│           Polling Lifecycle             │
│  coordinator.py → api/client.py        │
│  (GET only — _post not available)      │
└─────────────────────────────────────────┘
         ↕ reads coordinator data (never triggers refresh)
┌─────────────────────────────────────────┐
│        Service Call Handlers            │
│  actions/ → api/write_client.py        │
│  (inherits GET, adds _post)            │
└─────────────────────────────────────────┘
```

**Enforcement layers**:

1. **Type system**: `HospitableApiClient` has no `_post` method.
   Coordinators type-annotate their client as `HospitableApiClient`.
   Any `coordinator.client._post(...)` call is a mypy error in CI.
2. **Instance assertion**: Coordinators MUST be constructed with a
   base `HospitableApiClient` instance, NOT a `HospitableWriteClient`.
   A test asserts `not isinstance(coordinator.client,
   HospitableWriteClient)` for every coordinator class. The write
   client is a separate instance created per `actions/` handler
   context.
3. **Import scan**: A static test scans the AST of `coordinator.py`,
   `sensor/`, and `config_flow.py` and fails if any imports
   `HospitableWriteClient`, imports from `actions/`, or references
   `_post`.
4. **Lifecycle assertion**: `test_no_writes.py` asserts zero non-GET
   requests during the full polling lifecycle.

**Honest characterisation**: This guarantee is TEST-ENFORCED (four
independent gates), not structurally impossible. The tradeoff was
accepted because the structurally-impossible alternative (a completely
separate HTTP client) would duplicate connection pooling, auth, and
retry logic.

## Rate-Limit Accounting

```text
RateLimitTracker (module-level singleton)
├── _per_reservation: dict[(token_hash, reservation_uuid), deque[timestamp]]
│   Rule: max 2 entries per 60-second window
└── _per_token: dict[token_hash, deque[timestamp]]
    Rule: max 50 entries per 300-second window

Check: before every send_message call
Record: after successful acceptance (202)
Key: SHA-256(token) — never holds raw credential
```

Two config entries with the same PAT hash to the same key and share
one budget. Different PATs have independent budgets. This satisfies
FR-018.

## Coordinators (updated)

| Coordinator | Interval | Default | Floor | Phase |
| --- | --- | --- | --- | --- |
| `HospitableReservationsCoordinator` | reservation | 5 min | 1 min | Spec 001 |
| `HospitablePropertiesCoordinator` | property | 60 min | 15 min | Spec 001 |
| `HospitableCalendarCoordinator` | property | 60 min | 15 min | Spec 001 |
| `HospitableTasksCoordinator` | task | 15 min | 5 min | US4 (new) |

`HospitableTasksCoordinator` fans its poll out to ONE `GET /tasks`
request per selected property rather than one batched request naming
every property (FR-030). This is what makes the FR-034 per-property
failure isolation implementable: one failure affects one property,
which retains its last-good data while the rest update. It mirrors the
spec 001 calendar coordinator, which is already per-property. Cost at
reference scale is 13 requests per 15-minute poll on an endpoint that
publishes no rate limit and returns no `x-ratelimit-*` headers.
Pagination is followed per property, each using its own
`meta.last_page`.

The reservation coordinator is modified in US6 to:

- Add `include=guest` to the request (zero extra cost)
- Optionally fetch messages for the awaiting-host-reply indicator

## Phase breakdown

Six phases, one PR each, in priority order. Each is independently
shippable and ends at green CI before the next begins.

### Phase US1 (P1) — Service infrastructure and send message

**Delivers**: `api/write_client.py`; `api/messages.py`;
`actions/` package with table-driven registration, schemas,
helpers, `send_message.py`, and `rate_limit.py`; narrowed
`test_no_writes.py`; service text in `strings.json`/
`translations/en.json`; new test fixtures.

**Requirements**: FR-001 to FR-019, FR-044, FR-045.

**Why independently shippable**: A user can send a guest message via
service call and receive acceptance confirmation. The service
infrastructure (registration, disambiguation, rate limiting) is
established for all subsequent services.

**Red-phase sequence (Principle XII)**:

1. Red: Tests for write-client instantiation, `_post` method, rate
   limiting, send-message happy path, error cases, static import
   isolation.
2. Green: Implement `write_client.py`, `rate_limit.py`,
   `send_message.py`, registration in `actions/__init__.py`.
3. Red: Tests for `test_no_writes.py` narrowing (service call issues
   POST but polling lifecycle does not).
4. Green: Narrow `test_no_writes.py`.

**Exit criteria**: `send_message` service callable; rate limits
enforced; polling lifecycle still write-free; static import test
passing; `strings.json` has service text.

### Phase US2 (P2) — Read messages and lookup services

**Delivers**: `actions/get_messages.py`, `find_reservation.py`,
`get_reservations.py`, `get_property_info.py`; defensive message
pagination in `api/messages.py`.

**Requirements**: FR-020 to FR-029, FR-046 to FR-048.

**Why independently shippable**: All lookup services are operational.
Users can query reservations, properties, and message threads on
demand. These are GET-only and zero-risk.

**Red-phase sequence**:

1. Red: Tests for each service's happy path, not-found return value,
   pagination (messages), multi-entry disambiguation.
2. Green: Implement handlers.

**Exit criteria**: All five services registered and tested. Not-found
is a return value, not an exception. Message pagination handles both
cases.

### Phase US3 (P3) — Guest identity on reservation entities

**Delivers**: `include=guest` on reservation poll; `HospitableGuest`
model; guest attributes on `reservation_status` sensor; the
`reservation_id` attribute already ships; `guest_contact_details`
option in options flow; PII redaction for guest fields; updated
diagnostics.

**Requirements**: FR-039 to FR-043, FR-038b.

**Why independently shippable**: Guest names appear on reservation
sensors. Privacy framework proven (unrecorded, redacted from
diagnostics, never logged).

**Red-phase sequence**:

1. Red: Tests for `HospitableGuest.from_api()`, null guest handling,
   guest attributes on entity, unrecorded assertion, diagnostics
   redaction, log audit.
2. Green: Implement model, modify reservation coordinator, extend
   sensor, extend diagnostics.

**Exit criteria**: Guest first/last name on entity when available.
Absent when null. Never in logs or diagnostics. Opt-in email/phone
gated behind option. All guest attributes unrecorded.

### Phase US4 (P4) — Task sensors

**Delivers**: `api/tasks.py`; `HospitableTask` model;
`HospitableTasksCoordinator`; `sensor/tasks.py` with `next_task` and
`task_count`; `task_interval_minutes` and `task_window_days`
options; new fixtures.

**Requirements**: FR-030 to FR-035, FR-034.

**Why independently shippable**: Task sensors per property are
operational. Per-property fan-out, per-property pagination, and
per-property failure isolation proven. Type/service_id mapping
validated.

**Red-phase sequence**:

1. Red: Tests for task model, coordinator pagination, type mapping
   (Maintenance = task_type 5 ≠ service_id 8), sensor state.
2. Green: Implement model, coordinator, sensors.

**Exit criteria**: All pages fetched. Maintenance correctly labelled.
Task count matches total. 15-minute default with 5-minute floor.

### Phase US5 (P5) — Message presence indicators

**Delivers**: `sensor/messages.py` with `last_message_at` and
`awaiting_host_reply`; `awaiting_host_reply` option in options flow;
optional message fetch in reservation coordinator.

**Requirements**: FR-036 to FR-038a.

**Why independently shippable**: Per-property message indicators
operational. `last_message_at` derived from existing data (zero cost).
`awaiting_host_reply` opt-in with documented API cost.

**Red-phase sequence**:

1. Red: Tests for `last_message_at` sensor from reservation data,
   `awaiting_host_reply` sensor with mock messages, option gating.
2. Green: Implement sensors and coordinator modification.

**Exit criteria**: `last_message_at` reports timestamp, no extra calls.
`awaiting_host_reply` correct when enabled, absent when disabled.
Description states the read-receipt limitation.

### Phase US6 (P6) — Integration testing and polish

**Delivers**: End-to-end integration tests exercising multiple services
in sequence; multi-entry rate-limit sharing test; any fixes the
evidence forces; final `strings.json` audit.

**Requirements**: SC-001 to SC-009 verification.

**Why independently shippable**: This phase is predominantly tests and
polish. It delivers the evidence for every success criterion.

**Red-phase sequence**: Test-only strengthening of existing tests is
exempt from red-phase protocol (Principle XII, Exemptions). Any
behavior change discovered gets its own red phase.

**Exit criteria**: All success criteria demonstrably met. Full suite
green. No spec 001 test broken.

## Deviation record

### Deviation 1: `actions/` vs extending `services/`

**Instruction context**: Spec 001 defined `services/` as domain logic
(reservation selection, occupancy derivation, etc.) and explicitly
stated it is "not Home Assistant service-call registration."

**What this plan does**: Creates a NEW `actions/` package for HA
service-call handlers rather than overloading the existing `services/`
package.

**Why**: The name collision is documented in spec 001's plan as
deliberate — `services/` holds domain logic, not HA services. Adding
HA service handlers there would contradict that documented intent. The
Hostaway reference uses `services/` for HA services because it has no
conflicting domain-logic package. We do, so we use a different name.

**Cost of being wrong**: One rename. No user-visible change.

### Deviation 2: `SupportsResponse.ONLY` on send_message

**Instruction context**: Could argue OPTIONAL is more automation-
friendly (fire-and-forget).

**What this plan does**: Uses ONLY.

**Why**: FR-011 requires reporting acceptance. A fire-and-forget
caller that ignores the response has no way to confirm the message
was accepted. ONLY forces consumption of the result, which is the
correct contract for a write operation. The spec's anti-pattern
guidance explicitly rejects OPTIONAL+event dual mode.

### A spec 001 contract change: the service registration statement

Spec 001's `contracts/entities.md` states "No Home Assistant services
are registered." This plan's `contracts/entities.md` explicitly
replaces that statement. The change is called out here rather than made
silently.
