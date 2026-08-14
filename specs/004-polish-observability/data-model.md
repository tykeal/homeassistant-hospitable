<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Data Model: Polish and Observability

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) |
**Research**: [research.md](./research.md)

**Date**: 2026-08-14

## Scope

This describes model-level changes introduced by spec 004. No new
entities, no new coordinators, no new config entry options.

## Modified constants

### `sensor/tasks.py` — Progress bucket frozensets

The existing three frozensets are joined by a fourth:

| Constant | Current value | Change |
| --- | --- | --- |
| `PENDING_STATUSES` | `{"not_started"}` | Unchanged |
| `IN_PROGRESS_STATUSES` | `{"on_the_way", "arrived", "in_progress"}` | Unchanged |
| `COMPLETED_STATUSES` | `{"completed"}` | Unchanged |
| `CANCELLED_STATUSES` | *(does not exist)* | **NEW**: `{"cancelled"}` |

**Contract**: The union of all four frozensets MUST equal exactly
`{"not_started", "on_the_way", "arrived", "in_progress",
"completed", "cancelled"}`. This is asserted by a vocabulary
contract test (FR-007).

**Null handling**: `progress_status is None` → counted as pending.
Unchanged from spec 002.

**Comment block**: The existing comment (lines 38-45 of
`sensor/tasks.py`) states "A CANCELLED task falls in no bucket,
so the buckets deliberately need not sum to the total." This
comment is REMOVED and replaced with text describing the
four-bucket reconciliation guarantee: the buckets sum to
`task_count` while all progress statuses are members of the known
vocabulary.

## Modified entities

### `task_count` sensor — new attribute

The task-count sensor gains one breakdown attribute:

| Attribute | Type | Unrecorded | Notes |
| --- | --- | --- | --- |
| `pending_count` | `int` | Yes (existing) | Unchanged |
| `in_progress_count` | `int` | Yes (existing) | Unchanged |
| `completed_count` | `int` | Yes (existing) | Unchanged |
| `cancelled_count` | `int` | Yes (**NEW**) | FR-003 |

The `_unrecorded_attributes` frozenset gains `"cancelled_count"`.

The `extra_state_attributes` docstring is rewritten from
"A cancelled task appears in no bucket" to describe the sum
guarantee.

### Vocabulary drift guard

If a task's `progress_status` is not `None` and is not a member
of `PENDING_STATUSES | IN_PROGRESS_STATUSES | COMPLETED_STATUSES
| CANCELLED_STATUSES`, the integration logs a warning naming the
unknown value (FR-006). The task is counted in no bucket for that
poll cycle.

## Modified exceptions

### `HospitableError` — trace ID attribute

The base exception gains a `trace_id` parameter:

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `trace_id` | `str \| None` | `None` | FR-017 |

All subclasses inherit this. The constructor signature becomes:

```python
def __init__(
    self,
    message: str,
    *,
    status: int | None = None,
    endpoint: str = "",
    body: str = "",
    trace_id: str | None = None,
) -> None:
```

`HospitableRateLimitError.__init__` must also forward `trace_id`
to `super().__init__`.

## Modified API client

### `_raise_for_status` — trace extraction

Before raising any `HospitableError` subclass, extract
`response.headers.get("x-hospitable-trace")` and pass it as the
`trace_id` keyword argument.

### `_get_with_response` — no change needed

Already returns headers. Callers that need the trace read it from
the returned headers dict.

## Modified coordinators

### Per-coordinator `last_trace_id`

Each coordinator (reservations, properties, tasks) stores
`last_trace_id: str | None` from the most recent successful API
response. Updated after each successful `_get_with_response` call
(or equivalent) by reading
`headers.get("x-hospitable-trace")`.

## Modified diagnostics

### Trace in diagnostics payload

The `_coordinator_section` function includes `last_trace_id` in
each coordinator's section dict. Since this is nested inside the
`coordinators` key, which is in `ALLOWED_TOP_LEVEL`, it passes
through the redactor.

The trace ID is an operational correlation identifier, not personal
data (FR-021). It is NOT redacted.

### Absent trace handling

When the header was not present on the last response,
`last_trace_id` is `None`. The diagnostics payload shows `null`.
No empty string, no misleading value (FR-020).

## Modified response chokepoint

### Listing privacy filter

New constants in `actions/response.py`:

| Constant | Value | Notes |
| --- | --- | --- |
| `LISTING_KEYS` | `frozenset({"listings"})` | FR-011 |
| `LISTING_ALLOWED` | `("platform", "platform_id", "co_hosts")` | FR-011 |
| `LISTING_CONTACT` | `("platform_email", "platform_picture")` | FR-009 |

The `serialize_response` dict comprehension gains a third
conditional branch: `key in LISTING_KEYS` →
`_filter_listings(value, guest_contact=guest_contact)`.

`_filter_listings` handles the list-of-dicts shape identically to
`_filter_co_hosts`: iterates the list, applies the listing
allowlist per entry. Each filtered listing dict is then recursed
through `serialize_response` so that `co_hosts` inside it hits
the existing `CO_HOST_KEYS` branch.

## Modified service schema

### `GET_RESERVATIONS_SCHEMA` — new fields

| Field | Type | Required | Range | Default | Notes |
| --- | --- | --- | --- | --- | --- |
| `lookforward_days` | int | No | 1–1095 | Config `lookahead_days` | FR-023, FR-024, FR-027 |
| `lookbackward_days` | int | No | 0–365 | 7 (fixed) | FR-023, FR-025, FR-026 |

Both use `vol.Optional` with `vol.All(vol.Coerce(int),
vol.Range(min=..., max=...))`.

## No new entities

Spec 004 does not introduce new entity types.

## No new config entry options

The `guest_contact_details` opt-in from spec 002 governs the
listing field gating. No new option is needed.

## No new coordinators

All five deliverables work with existing coordinators.

## No config entry migration

No version bump, no migration.
