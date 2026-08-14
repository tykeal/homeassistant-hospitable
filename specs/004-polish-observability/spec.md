<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Feature Specification: Polish and Observability

**Feature Branch**: `spec/004-polish-observability`

**Created**: 2026-08-13

**Status**: Draft

**Input**: User description: "Polish and observability — five
independent deliverables: a cancelled task progress bucket,
listing-field privacy gating, bare mypy invocation, trace-header
capture, and a relative-day window override for
`get_reservations`."

## Overview

Specs 001 through 003 delivered a read-only Hospitable integration
with reservation sensors, property sensors, task/cleaning sensors,
five service actions, guest-identity privacy controls, and property
discovery. This specification covers five small, independent polish
and observability improvements that harden the integration against
silent data loss, close a privacy gap, simplify contributor tooling,
surface upstream correlation identifiers for support diagnostics,
and remove a workflow friction point from `get_reservations`.

The five deliverables are independent. Each may be implemented and
merged in its own PR without depending on the others.

### Evidence confidence legend

This specification uses the same confidence tiers as specs 001–003.

| Marker | Meaning |
| --- | --- |
| **CONFIRMED-BY-TEST** | Verified empirically against a live Hospitable account (read-only probes only; no POST has ever been executed). |
| **CONFIRMED-BY-SPEC** | Read directly from Hospitable's own OpenAPI export, but not confirmed by a live grant. |
| **DOCUMENTED** | Stated in Hospitable's current official documentation, but not verified empirically. |
| **LIKELY** | Reported by an independent third party who claims live verification, but not reproduced by this project. |
| **UNVERIFIED** | Single-source, undocumented, or inferred. Must not be relied upon without a test. |

### Amendments to earlier specifications

This specification formally amends the following requirements from
earlier specs:

- **Spec 002 FR-032 (task sensors)** — The task-count sensor's
  breakdown attributes currently comprise three buckets
  (`pending_count`, `in_progress_count`, `completed_count`) that
  deliberately do not sum to the sensor state. Deliverable 1 adds a
  fourth bucket (`cancelled_count`) and changes the contract so that
  the four buckets DO sum to `task_count` while the upstream
  vocabulary remains the known six values.

- **Spec 002 FR-047b scope boundary note** — The scope boundary
  paragraph in FR-047b explicitly states that `platform_email` and
  `platform_picture` "remain unfiltered by design." Deliverable 2
  reverses that decision: both fields are now gated behind the
  guest-contact opt-in, routed through the existing privacy
  chokepoint. The scope boundary note is superseded.

- **Spec 002 `get_property_info` docstring scope note** — The
  docstring at `actions/get_property_info.py` lines 10–14 states
  that `platform_email` and `platform_picture` are "not filtered,
  and that is a deliberate scope decision." This is superseded; the
  implementation PR MUST update the docstring to reflect the new
  gating.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Reconcilable task breakdown (Priority: P1)

As a property manager, I want the task-count sensor's progress
breakdown to account for every task — including cancelled ones — so
that the bucket counts always sum to the total and I can trust the
numbers without wondering where the missing tasks went.

**Why this priority**: A breakdown that does not reconcile invites
bug reports and erodes trust in the integration's data. This is the
maintainer's top priority among the five deliverables.

**Independent Test**: Supply a task fixture containing tasks with
each of the six known `progress_status` values (including
`cancelled` and `null`). Confirm `pending_count +
in_progress_count + completed_count + cancelled_count` equals
`task_count`.

**Acceptance Scenarios**:

1. **Given** a property with tasks spanning all six progress
   statuses, **When** the task coordinator polls, **Then** the
   task-count sensor's breakdown attributes sum to `task_count`.
2. **Given** a task with `progress_status` of `cancelled`, **When**
   the coordinator polls, **Then** the task increments
   `cancelled_count` and does NOT increment any other bucket.
3. **Given** a task with `progress_status` of `null`, **When** the
   coordinator polls, **Then** the task increments `pending_count`
   (existing behaviour, preserved).
4. **Given** a hypothetical future `progress_status` value not in
   the known six, **When** the coordinator encounters it, **Then**
   the integration logs a warning naming the unknown status and the
   task is counted in no bucket (the sum guarantee is suspended for
   that poll cycle).
5. **Given** the static frozensets in the codebase, **When** the
   test suite runs, **Then** a test asserts that the union of all
   four frozensets equals exactly `{"not_started", "on_the_way",
   "arrived", "in_progress", "completed", "cancelled"}`.

---

### User Story 2 — Listing field privacy gating (Priority: P1)

As a property manager, I want `platform_email` and
`platform_picture` on listings to be filtered through the same
privacy controls as every other personal-data field, so that the
integration's fail-closed posture has no exceptions.

**Why this priority**: Equal to Deliverable 1 because it closes a
known privacy gap that contradicts the project's allowlist posture.

**Independent Test**: Invoke `get_property_info` with
`guest_contact_details` disabled and confirm `platform_email` and
`platform_picture` are absent from every listing in the response.
Re-invoke with the option enabled and confirm both appear.

**Acceptance Scenarios**:

1. **Given** `guest_contact_details` is disabled, **When** a user
   invokes `get_property_info`, **Then** `platform_email` and
   `platform_picture` are omitted from every listing object in the
   response.
2. **Given** `guest_contact_details` is enabled, **When** a user
   invokes `get_property_info`, **Then** `platform_email` and
   `platform_picture` are present on listing objects (when the API
   supplies them).
3. **Given** a listing object containing an unknown/new key not in
   any allowlist, **When** the response is serialized, **Then** the
   unknown key is dropped (fail-closed).
4. **Given** a `list_properties` call, **When** the response is
   built, **Then** `co_hosts[].user_id` remains present and
   functional (spec 003 FR-007 dependency preserved).
5. **Given** a listing arrives as a list of dicts (not a single
   dict), **When** the privacy filter processes it, **Then** every
   entry in the list is individually filtered rather than the list
   passing through unfiltered.

---

### User Story 3 — Bare `uv run mypy` works (Priority: P2)

As a contributor, I want `uv run mypy` with no arguments to check
the same paths as `uv run mypy custom_components/ tests/`, so that
I do not need to remember the explicit paths.

**Why this priority**: A quality-of-life improvement for every
contributor and CI agent, but not a data-integrity issue.

**Independent Test**: Run `uv run mypy` and `uv run mypy
custom_components/ tests/` and confirm both produce identical
output.

**Acceptance Scenarios**:

1. **Given** `pyproject.toml` has a `files` setting under
   `[tool.mypy]`, **When** a contributor runs `uv run mypy` with
   no arguments, **Then** mypy checks `custom_components/` and
   `tests/`.
2. **Given** both invocation forms, **When** both are run on the
   same codebase, **Then** their output is identical (same errors,
   same files checked).

---

### User Story 4 — Trace header capture (Priority: P2)

As a property manager diagnosing a support issue, I want the
`x-hospitable-trace` correlation ID from API responses to appear
in error logs and the diagnostics payload, so that I can give
Hospitable support a trace to look up.

**Why this priority**: Observability improvement that directly
reduces support-ticket resolution time, but does not affect
data correctness.

**Independent Test**: Mock an API response with an
`x-hospitable-trace` header and confirm it appears in the
diagnostics payload. Mock an error response with the header and
confirm the logged error includes the trace ID.

**Acceptance Scenarios**:

1. **Given** an API error response carrying
   `x-hospitable-trace: abc123`, **When** the integration logs the
   error, **Then** the log message includes the trace ID `abc123`.
2. **Given** a successful API response carrying
   `x-hospitable-trace: abc123`, **When** the diagnostics payload
   is built, **Then** the most recent trace ID(s) are present in the
   diagnostics output.
3. **Given** an API response WITHOUT the `x-hospitable-trace`
   header, **When** the integration handles it, **Then** no trace
   ID is logged or surfaced, and no error or misleading empty value
   appears.
4. **Given** the trace ID appears in the diagnostics payload,
   **When** the diagnostics redactor runs, **Then** the trace ID
   passes through unredacted (it is an operational correlation
   identifier, not personal data — see FR-016 justification).

---

### User Story 5 — Relative-day window override (Priority: P2)

As a property manager, I want to widen or narrow the
`get_reservations` query window in a single service call —
without changing integration options — so that I can discover a
far-future booking's UUID and then use it with `find_reservation`
or `send_message`, which are not window-bound.

**Why this priority**: A workflow friction point that forces a
persistent configuration change for a one-off discovery task. Not
a data-integrity issue, but it recurs every time a far-future
booking needs attention during a live guest issue.

**Motivation (2026-08-13, maintainer-reported):** To validate
message sending end-to-end, the maintainer had to create an owner
stay more than 90 days out, then widen the integration's
`lookahead_days` option purely to make the reservation appear in
`get_reservations` so he could read its UUID. `find_reservation`
and `send_message` both resolve a reservation by UUID via
`resolve_reservation_uuid` and fetch it directly — neither is
window-bound. Only `get_reservations` and the reservation sensors
respect the configured window.

**Independent Test**: Invoke `get_reservations` with
`lookforward_days: 400` spanning a known far-future reservation.
Confirm it appears without any change to `lookahead_days`.

**Acceptance Scenarios**:

1. **Given** both `lookforward_days` and `lookbackward_days` are
   omitted, **When** a user invokes `get_reservations`, **Then**
   the forward reach equals the config entry's `lookahead_days`
   option (default 90) and the backward reach equals the
   action-specific fixed default of 7 days.
2. **Given** `lookforward_days: 400`, **When** a user invokes
   `get_reservations`, **Then** the queried window extends 400
   days into the future regardless of `lookahead_days`.
3. **Given** `lookbackward_days: 30`, **When** a user invokes
   `get_reservations`, **Then** the queried window extends 30
   days into the past regardless of `lookback_days`.
4. **Given** `lookforward_days: 1096` (above the 1095-day
   ceiling), **When** a user invokes `get_reservations`, **Then**
   the call raises `ServiceValidationError` naming the 1095-day
   limit.
5. **Given** `lookbackward_days: 366` (above the 365-day
   ceiling), **When** a user invokes `get_reservations`, **Then**
   the call raises `ServiceValidationError`.
6. **Given** valid parameters, **When** the upstream request
   succeeds, **Then** the response flows through
   `serialize_response` and the `found: false` vs `found: true`
   distinction is preserved.
7. **Given** a test that exercises `get_reservations`, **When**
   the test asserts `ServiceValidationError`, **Then** it MUST
   first assert the service is registered to avoid false passes
   from `ServiceNotFound` (which subclasses
   `ServiceValidationError`).

---

### Edge Cases

- A task with a `progress_status` that matches an
  `assignment_status` value (e.g. both vocabularies contain
  `cancelled`) — the bucket MUST key on `progress_status`, never
  `assignment_status`.
- A listing object that is a scalar or null rather than a dict —
  the privacy filter must not crash.
- The `x-hospitable-trace` header value contains unusual characters
  or is extremely long — the integration must log/store it safely
  without truncation errors.
- `mypy` `files` setting interaction with explicit CLI paths — the
  CLI paths must override `files` (standard mypy behaviour) so
  existing invocations are unaffected.
- `lookforward_days: 1` — valid; queries only one day forward.
  `lookforward_days: 1095` — valid (boundary inclusive).
  `lookforward_days: 1096` — rejected locally.
- `lookbackward_days: 0` — valid; future-only search (see FR-025
  justification). `lookbackward_days: 365` — valid (boundary
  inclusive). `lookbackward_days: 366` — rejected locally.
- Both parameters supplied simultaneously — both take effect;
  they are independent, not mutually exclusive.
- `lookforward_days` exceeding the config option's 730-day
  `lookahead_days` maximum — valid; the action intentionally
  reaches further than the option permits, which is the entire
  point of the escape hatch.

## Requirements *(mandatory)*

### Deliverable 1 — Cancelled task progress bucket

- **FR-001**: The integration MUST define a fourth progress bucket,
  `CANCELLED_STATUSES = frozenset({"cancelled"})`, alongside the
  existing `PENDING_STATUSES`, `IN_PROGRESS_STATUSES`, and
  `COMPLETED_STATUSES`.

- **FR-002**: The `cancelled` status MUST be keyed on
  `progress_status`, NOT `assignment_status`.
  `meta.assignment_statuses` also contains a value spelled
  `cancelled`; these are two different dimensions of a task.
  Confusing them would misclassify tasks. This distinction MUST be
  documented in the bucket definitions.

- **FR-003**: The task-count sensor MUST expose a `cancelled_count`
  breakdown attribute computed identically to the existing three
  buckets.

- **FR-004**: A task with `progress_status` of `null` MUST continue
  to be counted as pending (existing behaviour, unchanged).

- **FR-005**: While the upstream progress vocabulary remains the
  known six values (`not_started`, `on_the_way`, `arrived`,
  `in_progress`, `completed`, `cancelled`), the four bucket counts
  MUST sum to `task_count`. This is a reconciliation GUARANTEE
  conditioned on vocabulary stability.

- **FR-006**: The integration MUST implement a vocabulary drift
  guard. If a task arrives with a `progress_status` value that is
  not `null` and is not a member of any of the four frozensets, the
  integration MUST log a warning naming the unknown status value.
  The unknown task MUST NOT be silently assigned to any bucket; it
  falls outside the sum guarantee for that poll cycle.

- **FR-007**: The test suite MUST include an allowlist-style
  exhaustiveness assertion: the union of the four frozensets MUST
  equal exactly `{"not_started", "on_the_way", "arrived",
  "in_progress", "completed", "cancelled"}`. This is a vocabulary
  contract test; if Hospitable adds a seventh status, the test fails
  and forces the developer to add a bucket or make an explicit
  decision.

- **FR-008**: The comment block above the frozenset definitions
  MUST be updated to remove the statement that a cancelled task
  "falls in no bucket" and to reflect the new reconciliation
  guarantee. The docstring on `extra_state_attributes` MUST
  likewise be updated.

**Observed evidence (2026-08-13, CONFIRMED-BY-TEST):**
`meta.progress_statuses` from `GET /v2/tasks?properties[]=<id>`
contains exactly six values: `not_started`, `on_the_way`, `arrived`,
`in_progress`, `completed`, `cancelled`. In a 150-day window across
all 13 properties (119 tasks), `progress_status` was `completed`
on 67, `null` on 33, and no task had `progress_status == cancelled`.
No `cancelled` task has been observed in production data. This
bucket is vocabulary-driven and preventive, not observed.
`assignment_status` was `null` on all 100 sampled tasks.

### Deliverable 2 — Gate `platform_email` and `platform_picture`

- **FR-009**: `platform_email` and `platform_picture` on listing
  objects MUST be gated behind the existing `guest_contact_details`
  option (spec 002 FR-038b). When the option is disabled, both
  fields MUST be omitted from service responses. When enabled,
  both MUST be present (when the API supplies them).

- **FR-010**: The gating MUST be implemented inside the existing
  response-privacy chokepoint (`serialize_response` in
  `actions/response.py`, per spec 002 FR-048). It MUST NOT be
  implemented as a per-handler filter.

- **FR-011**: Listing objects MUST be processed through an
  allowlist, consistent with the existing fail-closed pattern. A
  listing key not enumerated in any allowlist MUST be dropped. The
  allowlist MUST include at minimum: `platform`, `platform_id`,
  `co_hosts`, and — when `guest_contact_details` is enabled —
  `platform_email` and `platform_picture`.

- **FR-012**: The filter MUST handle the list-of-dicts shape that
  listings arrive in. The existing `_filter_identity` begins with
  `if not isinstance(value, dict): return serialize_response(...)`,
  which would walk a list through recursive serialization without
  applying the listing allowlist. Listings MUST receive the same
  explicit list handling that `_filter_co_hosts` already provides
  for `co_hosts`. This exact trap has occurred once before in this
  project (with co-hosts) and MUST NOT recur.

- **FR-013**: `co_hosts` within each listing MUST continue to be
  processed through the existing `_filter_co_hosts` path (spec 002
  FR-047b). `platform` and `platform_id` MUST remain
  unconditionally returnable. Spec 003's `list_properties` depends
  on `co_hosts[].user_id` for the Airbnb `sender_id` workflow;
  breaking that dependency would break messaging.

- **FR-014**: The `get_property_info` handler's module docstring
  (lines 10–14 of `actions/get_property_info.py`) MUST be updated
  to reflect the new gating, removing the statement that
  `platform_email` and `platform_picture` are "not filtered."

### Deliverable 3 — Make bare `uv run mypy` work

- **FR-015**: `pyproject.toml`'s `[tool.mypy]` section MUST include
  a `files` setting that causes `uv run mypy` (with no arguments)
  to check `custom_components/` and `tests/`.

- **FR-016 (verification)**: The bare invocation (`uv run mypy`)
  and the explicit invocation (`uv run mypy custom_components/
  tests/`) MUST produce identical results. This equivalence SHOULD
  be verified in the implementation PR.

### Deliverable 4 — Surface the `x-hospitable-trace` header

- **FR-017**: The API client layer MUST capture the
  `x-hospitable-trace` response header value when present on any
  API response (success or error).

- **FR-018**: When the integration logs an API error, the log
  message MUST include the `x-hospitable-trace` value if one was
  present on the error response. This is the highest-value capture
  point: error responses are exactly when a trace is needed for
  support tickets.

- **FR-019**: The trace ID MUST also be captured from successful
  responses and surfaced in the diagnostics payload. The
  diagnostics payload MUST include the most recent trace ID(s) —
  at minimum one per coordinator — so that a diagnostics download
  taken shortly after an incident carries the relevant trace.

  **Justification for capturing on success too**: The trace is most
  valuable on errors, but a success trace lets a user report "I saw
  stale data at this time, here is the trace from that poll" —
  which is the second most common support scenario after outright
  failures.

- **FR-020**: When the `x-hospitable-trace` header is absent from
  a response, the integration MUST NOT log a misleading empty trace
  or crash. The trace field in diagnostics MUST be `null` or absent,
  not an empty string.

- **FR-021**: The `x-hospitable-trace` value is an operational
  correlation identifier, NOT personal data. It identifies a
  request/response pair on Hospitable's infrastructure and carries
  no guest, host, or account identity. It MUST therefore pass
  through the diagnostics redactor unredacted. This is a deliberate
  classification, not an oversight — the value MUST be added to
  `ALLOWED_TOP_LEVEL` or surfaced in a section that the redactor
  does not strip.

- **FR-022**: The diagnostics entrypoint
  (`async_get_config_entry_diagnostics` in `diagnostics.py`) MUST
  remain reachable from a real Home Assistant diagnostics download.
  The spec 002 dead-code discovery (a redactor that existed but was
  never callable because no diagnostics platform was registered)
  MUST NOT be repeated. A test MUST verify the entrypoint is
  importable and callable.

### Deliverable 5 — Relative-day window override for `get_reservations`

**Motivation:** `get_reservations` currently queries ONLY the
window defined by the integration's `lookback_days` /
`lookahead_days` options. Discovering a far-future reservation's
UUID requires widening those persistent options, even though the
subsequent `find_reservation` and `send_message` calls resolve by
UUID and are not window-bound. This deliverable adds optional
relative-day parameters so a single call can look outside the
configured window without changing integration options.

**Design decision (2026-08-13, maintainer-directed):** The
original design proposed absolute `start_date`/`end_date` fields
with a both-or-neither rule. The maintainer replaced that with
relative day-count parameters. Relative offsets cover the use
case more ergonomically ("look 400 days ahead" beats computing a
date), and keeping both relative and absolute forms would require
a conflict-precedence rule for no benefit.

- **FR-023**: `get_reservations` MUST accept two optional integer
  service fields: `lookforward_days` and `lookbackward_days`.
  Both MUST be declared as `vol.Optional` in the action schema.

- **FR-024 (`lookforward_days` default — inherited)**: When
  `lookforward_days` is omitted, the forward reach MUST default
  to the config entry's `lookahead_days` option value (which
  itself defaults to 90). This mirrors the sensor window by
  default, which is the least-surprise behaviour: omitting the
  field keeps the sensors' forward reach.

  **Note:** This is a least-surprise argument, not a
  backwards-compatibility one. The integration is unreleased
  and has no existing users.

- **FR-025 (`lookbackward_days` default — fixed 7, deliberately
  asymmetric)**: When `lookbackward_days` is omitted, the
  backward reach MUST default to a **fixed 7 days**. It MUST
  NOT inherit the config entry's `lookback_days` option (which
  defaults to 90 and ranges from 7 to 365).

  **Deliberate asymmetry — why the defaults differ:** The
  `lookforward_days` default inherits the configured option;
  `lookbackward_days` does not. This is intentional. The
  `get_reservations` action is a **lookup tool for messaging**:
  its primary purpose is discovering a reservation UUID so
  `find_reservation` or `send_message` can act on it. For that
  workflow, stale bookings rarely matter — the operator almost
  always wants a current or upcoming reservation. A 7-day
  lookback is enough to catch recently-started stays without
  returning months of irrelevant history. By contrast, the
  reservation sensors are a **monitoring surface** where the
  full configured lookback is needed for dashboard accuracy.
  **This asymmetry is a deliberate design choice. Do not
  "correct" it to symmetry — doing so would silently change
  the action's default query window from days to months and
  return large volumes of unneeded data in the common case.**

  `lookbackward_days: 0` is allowed (see FR-026). A caller who
  wants the sensors' backward reach can pass
  `lookbackward_days` explicitly.

- **FR-026 (`lookbackward_days` range — 0 to 365)**: The
  inclusive range for `lookbackward_days` MUST be **0 to 365**.
  Values outside this range MUST raise
  `ServiceValidationError`.

  **Justification for allowing 0:** The config entry option's
  `lookback_days` minimum is 7, but that bound exists for a
  **polling sensor** that must always cover at least a week to
  avoid missing in-progress stays. The `get_reservations`
  action is a **one-shot lookup** — a caller who only wants
  future reservations should be able to request exactly that.
  A zero-day lookback produces a future-only search, which is
  a valid and useful query ("show me what is coming up"). There
  is no operational harm: the upstream API accepts the query,
  and the result is simply empty or forward-only.

  **Upper bound justification:** 365 matches the config
  option's `LOOKBACK_MAX` (`options_bounds.py`). Looking back
  further than a year is unlikely for a messaging-focused
  lookup and would invite unnecessarily large result sets.

- **FR-027 (`lookforward_days` range — 1 to 1095)**: The
  inclusive range for `lookforward_days` MUST be **1 to 1095**.
  Values outside this range MUST raise
  `ServiceValidationError` with a message naming the allowed
  range.

  **Upper bound justification (1095 days = ~3 years):** The
  upstream reservations endpoint (`GET /v2/reservations`)
  enforces a 3-year future ceiling. Queries beyond that return
  HTTP 400 with `{"reason_phrase": "You cannot fetch prices
  and availabilities more than 3 years in the future."}` —
  a misleading message that names prices/availabilities while
  gating a reservations query (CONFIRMED-BY-TEST, 2026-08-13:
  `+1y`, `+2y`, `+3y` returned HTTP 200; `+5y` and `+10y`
  returned HTTP 400). The integration MUST validate locally
  and name the real limit so users are not confused by the
  upstream wording.

  **Lower bound justification:** A zero-day forward reach is
  meaningless (today only, with no backward reach if
  `lookbackward_days` is also 0, or with only backward reach).
  The minimum of 1 ensures the window always extends at least
  one day into the future.

  **Exceeding the config option's 730-day ceiling:** The
  config entry's `lookahead_days` option caps at 730 days
  (`LOOKAHEAD_MAX` in `options_bounds.py`). The action's
  1095-day ceiling intentionally exceeds this. The option
  governs a polling sensor that runs every update interval —
  a wide window there has recurring request-budget cost. The
  action is a one-shot call where the cost is borne once. This
  is the entire point of the per-call escape hatch.

- **FR-028 (validation error type)**: All range and input
  validation errors from this deliverable MUST raise
  `ServiceValidationError`, consistent with spec 003
  FR-017/FR-018. **Trap:** `ServiceNotFound` subclasses
  `ServiceValidationError`. Acceptance tests that merely
  assert `ServiceValidationError` is raised can pass
  spuriously when the service is not registered at all. Tests
  MUST first assert the service IS registered, then assert the
  expected validation error.

- **FR-029 (`date_query` remains fixed)**: The per-call override
  MUST NOT expose or change the `date_query` parameter. It
  remains fixed at `checkin` (the value set in
  `build_reservation_params`). Exposing it would widen the
  action's surface for no stated user need and would require
  documenting the semantic differences between query modes.
  Scope is kept tight.

- **FR-030 (privacy chokepoint preserved)**: The response MUST
  continue to flow through `serialize_response` in
  `actions/response.py`. The `found: false` vs
  `found: true` + empty-list distinction documented at the
  top of `get_reservations.py` MUST be preserved.

- **FR-031 (docstring contract update)**: The
  `async_handle_get_reservations` docstring in
  `actions/get_reservations.py` currently states: "The queried
  window matches the one the reservation coordinator polls, so
  the service and the entities describe the same span of
  time." **This statement is no longer true.** Even with no
  parameters supplied, the action's backward reach defaults to
  7 days while the reservation sensors use `lookback_days`
  (default 90). The docstring MUST be rewritten to describe
  the real relationship:

  > When both parameters are omitted the forward reach
  > matches the reservation coordinator's `lookahead_days`;
  > the backward reach defaults to 7 days (not
  > `lookback_days`). Callers who need the sensors' exact
  > window must pass both parameters explicitly.

  An inaccurate docstring is worse than none — this project
  has been bitten repeatedly by well-meaning corrections based
  on stale contract prose.

- **FR-032 (no changes to options or sensors)**: This
  deliverable MUST NOT change the reservation coordinator, the
  reservation sensors, the `lookback_days` / `lookahead_days`
  options, or their bounds (`options_bounds.py`: lookback
  7–365, lookahead 1–730). This is a per-call escape hatch
  only.

**Observed evidence (2026-08-13, CONFIRMED-BY-TEST):**
The reservations endpoint (`GET /v2/reservations`) enforces a
3-year future ceiling. Queries with an end date at +1y, +2y,
+3y all returned HTTP 200. Queries at +5y and +10y returned
HTTP 400 with `{"reason_phrase": "You cannot fetch prices and
availabilities more than 3 years in the future."}`. Note the
misleading message — it names prices/availabilities while gating
a reservations query. This is the same ceiling the `/tasks`
endpoint enforces.

### Key Entities

- **Progress status**: A task's lifecycle phase
  (`progress_status`). Known vocabulary: `not_started`,
  `on_the_way`, `arrived`, `in_progress`, `completed`, `cancelled`.
  Nullable upstream; null is treated as `not_started`.
- **Assignment status**: A task's assignment phase
  (`assignment_status`). Known vocabulary: `pending`, `accepted`,
  `rejected`, `cancelled`, `unassigned`. Separate dimension from
  progress status — the two `cancelled` values are distinct.
- **Listing**: A property's channel-specific presence (e.g. Airbnb
  listing, Vrbo listing). Carries `platform`, `platform_id`,
  `platform_email`, `platform_picture`, and `co_hosts`.
- **Trace ID**: The `x-hospitable-trace` response header value. An
  opaque correlation string assigned by Hospitable's infrastructure.
- **Per-call window override**: Optional `lookforward_days` and
  `lookbackward_days` integer fields on `get_reservations` that
  override the configured window for a single call. Each is
  independent and has its own default.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The task-count sensor's four breakdown attributes sum
  to its state value for every poll cycle where all task
  `progress_status` values are members of the known six-value
  vocabulary.
- **SC-002**: `platform_email` and `platform_picture` are absent
  from all service responses when `guest_contact_details` is
  disabled, verified by test.
- **SC-003**: `uv run mypy` with no arguments reports exactly the
  same errors as `uv run mypy custom_components/ tests/`.
- **SC-004**: A diagnostics download taken after an API error
  includes the `x-hospitable-trace` value from that error's
  response.
- **SC-005**: All 590 existing tests continue to pass (spec-only
  gate; implementation tests will be added per deliverable).
- **SC-006**: No unknown listing key passes through the response
  privacy chokepoint unfiltered.
- **SC-007**: `get_reservations` with `lookforward_days: 400`
  returns reservations beyond the configured `lookahead_days`
  window, verified by test. Out-of-range values raise
  `ServiceValidationError` (with the service confirmed
  registered first to avoid `ServiceNotFound` false passes).

## Assumptions

- **Release status (as of 2026-08-13):** This integration has never
  been released. There are no git tags, the sole GitHub release
  (`v0.0.1`) is a draft that was never published, and
  `manifest.json` reads version `0.1.0`. There are no known
  third-party installations; no backwards-compatibility, migration,
  or upgrade-path constraint applies at this time.

- **Deliverable 2 gating decision interpretation:** The maintainer
  approved "go with your suggestion" in response to a question
  phrased ambiguously — it could have meant "confirm the existing
  hole is acceptable" OR "gate the fields." This specification
  interprets the approval as GATE, because gating is consistent
  with the project's fail-closed, allowlist posture established
  across FR-046, FR-047, FR-047b, and FR-048. If the maintainer
  intended to confirm the hole, this interpretation should be
  corrected before implementation proceeds.

- **Cancelled task evidence is vocabulary-driven, not observed.**
  No task with `progress_status == cancelled` has been observed in
  any live data sample (150-day window, 119 tasks, 13 properties).
  The bucket is added because `meta.progress_statuses` declares
  `cancelled` as a valid value (CONFIRMED-BY-TEST), and the
  maintainer has decided the breakdown must reconcile. Any test
  fixture containing a cancelled task is a synthetic construct, not
  a reproduction of observed data.

- **`assignment_status` nulls:** `assignment_status` was null on
  all 100 sampled tasks. The `cancelled` value in
  `meta.assignment_statuses` has never been observed on a real task
  either. The FR-002 distinction between the two `cancelled`
  dimensions is preventive.

- **Trace header presence is unverified on success responses.**
  The `x-hospitable-trace` header has been observed on error
  responses (CONFIRMED-BY-TEST via the coordinator comment). Its
  presence on success responses is UNVERIFIED but LIKELY given
  standard correlation-header patterns. The implementation MUST
  tolerate its absence regardless.

- **Diagnostics platform registration:** The `diagnostics.py`
  module was added in spec 002 implementation and includes the
  required `async_get_config_entry_diagnostics` entrypoint. This
  specification assumes it remains registered and callable.

## Open Questions

- **OQ-001 — Listing allowlist completeness.** The listing
  allowlist (FR-011) includes `platform`, `platform_id`,
  `co_hosts`, `platform_email`, and `platform_picture`. If the
  upstream listing shape carries additional keys that have
  operational value (e.g. `listing_url`, `status`), the allowlist
  may need expansion. The implementation PR should confirm the
  live listing shape and adjust the allowlist accordingly. Any
  addition must be explicitly decided, not silently passed through.

- **OQ-002 — Pagination on widened windows.** The reservations
  endpoint uses `per_page: 100` (hardcoded in
  `build_reservation_params`). A `lookforward_days: 1095` call
  could exceed 100 reservations for a high-volume property. The
  current implementation does not paginate beyond the first page.
  Whether pagination should be added — or whether a warning in
  the response is sufficient — is deferred to the implementation
  PR. The spec notes the risk but does not mandate a solution.

## Out of Scope

- **Write operations of any kind.** All five deliverables are
  read-only or configuration-only.
- **New sensors or entities.** Deliverable 1 adds an attribute to
  an existing sensor; it does not create a new entity.
- **Task assignment status buckets.** Only progress status is
  bucketed. Assignment status tracking is not specified.
- **Rate-limit header capture.** Only `x-hospitable-trace` is
  captured; `x-ratelimit-*` headers remain unhandled.
- **Changes to `lookback_days` / `lookahead_days` bounds.**
  Deliverable 5 is a per-call escape hatch; the configured option
  bounds are unchanged.
- **Exposing `date_query` parameter.** The query semantic remains
  fixed at `checkin` (FR-029).
- **Absolute `start_date`/`end_date` fields on
  `get_reservations`.** Superseded by relative day-count
  parameters (see Deliverable 5 design decision).
- **OAuth.** Deferred as in spec 001.
- **Webhooks.** Deferred as in spec 001.
- **Production code or tests.** This is a specification-only
  deliverable; implementation follows in separate PRs.

## Cross-specification references

- **Spec 001** — Property sensor attribute contract (task sensors
  inherit the same coordinator pattern).
- **Spec 002 FR-032** — Task sensor definition (amended by FR-001
  through FR-008: cancelled bucket added, sum guarantee introduced).
- **Spec 002 FR-038b** — `guest_contact_details` option (governs
  FR-009 gating).
- **Spec 002 FR-046** — Exposure surface parity principle (FR-009
  adds listing fields to its scope).
- **Spec 002 FR-047b** — Co-host privacy allowlist and scope
  boundary note (scope boundary superseded by FR-009; co-host
  allowlist preserved by FR-013).
- **Spec 002 FR-048** — Response-privacy chokepoint (FR-010
  mandates routing through it).
- **Spec 003 FR-007** — Co-host data in `list_properties` response
  (FR-013 preserves this dependency).
- **Spec 003 FR-017/FR-018** — `ServiceValidationError` on
  conflicting or missing inputs (FR-028 applies the same
  convention to out-of-range day counts).
