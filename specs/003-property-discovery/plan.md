<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Implementation Plan: Property Discovery

**Branch**: `003-property-discovery` | **Date**: 2026-08-13 |
**Spec**: [spec.md](./spec.md)

**Input**: Feature specification from
`specs/003-property-discovery/spec.md`

## Summary

Close the property discovery gap through three coordinated changes:
a `list_properties` action serving curated property and co-host data
from the coordinator cache (no API call), a `property_id` attribute
on the property sensor, and entity/device targeting on the two
property-scoped actions. All changes are strictly read-only.

The technical approach is shaped by three forces:

1. **No new API requests.** The properties coordinator already polls
   `GET /properties?include=listings`. The raw co-host data arrives
   in that response and is discarded at parse time. Extending the
   parser to retain it lets `list_properties` serve from cache,
   honouring the real request budget (FR-009).
2. **One privacy chokepoint.** Co-host objects pass through the
   existing `actions/response.py` serialiser. No second filtering
   path is introduced (FR-048).
3. **One resolution helper.** Target conflict detection (FR-017) is
   implemented once in `resolve_property_id` and shared by both
   property-scoped actions (FR-019).

## Technical Context

**Language/Version**: Python 3.14, fully type annotated, `mypy` zero
errors. (Unchanged from specs 001 and 002.)

**Primary Dependencies**: No new runtime dependencies. `httpx`
remains the HTTP stack.

**Storage**: Home Assistant config entry storage only. No new options,
no config entry migration.

**Testing**: Same stack as specs 001 and 002. New test files under
`tests/actions/` and `tests/api/`. Existing `tests/sensor/
test_property_info.py` updated for the nine-attribute contract.
All HTTP mocked with `respx`.

**Target Platform**: Home Assistant 2026.8.0+ (unchanged).

**Scale**: One new service, one modified entity attribute, two
modified service schemas, one new model dataclass, one modified model
dataclass, one new action module, one modified helper module. ~5 new
or modified production modules.

**Unknowns resolved in planning**:

- Co-host model design: three-field frozen dataclass, parsed at
  model layer, gated at chokepoint. See
  [research.md D-01](./research.md#d-01).
- Cache-only service: properties coordinator provides all data.
  See [research.md D-02](./research.md#d-02).
- Target resolution: shared `resolve_property_id` helper. See
  [research.md D-04](./research.md#d-04).

**Unknowns not resolved** (none): All NEEDS CLARIFICATION items
were resolved in research. No open questions remain.

## Constitution Check

**Result: PASS. No constitutional principle is violated or waived.**

| Principle | Status | How this design satisfies it |
| --- | --- | --- |
| I. Code Quality & Testing | PASS | TDD red-phase protocol for every deliverable. All new modules typed and docstring-complete. `interrogate --fail-under=100` maintained |
| II. API Client Design | PASS | No new API calls. No new client methods. Co-host data already fetched; parser extended to retain it |
| III. Atomic Commits | PASS | Red-phase commits separate from green. Plan artifacts separate from code. Each deliverable independently committable |
| IV. Licensing | PASS | All new files carry inline SPDX headers. New spec files covered by existing `REUSE.toml` annotation for `specs/**` |
| V. Pre-Commit Integrity | PASS | No `--no-verify`. `markdownlint` covers new spec files. No new hooks needed |
| VI. Agent Co-Authorship & DCO | PASS | All commits `git commit -s` with `Co-authored-by: Copilot` trailer |
| VII. User Experience Consistency | PASS | Service name follows `hospitable.list_properties`. Target picker uses HA standard UI pattern. Error messages name the remedy |
| VIII. Performance | PASS | `list_properties` is cache-only — zero API cost. Target resolution is O(1) device registry lookup. No new coordinator |
| IX. Phased Development | PASS | Three deliverables (A, B, C), independently shippable. Each has defined exit criteria |
| X. Security & Credentials | PASS | No credential handling changes. Co-host data is operator team data, not guest PII. `property_id` is an opaque UUID with no PII |
| XI. Webhooks & Real-Time Events | NOT APPLICABLE | No webhooks introduced |
| XII. Red-Phase Commit Protocol | PASS | Every deliverable opens with `@pytest.mark.xfail(raises=..., strict=True)` tests. Concrete red-phase strategy in [research.md D-08](./research.md#d-08) |

## Project Structure

### Documentation (this feature)

```text
specs/003-property-discovery/
├── spec.md                          # Input (merged, authoritative)
├── plan.md                          # This file
├── research.md                      # Phase 0: decisions
├── data-model.md                    # Phase 1: models and entities
├── quickstart.md                    # Phase 1: validation guide
└── contracts/
    ├── services.md                  # New/modified service definitions
    └── entities.md                  # Modified entity contract
```

### Source Code (new and modified modules)

```text
custom_components/hospitable/
├── api/
│   └── models.py              # (MODIFIED) HospitableCoHost dataclass;
│                              #   HospitableListing gains co_hosts field
├── actions/
│   ├── __init__.py            # (MODIFIED) sixth service in table
│   ├── schemas.py             # (MODIFIED) list_properties schema;
│   │                          #   get_reservations/get_property_info
│   │                          #   property_id becomes Optional
│   ├── helpers.py             # (MODIFIED) resolve_property_id added
│   ├── list_properties.py     # (NEW) list_properties handler
│   ├── get_reservations.py    # (MODIFIED) uses resolve_property_id
│   └── get_property_info.py   # (MODIFIED) uses resolve_property_id
├── sensor/
│   └── property.py            # (MODIFIED) property_id in attributes
├── strings.json               # (MODIFIED) list_properties text;
│                              #   target field text on existing services
├── translations/en.json       # (MODIFIED) same additions
└── services.yaml              # (MODIFIED) list_properties definition;
                               #   target on get_reservations,
                               #   get_property_info

tests/
├── actions/
│   ├── test_list_properties.py    # (NEW) list_properties tests
│   └── test_property_targeting.py # (NEW) target resolution tests
├── api/
│   └── test_models.py             # (MODIFIED) co-host parsing tests
└── sensor/
    └── test_property_info.py      # (MODIFIED) nine-attribute contract
```

## Architecture: Read-Only Enforcement

This feature is entirely read-only. The enforcement layers from spec
002 (D-01) are unchanged:

1. **Type-level**: No `_post` method on `HospitableApiClient`.
   `list_properties` uses only coordinator cache reads.
2. **Instance-level**: Coordinators hold base client instances.
3. **Import-level**: No new import of `HospitableWriteClient` or
   `_post` anywhere.
4. **Lifecycle-level**: `test_no_writes.py` continues to assert zero
   non-GET requests during polling.

**New module `actions/list_properties.py`**: This module imports from
`actions/helpers.py` only. It does NOT import any API client class,
because it reads from coordinator cache, not from the API. The
write-isolation import scan in `test_write_isolation.py` already
excludes `actions/` from the polling surface, so no scan change is
needed.

## File Size Awareness

The `aislop` pre-commit hook enforces a ~440-line limit per file.
Current line counts for files this feature modifies:

| File | Current lines | Change | Projected |
| --- | --- | --- | --- |
| `api/models.py` | 439 | +20 (CoHost + parsing) | ~459 (**OVER**) |
| `actions/helpers.py` | 216 | +50 (resolve_property_id) | ~266 |
| `actions/__init__.py` | 167 | +8 (table entry + import) | ~175 |
| `actions/schemas.py` | 88 | +10 (new schema + Optional) | ~98 |
| `sensor/property.py` | 297 | +3 (attribute) | ~300 |
| `actions/get_reservations.py` | 126 | +10 (resolver call) | ~136 |
| `actions/get_property_info.py` | 82 | +10 (resolver call) | ~92 |

**`api/models.py` at 439 is ALREADY at the ~440 aislop threshold.**
Adding ~20 lines puts it at ~459, which is OVER. The implementation
stage MUST resolve this. Options:

1. Extract the co-host dataclass to a separate `api/co_host.py` — but
   this was rejected in D-01 as over-engineering for three fields.
2. Trim the existing file — the `__all__` re-export block and the
   `_optional_str` helper could move.
3. Add `HospitableCoHost` as a nested definition or place it in the
   listing section, and trim docstrings or consolidate methods.

The implementation stage must resolve this. The plan records the
constraint so the implementer is not surprised.

**New file `actions/list_properties.py`**: Estimated ~80-100 lines.
Well within the limit.

## Phase breakdown

Three deliverables in one PR, independently committable. Each follows
the two-commit sequence (red then green) per Principle XII.

### Deliverable A — `list_properties` action (P1)

**Delivers**: `HospitableCoHost` dataclass; extended
`HospitableListing`; `actions/list_properties.py` handler; schema;
registration in table; service text in `strings.json`,
`translations/en.json`, `services.yaml`; tests.

**Requirements**: FR-003 to FR-010, FR-021, FR-023.

**Why highest priority**: This is the primary ask. Without it, none
of the property-scoped actions are usable without undocumented
hackery (spec overview).

**Red-phase sequence (Principle XII)**:

1. Red: Tests for `HospitableCoHost` existence and
   `HospitableListing.co_hosts` field. `raises=ImportError` for the
   new class; `raises=AssertionError` for the field on the existing
   class.
2. Red: Tests for `list_properties` handler existence and response
   shape. `raises=ImportError` for the handler;
   `raises=AssertionError` for registration in service table.
3. Green: Implement `HospitableCoHost`, extend `HospitableListing`,
   implement handler, register service.

**Exit criteria**: `list_properties` callable; all known properties
returned with curated shape; co-hosts present; zero API calls issued;
chokepoint filters co-host contact fields; multi-entry disambiguation
works; write-isolation tests green.

### Deliverable B — `property_id` attribute (P2)

**Delivers**: `property_id` in `PROPERTY_INFO_ATTRIBUTES`; updated
docstring; updated test docstrings.

**Requirements**: FR-011 to FR-014.

**Why independently shippable**: A user can see the property ID in
Developer Tools without any action call.

**Red-phase sequence**:

1. Red: Test that `PROPERTY_INFO_ATTRIBUTES` contains
   `"property_id"`. `raises=AssertionError` because the tuple
   currently has eight entries.
2. Red: Test that the sensor's `extra_state_attributes` dict
   includes a `property_id` key. `raises=AssertionError`.
3. Green: Add `"property_id"` to tuple, return it in
   `extra_state_attributes`, update docstring.

**Exit criteria**: Nine attributes on the sensor. `property_id`
value is the correct UUID. All eight original attributes unchanged.
`test_property_info.py` green.

### Deliverable C — Entity/device targeting (P3)

**Delivers**: `resolve_property_id` in `actions/helpers.py`; modified
`get_reservations.py` and `get_property_info.py`; modified schemas;
`target` in `services.yaml`; target field text in `strings.json` and
`translations/en.json`; tests.

**Requirements**: FR-015 to FR-020, FR-024.

**Why independently shippable**: The two property-scoped actions
accept picker targets. Existing callers that supply `property_id`
directly are unaffected (FR-016, SC-006).

**Red-phase sequence**:

1. Red: Test that `resolve_property_id` exists in
   `actions.helpers`. `raises=ImportError`.
2. Red: Tests for conflict detection (same property → proceed;
   different → error; neither → error). `raises=ImportError` (the
   function does not exist yet).
3. Green: Implement `resolve_property_id`, modify handlers and
   schemas.

**Exit criteria**: Both services accept targets. Conflict rule
enforced. Cross-entry rejection works. Direct `property_id` still
works. Write-isolation tests green.

## Deviation record

### Deviation 1: `api/models.py` may exceed file-size limit

**Instruction context**: The `aislop` hook rejects files over ~440
lines. `api/models.py` is at 439.

**What this plan does**: Records the constraint and defers resolution
to the implementation stage, because the exact approach depends on
which trimming option best preserves readability.

**Why**: The 20-line addition (dataclass + parser extension) puts the
file at ~459. The implementation stage has three options (extract,
trim, consolidate) and must choose one. The plan cannot pre-decide
without knowing which option the pre-commit hook accepts.

**Cost of being wrong**: A pre-commit failure on the first attempt,
fixed by moving code. No user-visible effect.

### Deviation 2: No `contracts/upstream-requests.md`

**Instruction context**: Spec 002 produced an upstream-requests
contract documenting new API requests.

**What this plan does**: Omits this artifact.

**Why**: Spec 003 introduces ZERO new API requests (FR-009).
`list_properties` reads from cache. The two modified services
(`get_reservations`, `get_property_info`) already have their upstream
requests documented in spec 002. There is nothing to add.

### A spec 001 contract change: the property sensor attribute count

Spec 001 established exactly eight property sensor attributes. Spec
003 FR-013 formally amends this to nine. The change is called out in
[contracts/entities.md](./contracts/entities.md) rather than made
silently.

### A spec 002 contract change: the service count

Spec 002 stated five services. Spec 003 adds a sixth. Called out in
[contracts/entities.md](./contracts/entities.md).

### A spec 002 contract change: property-scoped service schemas

Spec 002 defined `get_reservations` and `get_property_info` with
`property_id` as REQUIRED. Spec 003 FR-015/FR-016 change it to
OPTIONAL and add a target definition. Called out in
[contracts/services.md](./contracts/services.md).
