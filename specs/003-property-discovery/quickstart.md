<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Quickstart Validation Guide: Property Discovery

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Prerequisites

- Home Assistant 2026.8.0+ with Hospitable integration installed
  (specs 001 and 002 fully implemented)
- At least one config entry with a valid PAT and selected properties
- `uv` installed for running the test suite
- All 564 existing tests passing (`uv run pytest tests/ -q`)

## Validation Scenarios

### VS-1: Write-isolation gates remain green

**Purpose**: Prove FR-001/FR-002 — no writes introduced, no
isolation assertions weakened.

```shell
uv run pytest tests/test_no_writes.py tests/test_write_isolation.py \
  tests/test_isolation_discovery.py -v
```

**Expected**: All 20 tests pass. Zero POST/PUT/PATCH/DELETE requests
captured. The new `actions/list_properties.py` module is NOT in the
polling surface — `test_isolation_discovery.py` already excludes the
entire `actions/` package from its filesystem walk, so no list
update is needed. The module must remain excluded (it is an action,
not a polling module).

### VS-2: `list_properties` service (mocked)

**Purpose**: Prove FR-003 through FR-010 — the new service returns
the curated shape from the coordinator cache with no API call.

```shell
uv run pytest tests/actions/test_list_properties.py -v
```

**Expected**: Tests cover:

- Happy path: all 13 known properties returned with curated fields
- `selected: true` for monitored properties, `false` for others
- Co-host objects present with `user_id`, `channel_name`, `name`
- Co-host `email`/`phone_numbers` absent with opt-in off, present
  with opt-in on (chokepoint filtering)
- Empty listings array when a property has no listings
- Multi-entry: `config_entry_id` selects one account
- No API request issued (respx assertion: zero captured requests)

### VS-3: `property_id` on property sensor

**Purpose**: Prove FR-011 through FR-014 — the attribute is present
and the contract is widened to nine.

```shell
uv run pytest tests/sensor/test_property_info.py -v
```

**Expected**: `PROPERTY_INFO_ATTRIBUTES` contains nine entries.
The sensor's `extra_state_attributes` includes `property_id` with
the correct UUID. All eight original attributes remain present.

### VS-4: Entity/device targeting on property-scoped actions

**Purpose**: Prove FR-015 through FR-020 — targets resolve correctly
and conflicts are detected.

```shell
uv run pytest tests/actions/test_property_targeting.py -v
```

**Expected**: Tests cover:

- Device target resolves to correct property_id
- Entity target resolves via device registry
- Both target and property_id, same property → proceeds
- Both target and property_id, different property →
  `ServiceValidationError`
- Neither target nor property_id → `ServiceValidationError`
- Target from wrong integration → `ServiceValidationError`
- Target from different config entry → `ServiceValidationError`
- Direct `property_id` without target → works (scripting path)

### VS-5: Co-host model parsing

**Purpose**: Prove FR-021 — `HospitableListing` retains co-hosts.

```shell
uv run pytest tests/api/test_models.py -k co_host -v
```

**Expected**: `HospitableListing.from_api` parses co-host arrays.
`HospitableCoHost` is a frozen dataclass with three fields. Empty
co-hosts array handled. Malformed entries skipped.

### VS-6: Response chokepoint handles co-hosts

**Purpose**: Prove FR-007 — co-hosts route through the existing
chokepoint with correct allowlist filtering.

```shell
uv run pytest tests/actions/test_response_privacy.py -k co_host -v
```

**Expected**: `user_id`, `channel_name`, `name` pass through.
`email`, `phone_numbers` gated by opt-in. Unknown keys dropped.

## Full suite

```shell
uv run pytest tests/ -q
```

All tests (specs 001 + 002 + 003) must pass together. No existing
test is deleted. `test_property_info.py` docstrings updated from
"eight" to "nine" but no assertion logic changes — the test derives
from the `PROPERTY_INFO_ATTRIBUTES` tuple.
