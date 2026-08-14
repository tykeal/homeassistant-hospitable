<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Phase 0 Research: Polish and Observability

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Date**: 2026-08-14

## Purpose

This document records decisions taken before design, reasoning, and
rejected alternatives for spec 004. It uses the same evidence legend
as the specification.

## Decision index

| ID | Decision | Governing requirements |
| --- | --- | --- |
| D-01 | `CANCELLED_STATUSES` frozenset added, bucket comment rewritten | FR-001 to FR-008 |
| D-02 | Listing privacy filter via `LISTING_KEYS` / `LISTING_CONTACT` pattern | FR-009 to FR-014 |
| D-03 | `files` setting in `[tool.mypy]` | FR-015, FR-016 |
| D-04 | Trace capture on `HospitableError` and per-coordinator last-trace | FR-017 to FR-022 |
| D-05 | `lookforward_days` / `lookbackward_days` on `get_reservations` | FR-023 to FR-032 |
| D-06 | File-size hazard assessment and extraction plan | Hazard A |
| D-07 | Red-phase strategy per deliverable | Constitution XII |
| D-08 | PR split and ordering | Hazard G |

## D-01: Cancelled progress bucket {#d-01}

**Decision**: Add `CANCELLED_STATUSES = frozenset({"cancelled"})` to
`sensor/tasks.py` alongside the existing three frozensets. Add a
`cancelled_count` attribute to the task-count sensor's
`extra_state_attributes`. Add `cancelled_count` to
`_unrecorded_attributes`. Rewrite the comment block (lines 38-45)
to describe the four-bucket reconciliation guarantee. Rewrite the
`extra_state_attributes` docstring to state the sum guarantee.

**Vocabulary drift guard (FR-006)**: In the `extra_state_attributes`
property, after computing the four counts, check each task: if
`progress_status` is not `None` and is not a member of the UNION of
all four frozensets, log a warning naming the unknown value. This
task is not counted in any bucket. The drift guard is a runtime
check, not a test-time assertion.

**Exhaustiveness test (FR-007)**: A unit test asserts that
`PENDING_STATUSES | IN_PROGRESS_STATUSES | COMPLETED_STATUSES |
CANCELLED_STATUSES` equals exactly
`{"not_started", "on_the_way", "arrived", "in_progress",
"completed", "cancelled"}`. This is the vocabulary contract test.

**Null handling (FR-004)**: Unchanged. A task with
`progress_status is None` increments `pending_count`.

**Why `cancelled` is not merged into `COMPLETED_STATUSES`**: A
cancelled task is NOT completed. Counting it as completed would
overstate finished work. The maintainer explicitly wants the
breakdown to reconcile while keeping the semantic distinction.

**Fixture honesty (Hazard D)**: No cancelled task has ever been
observed in live data. Test fixtures use synthetic tasks with
`progress_status="cancelled"` and document this explicitly. No
fixture pretends to reproduce observed data.

**Alternatives considered**:

- *Merge cancelled into completed*: Rejected — semantically wrong,
  and the maintainer specifically requested a separate bucket.
- *Log unknown statuses only once per value*: Rejected — the
  coordinator refreshes periodically; a persistent unknown status
  should remain visible across polls, and the log level is `warning`
  which is not spammy.

## D-02: Listing privacy gating {#d-02}

**Decision**: Introduce a `LISTING_KEYS` frozenset and a
`LISTING_CONTACT` tuple in `actions/response.py`, following the
same pattern as `IDENTITY_KEYS` / `CO_HOST_KEYS`. Add a
`_filter_listings` function that handles the list-of-dicts shape.

The routing in `serialize_response`'s dict comprehension gains a
third branch: `key in LISTING_KEYS` → `_filter_listings(value,
guest_contact=guest_contact)`.

**Allowlist design** (FR-011):

| Listing key | In response? |
| --- | --- |
| `platform` | Always |
| `platform_id` | Always |
| `co_hosts` | Always (then gated per co-host entry) |
| `platform_email` | Only with `guest_contact_details` on |
| `platform_picture` | Only with `guest_contact_details` on |
| Any other key | Dropped (fail-closed) |

`LISTING_ALLOWED = ("platform", "platform_id", "co_hosts")`
`LISTING_CONTACT = ("platform_email", "platform_picture")`

**List-of-dicts handling (FR-012, Hazard B)**: `_filter_listings`
checks `isinstance(value, list)` and iterates, applying the
listing allowlist per entry. A non-list value is recursed through
`serialize_response`. This mirrors `_filter_co_hosts` exactly.

**Critical**: Each filtered listing dict's `co_hosts` key MUST be
further processed through `_filter_co_hosts`. The allowlist
approach achieves this: the filtered listing dict is built with
the allowlisted keys, and then the `co_hosts` value within it is
passed through `_filter_co_hosts`. Implementation detail: after
building the allowlisted dict, recursively call
`serialize_response` on the result so that `co_hosts` hits the
`CO_HOST_KEYS` branch.

**Mutation test (Hazard B)**: Plan a test that supplies a listing
with `platform_email` present and `guest_contact_details` disabled,
then asserts `platform_email` is ABSENT. This test must be
structured so that if the filter were removed or bypassed, the
assertion would fail. Specifically: supply a list of dicts (not a
single dict) to trigger the list path.

**Sender_id regression (Hazard C, FR-013)**: Plan a test that
invokes `list_properties` (or exercises the response chokepoint
with a payload containing `co_hosts[].user_id`) and confirms
`user_id` survives. The `co_hosts` path is unchanged by this
deliverable — the new `LISTING_KEYS` branch does NOT intercept
`co_hosts` at the top level; it only intercepts `listings`. Inside
a listing, `co_hosts` passes through the existing `CO_HOST_KEYS`
branch via recursive `serialize_response`.

**Docstring update (FR-014)**: The `get_property_info.py` module
docstring (lines 10-14) must be rewritten to reflect that
`platform_email` and `platform_picture` are now gated.

**Alternatives considered**:

- *Denylist for platform_email/platform_picture*: Rejected — the
  project's established pattern is allowlist-based, fail-closed.
- *Per-handler filtering in get_property_info.py*: Rejected by
  FR-010 — the chokepoint is the single filtering path.
- *Adding listing keys to IDENTITY_KEYS*: Rejected — listings are
  not identity objects; they have a different allowlist shape.

## D-03: Bare `uv run mypy` works {#d-03}

**Decision**: Add `files = ["custom_components", "tests"]` to
`[tool.mypy]` in `pyproject.toml`.

**Verification**: The mypy `files` setting defines default paths
when no CLI arguments are given. When CLI paths ARE given, they
override `files` (standard mypy behaviour). So existing
`uv run mypy custom_components/ tests/` invocations are unaffected.

**Why not a glob**: `files` accepts a list of paths. Directories
are recursed. No glob is needed.

**Alternatives considered**:

- *Shell alias or Makefile target*: Rejected — the spec requires
  the bare `uv run mypy` invocation to work, and a `files` setting
  is the standard mypy mechanism for this.

## D-04: Trace header capture {#d-04}

**Decision**: Capture `x-hospitable-trace` at two points:

1. **Error path**: In `_raise_for_status` (or in the
   `HospitableError` base class), attach the trace ID from the
   response headers. Every `HospitableError` subclass gains a
   `trace_id: str | None` attribute. The coordinators already log
   `HospitableError` instances; the log formatting is updated to
   include `trace_id` when present.

2. **Success path**: `_get_with_response` already returns headers.
   Each coordinator stores the most recent `x-hospitable-trace`
   value from a successful response. A new attribute
   `last_trace_id: str | None` on the coordinator base (or each
   coordinator individually) holds this.

**Diagnostics surface (FR-019, FR-021)**: The diagnostics payload
gains a `trace_ids` key (or each coordinator section gains
`last_trace_id`). Since `x-hospitable-trace` is an operational
correlation identifier and not personal data, it is added to
`ALLOWED_TOP_LEVEL` in `diagnostics.py` OR surfaced inside the
coordinator section (which is already allowed).

**Absent header (FR-020)**: When the header is missing, the trace
field is `None`. No empty string, no log noise.

**Diagnostics entrypoint (FR-022)**: The entrypoint already exists
and is registered. A test must verify it remains importable and
callable.

**Design choice — per-coordinator trace vs. global**: Per-coordinator
is better because multiple coordinators poll independently. A
global "last trace" would be ambiguous. Storing one trace per
coordinator gives the diagnostics consumer a trace from each poll
domain.

**Where trace is stored on error**: On the `HospitableError`
instance itself. The coordinator catches `HospitableError` and
logs it; the logging format includes `exc.trace_id`.

**Implementation detail**: In `_raise_for_status`, extract
`response.headers.get("x-hospitable-trace")` before raising. Pass
it to the `HospitableError` constructor. Add `trace_id` parameter
to `HospitableError.__init__`.

**Alternatives considered**:

- *Capture all response headers*: Rejected — only the trace header
  is specified; `x-ratelimit-*` is out of scope (spec Out of Scope).
- *Store trace in a separate service*: Rejected — over-engineered;
  a simple attribute on the coordinator and exception suffices.

## D-05: Relative-day window override {#d-05}

**Decision**: Add `lookforward_days` and `lookbackward_days` as
`vol.Optional(vol.All(vol.Coerce(int), vol.Range(min=..., max=...)))`
fields to `GET_RESERVATIONS_SCHEMA`. In the handler, use them to
override the window calculation.

**Schema additions** (in `actions/schemas.py`):

```python
ATTR_LOOKFORWARD_DAYS = "lookforward_days"
ATTR_LOOKBACKWARD_DAYS = "lookbackward_days"

# Added to GET_RESERVATIONS_SCHEMA:
vol.Optional(ATTR_LOOKFORWARD_DAYS): vol.All(
    vol.Coerce(int), vol.Range(min=1, max=1095)
),
vol.Optional(ATTR_LOOKBACKWARD_DAYS): vol.All(
    vol.Coerce(int), vol.Range(min=0, max=365)
),
```

**Validation approach**: Use Voluptuous `vol.Range` for basic range
checking. This raises `vol.MultipleInvalid` (caught by HA as
`ServiceValidationError`) for out-of-range values. This is
consistent with how HA services work — Voluptuous validation
happens before the handler is called.

**Wait — `vol.MultipleInvalid` vs `ServiceValidationError`**: When
HA calls a service, the schema is validated first. If Voluptuous
raises, HA catches it and raises `ServiceValidationError`. So
using `vol.Range` in the schema DOES produce
`ServiceValidationError` at the handler level. The FR-028
requirement is satisfied.

**However**, the error message from `vol.Range` is generic
("value must be at most 1095"). FR-027 says the message must
"name the allowed range". The Voluptuous message does name the
range, but in a generic way. This is acceptable — the service
definition in `services.yaml` and `strings.json` will describe
the fields and their ranges, and the Voluptuous error message is
what HA shows to the user for any schema violation.

**Default logic in handler**: In
`async_handle_get_reservations`, after resolving the config entry:

```python
lookforward = call.data.get(
    ATTR_LOOKFORWARD_DAYS,
    int(entry.options.get(CONF_LOOKAHEAD_DAYS, LOOKAHEAD_DEFAULT)),
)
lookbackward = call.data.get(ATTR_LOOKBACKWARD_DAYS, 7)
```

The forward default inherits from the config entry's
`lookahead_days` (FR-024). The backward default is a fixed 7
(FR-025).

**Window calculation**: Replace the current `start`/`end`
computation:

```python
today = dt_util.utcnow().date()
start = today - timedelta(days=lookbackward)
end = today + timedelta(days=lookforward)
```

**`date_query` unchanged (FR-029)**: `build_reservation_params`
hardcodes `"date_query": "checkin"`. Not exposed.

**Privacy chokepoint preserved (FR-030)**: The response still flows
through `serialize_response`.

**Docstring rewrite (FR-031, Hazard E)**: The
`async_handle_get_reservations` docstring must be rewritten per
the spec's FR-031 language.

**Services text**: Add field descriptions in `services.yaml`,
`strings.json`, and `translations/en.json`.

**ServiceNotFound trap (FR-028, Hazard F)**: Tests MUST assert
`hass.services.has_service(DOMAIN, "get_reservations")` before
asserting `ServiceValidationError` on out-of-range values.

**Alternatives considered**:

- *Absolute start_date/end_date*: Rejected by maintainer directive.
- *Inherit lookback from config option too*: Rejected by FR-025's
  explicit asymmetry — the 7-day fixed default is deliberate.
- *Custom validation in handler instead of vol.Range*: Rejected —
  Voluptuous schema validation is the HA convention and produces
  the correct exception type.

## D-06: File-size hazard assessment {#d-06}

**Decision**: Measure and record current file sizes. Determine
whether any deliverable pushes a file over the ~440-line aislop
limit.

| File | Current lines | Deliverable | Change | Projected |
| --- | --- | --- | --- | --- |
| `actions/helpers.py` | 427 | (none) | 0 | 427 |
| `api/models.py` | 424 | (none) | 0 | 424 |
| `actions/response.py` | 142 | D2 | +40 (listings filter) | ~182 |
| `sensor/tasks.py` | 298 | D1 | +20 (bucket + drift guard) | ~318 |
| `actions/get_reservations.py` | 132 | D5 | +15 (window params) | ~147 |
| `actions/schemas.py` | 98 | D5 | +10 (new fields) | ~108 |
| `api/reservations.py` | 40 | (none) | 0 | 40 |
| `diagnostics.py` | 282 | D4 | +10 (trace in payload) | ~292 |
| `api/client.py` | 410 | D4 | +10 (trace on error) | ~420 |
| `api/exceptions.py` | 95 | D4 | +5 (trace_id attr) | ~100 |
| `coordinator_tasks.py` | 148 | D4 | +5 (store trace) | ~153 |
| `api/task_model.py` | 268 | (none) | 0 | 268 |
| `services.yaml` | 124 | D5 | +15 | ~139 |
| `strings.json` | 246 | D5 | +10 | ~256 |
| `translations/en.json` | 246 | D5 | +10 | ~256 |

**Result: No file exceeds the ~440-line limit.** The two pressure
points (`helpers.py` at 427 and `models.py` at 424) are NOT
modified by any deliverable in this spec. No extraction is needed.

**`api/client.py` at 410 is close but projected at ~420 — safe.**

## D-07: Red-phase strategy per deliverable {#d-07}

**Decision**: Concrete red-phase plan for each deliverable per
Constitution XII.

### Deliverable 1 — Cancelled progress bucket

**Principle XII applies.** This is new observable behaviour.

**Red-phase tests (all `raises=AssertionError`)**:

1. Test that `CANCELLED_STATUSES` exists and equals
   `frozenset({"cancelled"})` — imports the name, asserts value.
   Fails with `AssertionError` because the frozenset does not exist
   yet. Actually, importing a non-existent name from an existing
   module raises `ImportError` in Python 3.14. So
   `raises=ImportError`.
2. Test that the union of all four frozensets equals the known
   vocabulary — fails with `ImportError` (because
   `CANCELLED_STATUSES` does not exist).
3. Test that `extra_state_attributes` includes `cancelled_count` —
   sets up a sensor with fixtures spanning all statuses, asserts
   `cancelled_count` in the result. Fails with `KeyError` because
   the attribute is not returned. Pin `raises=KeyError`.
4. Test that a cancelled task increments `cancelled_count` and NOT
   any other bucket — same setup, assert value. Fails with
   `KeyError`. Pin `raises=KeyError`.
5. Test that the sum of all four buckets equals `task_count` — fails
   with `KeyError`. Pin `raises=KeyError`.
6. Test vocabulary drift guard: supply a task with an unknown
   `progress_status`, assert a warning is logged — fails because
   the drift guard does not exist. The test can import existing
   sensor code, set up the sensor, and assert on `caplog`. Fails
   with `AssertionError` because no warning is logged. Pin
   `raises=AssertionError`.

### Deliverable 2 — Listing privacy gating

**Principle XII applies.** This is new observable behaviour.

**Red-phase tests**:

1. Test that `LISTING_KEYS` exists in `actions/response.py` — fails
   with `ImportError`. Pin `raises=ImportError`.
2. Test that a listing with `platform_email` is filtered when
   `guest_contact_details` is disabled — constructs a payload, runs
   it through `serialize_response`, asserts `platform_email` absent.
   Fails with `AssertionError` because the filter does not exist.
   Pin `raises=AssertionError`.
3. Test the list-of-dicts path: supply `"listings": [{"platform":
   "airbnb", "platform_email": "x@y"}]`, assert `platform_email`
   absent from every entry. Fails with `AssertionError`. Pin
   `raises=AssertionError`.
4. **Mutation test (Hazard B)**: Supply a list of listing dicts with
   `platform_email`, assert absent. This is test 3 but explicitly
   designed so that removing the filter makes it fail.
5. **Regression test (Hazard C)**: Supply a payload with
   `co_hosts[].user_id` inside a listing, assert `user_id` survives.
   This is a green characterization test that ships in the red
   commit as `@pytest.mark.xfail(raises=AssertionError, ...)` if
   the listings path does not yet exist, or as a plain passing test
   if it can be structured against the existing code. Since the
   existing `serialize_response` already handles `co_hosts` via
   `CO_HOST_KEYS`, and this test exercises the chokepoint with a
   payload shaped like `{"listings": [{"co_hosts": [{"user_id":
   "X"}]}]}`, it depends on the new `LISTING_KEYS` branch to route
   `listings` correctly. So it fails in the red phase with
   `AssertionError`. Pin `raises=AssertionError`.

### Deliverable 3 — Bare `uv run mypy`

**Principle XII does NOT apply.** This is a configuration-only
change to `pyproject.toml`. The constitution's XII exemptions
include "configuration-only commits." The `files` setting is a tool
configuration, not observable production behaviour.

**Justification**: Adding `files = [...]` to `[tool.mypy]` does not
change any production code, entity behaviour, API response, or
sensor value. It changes how a developer tool discovers its input
files. This is analogous to adding a lint rule or a test runner
flag.

**Characterization test**: A CI-level verification that
`uv run mypy` and `uv run mypy custom_components/ tests/` produce
identical output. This ships as a green commit.

### Deliverable 4 — Trace header capture

**Principle XII applies partially.**

**The error-path trace capture**: Adding `trace_id` to
`HospitableError` and including it in log messages IS new
observable behaviour. Red-phase tests:

1. Test that `HospitableError` accepts a `trace_id` kwarg — fails
   with `TypeError` because the constructor does not accept it yet.
   Pin `raises=TypeError`.
2. Test that an API error logged by the coordinator includes the
   trace ID — mock an error response with the header, assert
   `trace_id` appears in the log. Fails with `AssertionError`
   (no trace in log). Pin `raises=AssertionError`.

**The success-path trace capture**: Adding `last_trace_id` to the
coordinator and surfacing it in diagnostics IS new observable
behaviour. Red-phase tests:

1. Test that the diagnostics payload includes a trace ID after a
   successful poll — mock a success response with the header, build
   diagnostics, assert presence. Fails with `AssertionError` or
   `KeyError`. Pin `raises=AssertionError`.
2. Test that the trace ID passes through the redactor unredacted —
   assert the value in the redacted payload. Fails with
   `AssertionError`. Pin `raises=AssertionError`.
3. Test that when the header is absent, the trace is `None` (not
   empty string) — fails with `AssertionError`. Pin
   `raises=AssertionError`.

**Diagnostics entrypoint test (FR-022)**: Verify the entrypoint
is importable and callable. This tests EXISTING behaviour, so it
ships green as a characterization test. No `xfail` needed.

### Deliverable 5 — Relative-day window override

**Principle XII applies.** This is new observable behaviour.

**Red-phase tests**:

1. Test that `GET_RESERVATIONS_SCHEMA` accepts `lookforward_days` —
   fails with `vol.MultipleInvalid` (schema rejects unknown keys).
   Pin `raises=MultipleInvalid`.

   **Note**: `vol.Schema({...})` rejects unknown keys by default,
   so the schema WILL reject `lookforward_days` until the field is
   added. The test calls the service with `lookforward_days: 400`
   and asserts the response covers a wider window. Fails with
   `ServiceValidationError` (from schema rejection) in the red
   phase. Pin `raises=ServiceValidationError`.

2. Test that `lookforward_days: 400` extends the window — call the
   service, mock the API, assert the API was called with an end date
   400 days out. Fails with `AssertionError`. Pin
   `raises=AssertionError`.

3. Test that `lookbackward_days: 30` extends the backward window —
   similar. Fails with `AssertionError`. Pin `raises=AssertionError`.

4. Test that `lookforward_days: 1096` raises
   `ServiceValidationError` — FIRST assert service is registered
   (`hass.services.has_service`), then assert the error. Fails with
   `AssertionError` because Voluptuous does not yet reject it (field
   not in schema). Pin `raises=AssertionError`.

5. Test that `lookbackward_days: 366` raises
   `ServiceValidationError` — same pattern. Pin
   `raises=AssertionError`.

6. Test that default `lookforward_days` inherits from config
   `lookahead_days` — call with no params, assert API called with
   the config value. Currently passes (existing behaviour). This is
   a characterization test that ships green — BUT after the
   implementation, the backward default changes from the config
   `lookback_days` to fixed 7. So a characterization test of the
   CURRENT backward default would need to be updated. Plan this
   carefully: the red phase tests the NEW behaviour; the old
   backward default is intentionally changed.

## D-08: PR split and ordering {#d-08}

**Decision**: Five independent PRs, one per deliverable. Recommended
ordering:

1. **PR 1: Deliverable 3** (bare `uv run mypy`) — smallest, zero
   risk, configuration-only. Gets the tooling improvement in first.
   No Principle XII ceremony.

2. **PR 2: Deliverable 1** (cancelled bucket) — self-contained in
   `sensor/tasks.py`. No file-size pressure. Clean red/green cycle.

3. **PR 3: Deliverable 2** (listing privacy) — self-contained in
   `actions/response.py` plus the docstring fix in
   `get_property_info.py`. No file-size pressure. Depends on
   understanding the chokepoint well, so benefits from being done
   after the simpler bucket work.

4. **PR 4: Deliverable 4** (trace header) — touches the API client,
   exceptions, coordinators, and diagnostics. More cross-cutting
   than 1-3. No file-size pressure.

5. **PR 5: Deliverable 5** (window override) — touches the handler,
   schema, service text files. Most surface area in terms of files
   touched, but all changes are small. Last because it benefits
   from the trace header work being in place (a widened window query
   that fails produces a traceable error).

**Independence**: All five PRs can merge in any order. No
deliverable depends on another. The ordering above is a
recommendation based on risk/size gradient, not a dependency chain.

**No extraction needed**: Per D-06, no file exceeds the limit.

## Assumptions

| ID | Assumption | Tier | Fallback |
| --- | --- | --- | --- |
| A-01 | `meta.progress_statuses` contains exactly six values | CONFIRMED-BY-TEST | Exhaustiveness test fails and forces bucket decision |
| A-02 | No cancelled task exists in live data | CONFIRMED-BY-TEST | Fixtures are synthetic, documented as such |
| A-03 | `x-hospitable-trace` present on error responses | CONFIRMED-BY-TEST (coordinator comment) | Absent trace is `None` |
| A-04 | `x-hospitable-trace` present on success responses | UNVERIFIED / LIKELY | Absent trace is `None` |
| A-05 | Reservations endpoint enforces 3-year ceiling | CONFIRMED-BY-TEST | Local validation catches before upstream |
| A-06 | Listing objects carry `platform_email` and `platform_picture` | CONFIRMED-BY-SPEC (get_property_info docstring names them) | Allowlist drops unknown keys |
| A-07 | `assignment_status` is a separate dimension from `progress_status` | CONFIRMED-BY-TEST | Bucket keys only on `progress_status` |

## Spec defects found

None. All 32 functional requirements are internally consistent and
implementable as specified.

## Open Questions carried forward

- **OQ-001** (listing allowlist completeness) — carried from spec.
  Implementation PR for Deliverable 2 should confirm the live
  listing shape and adjust the allowlist if needed.
- **OQ-002** (pagination on widened windows) — carried from spec.
  Deferred to Deliverable 5 implementation PR.
