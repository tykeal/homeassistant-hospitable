<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Implementation Plan: Polish and Observability

**Branch**: `004-polish-observability` | **Date**: 2026-08-14 |
**Spec**: [spec.md](./spec.md)

**Input**: Feature specification from
`specs/004-polish-observability/spec.md`

## Summary

Five independent deliverables that harden the integration:

1. A fourth `cancelled` progress bucket on the task-count sensor
   with a reconciliation guarantee.
2. Privacy gating of `platform_email` and `platform_picture` on
   listing objects through the existing response chokepoint.
3. A `files` setting in `[tool.mypy]` so bare `uv run mypy` works.
4. Capture of the `x-hospitable-trace` response header on errors
   and in the diagnostics payload.
5. Optional `lookforward_days` / `lookbackward_days` parameters on
   `get_reservations` for per-call window overrides.

Each deliverable is independent and ships in its own PR. No
deliverable depends on another. The ordering recommendation is
D3 → D1 → D2 → D4 → D5 (smallest risk first).

## Technical Context

**Language/Version**: Python 3.14, fully type annotated, `mypy`
strict mode. (Unchanged from specs 001–003.)

**Primary Dependencies**: No new runtime dependencies. `httpx`
remains the HTTP stack.

**Storage**: Home Assistant config entry storage only. No new
options, no config entry migration.

**Testing**: Same stack as specs 001–003. `pytest` with
`pytest-homeassistant-custom-component`, HTTP mocked with `respx`.
All five deliverables add tests under `tests/`.

**Target Platform**: Home Assistant 2026.8.0+ (unchanged).

**Scale**: Five small, independent changes. ~10 production files
modified, ~5 new test files or test additions. No new entities, no
new coordinators, no new API calls (except that Deliverable 5
changes the window parameters on an existing call).

**Release status**: This integration has never been released. No
git tags, no published releases, no known third-party
installations. No backwards-compatibility, migration, or
upgrade-path constraint applies.

## Constitution Check

**Result: PASS. No constitutional principle is violated or waived.**

| Principle | Status | How this design satisfies it |
| --- | --- | --- |
| I. Code Quality & Testing | PASS | TDD red-phase protocol for D1, D2, D4, D5. D3 is configuration-only (exempt). All new code typed and docstring-complete |
| II. API Client Design | PASS | D4 adds trace capture to existing client error path. No new API calls. D5 changes query parameters on an existing call |
| III. Atomic Commits | PASS | Red-phase commits separate from green. Plan artifacts separate from code. Each deliverable independently committable |
| IV. Licensing | PASS | All new files carry inline SPDX headers. Spec files covered by existing `REUSE.toml` annotation |
| V. Pre-Commit Integrity | PASS | No `--no-verify`. `markdownlint` covers new spec files. No new hooks needed |
| VI. Agent Co-Authorship & DCO | PASS | All commits `git commit -s` with `Co-authored-by: Copilot` trailer |
| VII. User Experience | PASS | D5 adds service fields with descriptive text. Error messages name the allowed range |
| VIII. Performance | PASS | D1 adds O(n) loop over tasks already in memory. D4 reads one header. D5 changes parameters, not request count |
| IX. Phased Development | PASS | Five deliverables, independently shippable, each with defined exit criteria |
| X. Security & Credentials | PASS | No credential handling changes. Trace ID is operational, not PII. Listing fields gated behind existing opt-in |
| XI. Webhooks | NOT APPLICABLE | No webhooks introduced |
| XII. Red-Phase Commit Protocol | PASS | Per-deliverable strategy in [research.md D-07](./research.md#d-07). D3 explicitly exempt (configuration-only) |

## Project Structure

### Documentation (this feature)

```text
specs/004-polish-observability/
├── spec.md              # Input (authoritative)
├── plan.md              # This file
├── research.md          # Phase 0: decisions D-01 to D-08
├── data-model.md        # Phase 1: model changes
├── quickstart.md        # Phase 1: validation guide
└── contracts/
    ├── services.md      # Modified get_reservations contract
    └── entities.md      # Modified task-count sensor contract
```

### Source Code (new and modified modules)

```text
custom_components/hospitable/
├── sensor/
│   └── tasks.py           # (MODIFIED) D1: CANCELLED_STATUSES,
│                          #   cancelled_count, drift guard
├── actions/
│   ├── response.py        # (MODIFIED) D2: LISTING_KEYS, filter
│   ├── get_property_info.py  # (MODIFIED) D2: docstring update
│   ├── get_reservations.py   # (MODIFIED) D5: window params
│   └── schemas.py         # (MODIFIED) D5: new schema fields
├── api/
│   ├── client.py          # (MODIFIED) D4: trace on error
│   ├── exceptions.py      # (MODIFIED) D4: trace_id attribute
│   └── reservations.py    # (unchanged)
├── coordinator_tasks.py   # (MODIFIED) D4: store last trace
├── coordinator.py         # (MODIFIED) D4: store last trace
├── diagnostics.py         # (MODIFIED) D4: trace in payload
├── services.yaml          # (MODIFIED) D5: new fields
├── strings.json           # (MODIFIED) D5: field descriptions
└── translations/en.json   # (MODIFIED) D5: field descriptions

pyproject.toml             # (MODIFIED) D3: mypy files setting

tests/
├── sensor/
│   └── test_task_count.py     # (NEW/MODIFIED) D1: bucket tests
├── actions/
│   └── test_response_privacy.py  # (MODIFIED) D2: listing filter
├── api/
│   └── test_client.py        # (MODIFIED) D4: trace capture
└── actions/
    └── test_get_reservations.py  # (MODIFIED) D5: window tests
```

## File Size Awareness

The `aislop` pre-commit hook enforces a ~440 effective line limit.
Current measured line counts and projections for every modified
file:

| File | Current | Deliverable | Δ | Projected |
| --- | --- | --- | --- | --- |
| `actions/helpers.py` | 427 | — | 0 | 427 |
| `api/models.py` | 424 | — | 0 | 424 |
| `api/client.py` | 410 | D4 | +10 | ~420 |
| `sensor/tasks.py` | 298 | D1 | +20 | ~318 |
| `diagnostics.py` | 282 | D4 | +10 | ~292 |
| `api/task_model.py` | 268 | — | 0 | 268 |
| `strings.json` | 246 | D5 | +10 | ~256 |
| `translations/en.json` | 246 | D5 | +10 | ~256 |
| `coordinator_tasks.py` | 148 | D4 | +5 | ~153 |
| `actions/response.py` | 142 | D2 | +40 | ~182 |
| `actions/get_reservations.py` | 132 | D5 | +15 | ~147 |
| `services.yaml` | 124 | D5 | +15 | ~139 |
| `actions/schemas.py` | 98 | D5 | +10 | ~108 |
| `api/exceptions.py` | 95 | D4 | +5 | ~100 |
| `actions/get_property_info.py` | 88 | D2 | +2 | ~90 |
| `api/reservations.py` | 40 | — | 0 | 40 |

**Result: No file exceeds the ~440-line limit.** The two pressure
points (`helpers.py` at 427 and `models.py` at 424) are NOT touched
by any deliverable. No extraction is needed.

## Deliverable breakdown

### Deliverable 1 — Cancelled task progress bucket (P1)

**Delivers**: `CANCELLED_STATUSES` frozenset; `cancelled_count`
attribute; rewritten bucket comment and docstring; vocabulary drift
guard; exhaustiveness test.

**Requirements**: FR-001 to FR-008.

**Files modified**: `sensor/tasks.py`.

**Red-phase strategy**: See [research.md D-07](./research.md#d-07).
Tests pin `raises=ImportError` (for the new frozenset name),
`raises=KeyError` (for the missing attribute), and
`raises=AssertionError` (for the drift guard). Behavioural red
phases — not import-only.

**Exit criteria**: Four buckets sum to `task_count`. Drift guard
logs warnings. Exhaustiveness test passes. Null progress still
counted as pending. Write-isolation tests green.

### Deliverable 2 — Listing field privacy gating (P1)

**Delivers**: `LISTING_KEYS`, `LISTING_ALLOWED`, `LISTING_CONTACT`
constants; `_filter_listings` / `_filter_one_listing` functions;
list-of-dicts handling; docstring update on `get_property_info.py`.

**Requirements**: FR-009 to FR-014.

**Files modified**: `actions/response.py`,
`actions/get_property_info.py`.

**Red-phase strategy**: See [research.md D-07](./research.md#d-07).
Tests pin `raises=ImportError` and `raises=AssertionError`.
Includes a mutation test proving the filter engages on a list of
dicts (Hazard B) and a regression test preserving
`co_hosts[].user_id` (Hazard C).

**Exit criteria**: `platform_email` and `platform_picture` absent
when opt-in disabled, present when enabled. Unknown listing keys
dropped. `co_hosts[].user_id` survives. List-of-dicts path
exercises per-entry filtering. Docstring updated.
Write-isolation tests green.

### Deliverable 3 — Bare `uv run mypy` works (P2)

**Delivers**: `files = ["custom_components", "tests"]` in
`[tool.mypy]` section of `pyproject.toml`.

**Requirements**: FR-015, FR-016.

**Principle XII ruling**: **EXEMPT.** This is a configuration-only
change. Constitution XII's exemptions explicitly list
"configuration-only commits." The `files` setting changes tool
behaviour, not production code behaviour. No red-phase commit.

**Files modified**: `pyproject.toml`.

**Exit criteria**: `uv run mypy` and
`uv run mypy custom_components/ tests/` produce identical output.

### Deliverable 4 — Trace header capture (P2)

**Delivers**: `trace_id` attribute on `HospitableError`;
`last_trace_id` on coordinators; trace in diagnostics payload;
trace in error log messages.

**Requirements**: FR-017 to FR-022.

**Files modified**: `api/exceptions.py`, `api/client.py`,
`coordinator_tasks.py`, `coordinator.py`, `diagnostics.py`.

**Red-phase strategy**: See [research.md D-07](./research.md#d-07).
Tests pin `raises=TypeError` (new constructor kwarg),
`raises=AssertionError` (trace in log/diagnostics). Includes a
characterization test that the diagnostics entrypoint is
importable (ships green, FR-022).

**Exit criteria**: Error responses with trace header produce logs
containing the trace. Diagnostics payload includes per-coordinator
trace IDs. Absent header produces `None`, not empty string.
Trace passes through redactor unredacted. Entrypoint callable.
Write-isolation tests green.

### Deliverable 5 — Relative-day window override (P2)

**Delivers**: `lookforward_days` and `lookbackward_days` fields on
`GET_RESERVATIONS_SCHEMA`; handler logic for per-call window;
docstring rewrite; service text updates.

**Requirements**: FR-023 to FR-032.

**Files modified**: `actions/schemas.py`,
`actions/get_reservations.py`, `services.yaml`, `strings.json`,
`translations/en.json`.

**Red-phase strategy**: See [research.md D-07](./research.md#d-07).
Tests pin `raises=AssertionError`. Service-registration assertion
before every `ServiceValidationError` assertion (Hazard F, FR-028).

**Exit criteria**: `lookforward_days: 400` extends window to 400
days. `lookbackward_days: 30` extends backward to 30 days.
Out-of-range values raise `ServiceValidationError`. Defaults
match FR-024/FR-025 (forward inherits config, backward fixed 7).
`date_query` unchanged. Response through chokepoint. Docstring
rewritten (FR-031, Hazard E). Write-isolation tests green.

## Architecture: Read-Only Enforcement

All five deliverables are read-only or configuration-only. The
enforcement layers from spec 002 are unchanged:

1. **Type-level**: No `_post` method on `HospitableApiClient`.
2. **Instance-level**: Coordinators hold base client instances.
3. **Import-level**: No new import of `HospitableWriteClient`.
4. **Lifecycle-level**: `test_no_writes.py` still asserts zero
   non-GET requests (except the messaging test which is already
   exempted).

The 20 write-isolation tests across `test_no_writes.py`,
`test_write_isolation.py`, and `test_isolation_discovery.py` MUST
remain green. **No existing assertion may be deleted, weakened,
renamed, or skipped.**

## Recommended PR split and ordering

| Order | Deliverable | Risk | Size | Principle XII |
| --- | --- | --- | --- | --- |
| 1 | D3 — bare mypy | None | 1 line | Exempt |
| 2 | D1 — cancelled bucket | Low | ~20 lines + tests | Applies |
| 3 | D2 — listing privacy | Medium | ~40 lines + tests | Applies |
| 4 | D4 — trace header | Medium | ~30 lines + tests | Applies |
| 5 | D5 — window override | Medium | ~40 lines + tests | Applies |

All five are independent. Any ordering works; this one progresses
from simplest to most cross-cutting.

## Deviation record

### No extraction needed (contrast with spec 003)

Spec 003's plan identified `api/models.py` at 439 lines as
exceeding the limit when extended. This spec's deliverables do NOT
modify either pressure-point file (`helpers.py` at 427,
`models.py` at 424). No extraction is needed.

### No new API requests

Deliverables 1, 2, 3, and 4 introduce zero new API requests.
Deliverable 5 changes the query parameters on an existing request,
not the request count.

### Principle XII exemption for Deliverable 3

Explicitly documented in the deliverable section and in
[research.md D-07](./research.md#d-07). Configuration-only changes
are exempt per Constitution XII's exemption list.
