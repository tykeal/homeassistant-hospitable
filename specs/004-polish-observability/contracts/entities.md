<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract: Entity Surface (Spec 004 Amendments)

**Feature**: [../spec.md](../spec.md) |
**Data model**: [../data-model.md](../data-model.md)

This document defines entity changes introduced by spec 004.

## Changes to spec 002 entity contract

### `task_count` sensor attribute contract (AMENDED)

Spec 002 established three breakdown attributes on the task-count
sensor: `pending_count`, `in_progress_count`, `completed_count`.
The docstring and comment stated these deliberately need not sum
to the total because cancelled tasks fall in no bucket.

**Spec 004 amends this to four breakdown attributes.** The addition
is `cancelled_count`. The sum guarantee changes: the four buckets
MUST sum to `task_count` while all progress statuses are members
of the known six-value vocabulary.

| Attribute | Type | Unrecorded | New? | Notes |
| --- | --- | --- | --- | --- |
| `pending_count` | `int` | Yes | No | Unchanged |
| `in_progress_count` | `int` | Yes | No | Unchanged |
| `completed_count` | `int` | Yes | No | Unchanged |
| `cancelled_count` | `int` | Yes | **Yes** | FR-003 |

**Sum guarantee**: `pending_count + in_progress_count +
completed_count + cancelled_count == task_count` when all tasks
have known progress statuses. If an unknown status is encountered,
the task is counted in no bucket and the sum guarantee is suspended
for that poll cycle (FR-005, FR-006).

**Null handling**: `progress_status is None` → `pending_count`.
Unchanged.

### Vocabulary drift guard (NEW)

If a task arrives with a `progress_status` not in any of the four
frozensets and not `None`, the integration logs a warning naming the
value (FR-006). This is a runtime guard, not a test assertion.

A test-time exhaustiveness assertion verifies the four frozensets
cover exactly the known vocabulary (FR-007).

## No new entities

Spec 004 does not introduce new entity types.

## No new sensors

The `cancelled_count` attribute is added to an existing sensor, not
a new one.

## Device scope (unchanged)

One device per selected property. No new devices.

## Platform scope (unchanged)

Sensor only. No new platform.
