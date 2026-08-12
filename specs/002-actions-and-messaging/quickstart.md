<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Quickstart Validation Guide: Actions and Messaging

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Prerequisites

- Home Assistant 2026.8.0+ with the Hospitable integration installed
  (spec 001 fully implemented)
- At least one config entry with a valid PAT and selected properties
- `uv` installed for running the test suite
- All spec 001 tests passing (`uv run pytest`)

## Validation Scenarios

### VS-1: Polling lifecycle remains write-free

**Purpose**: Prove FR-001/FR-002 — no writes from coordinators.

```shell
uv run pytest tests/test_no_writes.py -v
```

**Expected**: All assertions pass. Zero POST/PUT/PATCH/DELETE requests
captured during setup → refresh → options change → reload → unload.
The test is narrowed to cover the polling lifecycle only.

### VS-2: Send message service (mocked)

**Purpose**: Prove the send-message service issues a correctly shaped
POST and returns an acceptance response.

```shell
uv run pytest tests/actions/test_send_message.py -v
```

**Expected**: Tests cover:

- Happy path: 202 returned, response contains `{"accepted": true}`
- Rate limit: pre-call rejection with explanatory message
- sender_id on non-Airbnb: `ServiceValidationError` before API call
- HTTP 422: `ServiceValidationError` with detail from body
- HTTP 403: `HomeAssistantError` explaining capability limitation

### VS-3: Read messages service (mocked)

**Purpose**: Prove the get-messages service returns the thread.

```shell
uv run pytest tests/actions/test_get_messages.py -v
```

**Expected**: Tests cover paginated and non-paginated responses,
not-found as return value, PII never logged.

### VS-4: Lookup services (mocked)

**Purpose**: Prove find_reservation, get_reservations, get_property_info
return structured data with not-found handled as return values.

```shell
uv run pytest tests/actions/test_lookups.py -v
```

### VS-5: Task sensors

**Purpose**: Prove task coordinator paginates, maps types correctly,
and task sensors report expected state.

```shell
uv run pytest tests/sensor/test_tasks.py -v
```

**Expected**: Maintenance correctly labelled (task_type 5 ≠ service_id
8). All pages fetched. Task count matches total.

### VS-6: Guest attributes on reservation entity

**Purpose**: Prove guest data appears as unrecorded attributes when
`include=guest` returns data.

```shell
uv run pytest tests/sensor/test_reservation.py -k guest -v
```

**Expected**: `guest_first_name` present, `guest_email` absent by
default, all guest attributes in `_unrecorded_attributes`.

### VS-7: PII audit

**Purpose**: Prove SC-003 — no guest PII in logs or diagnostics.

```shell
uv run pytest tests/test_privacy.py -v
```

**Expected**: Diagnostics shows `"**REDACTED**"` for guest fields.
DEBUG log capture contains zero guest names, emails, phone numbers,
message bodies.

### VS-8: Multi-entry disambiguation

**Purpose**: Prove FR-008 — auto-select with one entry, error with
multiple.

```shell
uv run pytest tests/actions/ -k disambiguation -v
```

### VS-9: Rate-limit enforcement

**Purpose**: Prove SC-005 — limits enforced in 100% of test scenarios.

```shell
uv run pytest tests/actions/test_rate_limit.py -v
```

**Expected**: 2/min/reservation and 50/5min/token both enforced.
Error message names the limit and approximate reset time.

### VS-10: Static import isolation

**Purpose**: Prove that coordinator and sensor modules never import
from `actions/` or `api.write_client`.

```shell
uv run pytest tests/test_no_writes.py::test_write_module_not_imported_by_polling_code -v
```

## Full suite

```shell
uv run pytest --strict-markers -v
```

All tests (spec 001 + spec 002) must pass together. No spec 001 test
is modified except `test_no_writes.py` (narrowed, not deleted).
