<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Quickstart Validation Guide: Polish and Observability

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Prerequisites

- Home Assistant 2026.8.0+ with Hospitable integration installed
  (specs 001 through 003 fully implemented)
- At least one config entry with a valid PAT and selected properties
- `uv` installed for running the test suite
- All 590 existing tests passing (`uv run pytest tests/ -q`)

## Validation Scenarios

### VS-1: Write-isolation gates remain green

**Purpose**: Prove no writes introduced, no isolation assertions
weakened.

```shell
uv run pytest tests/test_no_writes.py tests/test_write_isolation.py \
  tests/test_isolation_discovery.py -v
```

**Expected**: All 20 tests pass. Zero POST/PUT/PATCH/DELETE requests
captured. No existing assertion deleted, weakened, renamed, or
skipped.

### VS-2: Cancelled progress bucket (Deliverable 1)

**Purpose**: Prove FR-001 to FR-008 — four buckets sum to
`task_count`, drift guard logs unknowns.

```shell
uv run pytest tests/sensor/ -k "cancelled or bucket or drift" -v
```

**Expected**: Tests cover:

- `CANCELLED_STATUSES` exists and equals `frozenset({"cancelled"})`
- Union of four frozensets equals the six-value vocabulary
- `cancelled_count` present in `extra_state_attributes`
- A cancelled task increments `cancelled_count`, not other buckets
- Four buckets sum to `task_count`
- `progress_status=None` still counted as pending
- Unknown status logged as warning, not counted in any bucket
- Fixtures document their synthetic nature

### VS-3: Listing privacy gating (Deliverable 2)

**Purpose**: Prove FR-009 to FR-014 — listing fields filtered
through chokepoint.

```shell
uv run pytest tests/actions/test_response_privacy.py \
  -k "listing" -v
```

**Expected**: Tests cover:

- `platform_email` and `platform_picture` absent when opt-in off
- `platform_email` and `platform_picture` present when opt-in on
- Unknown listing key dropped (fail-closed)
- List-of-dicts path exercises per-entry filtering (mutation test)
- `co_hosts[].user_id` survives within listings (regression test)
- `platform` and `platform_id` always present

### VS-4: Bare `uv run mypy` works (Deliverable 3)

**Purpose**: Prove FR-015, FR-016 — bare invocation checks the
same paths.

```shell
uv run mypy 2>&1 | tail -5
uv run mypy custom_components/ tests/ 2>&1 | tail -5
```

**Expected**: Both invocations produce identical output (same
errors, same files checked).

### VS-5: Trace header capture (Deliverable 4)

**Purpose**: Prove FR-017 to FR-022 — trace captured on errors,
surfaced in diagnostics.

```shell
uv run pytest tests/api/test_client.py -k trace -v
uv run pytest tests/ -k "diagnostics and trace" -v
```

**Expected**: Tests cover:

- `HospitableError` accepts `trace_id` kwarg
- Error logged by coordinator includes trace ID when present
- Diagnostics payload includes per-coordinator `last_trace_id`
- Absent header → `None` (not empty string)
- Trace passes through redactor unredacted
- Diagnostics entrypoint importable and callable

### VS-6: Relative-day window override (Deliverable 5)

**Purpose**: Prove FR-023 to FR-032 — per-call window parameters
work.

```shell
uv run pytest tests/actions/test_get_reservations.py \
  -k "lookforward or lookbackward or window" -v
```

**Expected**: Tests cover:

- `lookforward_days: 400` extends window to 400 days forward
- `lookbackward_days: 30` extends window to 30 days backward
- Default forward inherits config `lookahead_days`
- Default backward is fixed 7 days
- `lookforward_days: 1096` → `ServiceValidationError`
  (service registration asserted first)
- `lookbackward_days: 366` → `ServiceValidationError`
  (service registration asserted first)
- `lookbackward_days: 0` → valid (future-only search)
- `lookforward_days: 1095` → valid (boundary inclusive)
- Response through chokepoint, `found` distinction preserved

## Full suite

```shell
uv run pytest tests/ -q
```

All tests (specs 001 + 002 + 003 + 004) must pass together.
No existing test deleted or weakened.

## Static analysis

```shell
uv run ruff check custom_components/ tests/
uv run mypy custom_components/ tests/
uv run mypy
```

All three commands must exit cleanly.
