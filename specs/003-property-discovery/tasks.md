<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Tasks: Property Discovery

**Input**: Design documents from `/specs/003-property-discovery/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`. Spec 002 is complete and merged; its `tasks.md` is the
format and detail precedent for this file.

**Tests**: Test tasks are MANDATORY. Constitution Principle I
(NON-NEGOTIABLE) makes code-level TDD mandatory and Principle IX forbids
deferring unit-level TDD. Per Principle XII (Red-Phase Commit Protocol)
tests land as a red-phase commit containing tests only, with every test
marked `@pytest.mark.xfail(raises=..., reason="...", strict=True)`; the
implementation lands as a separate green-phase commit that removes those
markers and the `# type: ignore[...]` comments.

**Organization**: Tasks are grouped by deliverable / user story so each
can be implemented, tested, and shipped independently. One pull request
containing all three deliverables (this is a single coordinated feature,
not six independent user stories like spec 002). Phase order is strictly
sequential: Setup → Foundational → A → B → C → Polish.

**Checkbox flips**: Task-list checkbox flips (`- [ ]` → `- [X]`) ride
the implementation PR as a SEPARATE atomic commit, per this project's
atomic-commit rule. They are documentation changes, not code changes,
and must not be mixed into red-phase or green-phase commits.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story the task belongs to (US1, US2, US3)
- Exact file paths are given in every task
- Trailing parentheses list the functional requirements the task serves

## Path Conventions

Single project. Integration code lives under
`custom_components/hospitable/`, tests under `tests/`, packaging files at
the repository root. Paths follow `plan.md` §Project Structure.

---

## Red/green phase protocol (read before starting any phase)

Every user-story phase below is split into a **RED PHASE** group and a
**GREEN PHASE** group. They are separate commits. The rules are
mechanical and non-negotiable:

1. **Red-phase commit contains tests only.** No production module may be
   created or edited in it.
2. **Every red-phase test carries `raises=` naming a specific exception
   type.** `strict=True` alone does not check *why* a test failed; when
   `xfailed.raises is None` any exception raised during setup or call
   counts as an expected failure, so a test that fails for the wrong
   reason (a typo, a bad fixture name) still passes the gate and asserts
   nothing. `raises=` is MANDATORY on every marker in this file.
3. **Imports of not-yet-existing modules go inside the test body.** A
   module-level import breaks *collection*, which taints the entire run
   and produces an error rather than an expected failure.
   `pytest.importorskip` is PROHIBITED here: it yields SKIP, which hides
   the gap instead of recording it.
4. **Deferred imports carry `# type: ignore[import-not-found]`.** Use
   `# type: ignore[attr-defined]` where the module exists but the name
   does not — which is the common case when importing a new name from an
   existing module like `actions/helpers.py`.
   `warn_unused_ignores = true` is the mypy analogue of `xfail_strict`
   and forces these to be removed at green phase.
5. **`tests/conftest.py` imports no not-yet-existing module at all.**
   Fixtures needing integration objects are factory fixtures returning a
   callable that performs its import inside its own body.
6. **A red phase where every test dies on `ImportError` proves
   nothing behavioural.** An `ImportError` red phase IS constitutionally
   valid (the constitution's own canonical example uses
   `raises=ImportError`), BUT every deliverable needs at least one
   BEHAVIOURAL red-phase test failing with a genuine `AssertionError`,
   because an import test passes the moment an empty stub exists and
   therefore cannot catch a wrong implementation. Import tests and
   behavioural tests BOTH belong in the red phase.
7. **Before every red-phase commit** run
   `uv run pytest --runxfail <node ids>` **scoped to the new tests only**
   — never bare — and confirm each fails with the declared exception.
8. **The green-phase commit removes the markers and the ignores in the
   same commit that adds the implementation.** `xfail_strict = true`
   turns an unexpected pass into a failure, so a forgotten marker breaks
   the build. That is the intended gate.
9. **Every commit leaves the suite green.** A clone at any commit is
   valid.

**Exemptions (Principle XII §Exemptions)**: pure refactors, docs-only,
CI-only, packaging-only, config-only, and test-only changes that assert
no new production behaviour. Phase 1, Phase 2, and Phase 7 below are
exempt on those grounds and are therefore NOT split red/green.

---

## Phase 1: Setup (test scaffolding and fixtures)

**Purpose**: Test-tree scaffolding and synthetic fixtures that every
later phase depends on. **Ships in**: the single pull request.

**Principle XII status**: EXEMPT — test-only and fixture-only changes
that assert no new production behaviour. Do not force these into a
red/green pair.

- [x] T001 Create `tests/actions/test_list_properties.py` as an empty
      test module with an SPDX header and a module docstring stating it
      covers Deliverable A (`list_properties`). The file MUST NOT import
      any `custom_components.hospitable` module at module level.
- [x] T002 [P] Create `tests/actions/test_property_targeting.py` as an
      empty test module with an SPDX header and a module docstring
      stating it covers Deliverable C (entity/device targeting on
      property-scoped actions). The file MUST NOT import any
      `custom_components.hospitable` module at module level.
- [x] T003 [P] Create `tests/fixtures/properties_with_listings.json`:
      a synthetic properties endpoint response with at least 3
      properties. One property must have 2 listings each with co-hosts
      (each co-host carrying exactly `{channel_name, name, user_id}`);
      one property must have zero listings; one property must have 1
      listing with an empty co-hosts array. All values MUST be obviously
      synthetic (UUIDs like `11111111-...`, names like `Test Property`).
      No real personal data. (FR-005, FR-006, FR-007, FR-008, FR-010)
- [x] T004 [P] Add SPDX headers or `REUSE.toml` coverage for every file
      created in T001..T003 and run `uv run reuse lint` to confirm the
      tree is compliant. JSON fixtures cannot carry comments, so they
      MUST be covered by a `REUSE.toml` annotation.

**Exit criteria**: `uv run pytest` collects cleanly, `uv run reuse lint`
passes, and no fixture contains real personal data.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: The `api/models.py` file-size extraction that MUST happen
BEFORE `HospitableCoHost` can be added, plus any shared constants.

**Principle XII status**: EXEMPT — pure refactor with zero behaviour
change. Do not force into a red/green pair.

**⚠️ BLOCKS all user stories. Complete before starting Phase 3.**

**⚠️ `api/models.py` is at 439 lines against a ~440-line `aislop`
threshold.** Adding `HospitableCoHost` (~20 lines) pushes it OVER and
the commit WILL be rejected by the pre-commit hook. This phase extracts
existing code to make room. The extraction MUST be committed and pass
pre-commit BEFORE any model change.

- [x] T005 Measure the current line count of
      `custom_components/hospitable/api/models.py` (expected: 439).
      Record it in the commit message. Confirm the `aislop` threshold
      by inspecting the pre-commit config. (FR-021)
- [x] T006 Extract `HospitableMessage`, `_optional_str`, and their
      imports from `custom_components/hospitable/api/models.py` into a
      new `custom_components/hospitable/api/message_model.py`. The
      existing `__all__` block at the bottom of `models.py` already
      demonstrates re-export of extracted models (it re-exports
      `HospitableGuest`, `HospitableTask`, etc. from separate files).
      Follow that EXACT pattern: add `HospitableMessage` to the
      `__all__` list, import it from the new module, and ensure every
      existing `from custom_components.hospitable.api.models import
      HospitableMessage` continues to resolve. The new file MUST carry
      an SPDX header. Run `uv run pytest tests/ -q` (expect 564 pass)
      to confirm zero behaviour change. Run `wc -l` on `models.py`
      after the extraction and confirm it is comfortably below 440.
      (FR-021)
- [x] T007 [P] Add a `SERVICE_LIST_PROPERTIES` constant string
      `"list_properties"` to
      `custom_components/hospitable/actions/__init__.py`, below the
      existing five `SERVICE_*` constants. Do NOT add it to the
      `SERVICE_DEFINITIONS` tuple yet (the handler does not exist).
      (FR-003)

**Exit criteria**: `models.py` is well under 440 lines. All 564 tests
pass. All imports of `HospitableMessage` still resolve. The constant
is defined but unused (no warning expected because it will be consumed
in Phase 3).

---

## Phase 3: Deliverable A — `list_properties` action (US1, Priority P1) 🎯 MVP

**Goal**: A user can invoke `hospitable.list_properties` and receive
every known property with curated metadata including co-host user IDs,
served entirely from the coordinator cache with NO API call.

**Independent test**: Call `list_properties` with no arguments against
a mocked coordinator cache holding 3+ properties. Confirm the response
contains all properties with curated fields per FR-005. Confirm zero
API calls were issued.

**Requirements**: FR-001 to FR-010, FR-021, FR-022, FR-023.

### RED PHASE COMMIT — Deliverable A (tests only)

Expected failure modes are stated per task. Groups touching
`api/models.py` and `actions/__init__.py` MUST fail with
`AssertionError`, because those modules already exist —
`ImportError` there means the test is wrong, not the code.

**Behavioural red-phase tests (AssertionError)**: T009, T010, T011,
T014, T015, T016 fail with genuine `AssertionError` against existing
code or against real observed behaviour. These are the tests that
cannot pass from an empty stub and therefore genuinely constrain the
implementation.

**Import red-phase tests (ImportError)**: T008, T012, T013 fail
with `ImportError` because the class or module does not yet exist.
These are constitutionally valid (the constitution's canonical example
uses `raises=ImportError`) but are NOT the only red-phase tests for
this deliverable.

- [x] T008 [P] [US1] In `tests/api/test_models.py`, add an xfail test
      (`raises=ImportError`) asserting that `HospitableCoHost` can be
      imported from `custom_components.hospitable.api.models`. Import
      inside the test body with `# type: ignore[attr-defined]` (the
      module exists but the name does not). Verify the import fails:
      `uv run pytest --runxfail tests/api/test_models.py::<node>`.
      (FR-006, FR-007, FR-021)
- [x] T009 [P] [US1] In `tests/api/test_models.py`, add an xfail test
      (`raises=AssertionError`) asserting that `HospitableListing` has
      a `co_hosts` field. Import `HospitableListing` (it exists) and
      assert `hasattr(HospitableListing(...), "co_hosts")` or
      equivalent. This MUST fail with `AssertionError` because the
      field does not exist on the current two-field dataclass. Verify:
      `uv run pytest --runxfail tests/api/test_models.py::<node>`.
      (FR-006, FR-021)
- [x] T010 [US1] In `tests/api/test_models.py`, add an xfail test
      (`raises=AssertionError`) asserting that
      `HospitableListing.from_api` parses co-hosts from a payload
      containing `co_hosts: [{user_id: "u1", channel_name: "c1",
      name: "n1"}]`. Assert the parsed listing's `co_hosts` tuple has
      length 1 and the first element's `user_id == "u1"`. This MUST
      fail with `AssertionError` because `from_api` currently discards
      co-host data. Verify:
      `uv run pytest --runxfail tests/api/test_models.py::<node>`.
      (FR-006, FR-007, FR-021)
- [x] T011 [P] [US1] In `tests/api/test_models.py`, add an xfail test
      (`raises=AssertionError`) asserting that
      `HospitableListing.from_api` with a payload that has NO
      `co_hosts` key produces a listing with `co_hosts == ()`. Verify:
      `uv run pytest --runxfail tests/api/test_models.py::<node>`.
      (FR-006, FR-021)
- [x] T012 [P] [US1] In `tests/actions/test_list_properties.py`, add
      an xfail test (`raises=ImportError`) asserting that
      `async_handle_list_properties` can be imported from
      `custom_components.hospitable.actions.list_properties`. Import
      inside the test body with
      `# type: ignore[import-not-found]`. Verify:
      `uv run pytest --runxfail tests/actions/test_list_properties.py::<node>`.
      (FR-003)
- [x] T013 [P] [US1] In `tests/actions/test_list_properties.py`, add
      an xfail test (`raises=ImportError`) asserting that
      `LIST_PROPERTIES_SCHEMA` can be imported from
      `custom_components.hospitable.actions.schemas`. Import inside the
      test body with `# type: ignore[attr-defined]`. Verify:
      `uv run pytest --runxfail tests/actions/test_list_properties.py::<node>`.
      (FR-004)
- [x] T014 [US1] In `tests/actions/test_list_properties.py`, add an
      xfail test (`raises=AssertionError`) asserting that
      `"list_properties"` appears as a `name` in the
      `SERVICE_DEFINITIONS` tuple in `actions/__init__.py`. Import
      `SERVICE_DEFINITIONS` (it exists — the handler import is NOT
      added until the green phase T022) and assert any definition has
      `name == "list_properties"`. This MUST fail with
      `AssertionError` because the tuple contains only five entries
      and none is named `"list_properties"`. No `# type: ignore` is
      needed — the module and the name both exist. Verify:
      `uv run pytest --runxfail tests/actions/test_list_properties.py::<node>`.
      (FR-003, FR-005)
- [x] T015 [US1] In `tests/actions/test_list_properties.py`, add an
      xfail test (`raises=AssertionError`) that sets up a mock
      coordinator cache with 2 properties (one selected, one not) and
      calls the `list_properties` handler. Assert the response is a
      dict with key `"properties"` containing a list of length 2 where
      each entry has exactly the keys `property_id`, `name`,
      `public_name`, `selected`, `listings`. Assert the unselected
      property has `selected: False`. This is a BEHAVIOURAL red-phase
      test. It MUST fail with `AssertionError` because the handler
      does not exist yet and the service call will fail. Use a factory
      fixture or inline mock setup. Verify:
      `uv run pytest --runxfail tests/actions/test_list_properties.py::<node>`.
      (FR-005, FR-008, FR-009, FR-010)
- [x] T016 [P] [US1] In `tests/actions/test_list_properties.py`, add
      an xfail test (`raises=AssertionError`) that sets up a mock
      coordinator with a property whose listing has co-hosts, calls
      `list_properties`, and asserts the response includes co-host
      objects with `user_id`, `channel_name`, and `name` keys. Also
      assert that NO other keys (e.g., `email`, `phone_numbers`) are
      present on the co-host objects when `guest_contact_details` is
      disabled. This is a BEHAVIOURAL red-phase test. Verify:
      `uv run pytest --runxfail tests/actions/test_list_properties.py::<node>`.
      (FR-006, FR-007, FR-010)
- [x] T017 [P] [US1] In `tests/actions/test_list_properties.py`, add
      an xfail test (`raises=AssertionError`) for the multi-entry
      disambiguation: with two loaded entries and no `config_entry_id`,
      the call raises `ServiceValidationError`. With a specific
      `config_entry_id`, only that entry's properties are returned.
      Verify:
      `uv run pytest --runxfail tests/actions/test_list_properties.py::<node>`.
      (FR-004, FR-022)

### GREEN PHASE COMMIT — Deliverable A (implementation)

- [x] T018 [US1] Add the `HospitableCoHost` frozen dataclass to
      `custom_components/hospitable/api/models.py` with fields
      `user_id: str`, `channel_name: str`, `name: str`. Add a
      `from_api` classmethod. Confirm `wc -l` stays under 440 (the
      extraction in T006 made room). (FR-006, FR-007, FR-021,
      data-model.md)
- [x] T019 [US1] Extend `HospitableListing` in
      `custom_components/hospitable/api/models.py`: add a `co_hosts`
      field of type `tuple[HospitableCoHost, ...]` with
      `field(default=())`. Update `HospitableListing.from_api` to parse
      `payload.get("co_hosts", [])` into `HospitableCoHost` objects.
      (FR-006, FR-021)
- [x] T020 [US1] Add `LIST_PROPERTIES_SCHEMA` to
      `custom_components/hospitable/actions/schemas.py`: a
      `vol.Schema` with one `vol.Optional(ATTR_CONFIG_ENTRY_ID):
      cv.string` field. (FR-004)
- [x] T021 [US1] Create
      `custom_components/hospitable/actions/list_properties.py` with
      `async_handle_list_properties(hass, call) -> ServiceResponse`.
      The handler MUST:
      1. Call `resolve_config_entry` to get the config entry (FR-004).
      2. Read `entry.runtime_data["coordinators"]["properties"].data`
         for the property cache (FR-009 — NO API call).
      3. Read `entry.runtime_data["known_property_ids"]` and
         `entry.runtime_data["selected_property_ids"]` (FR-008).
      4. For each known property, build the curated shape: only
         `property_id`, `name`, `public_name`, `selected`, `listings`
         (FR-005, FR-010).
      5. For each listing, include `platform`, `platform_id`, and
         `co_hosts` (FR-006).
      6. Pass each co-host through the response privacy chokepoint in
         `actions/response.py` — the SAME `filter_response` function
         that all other services use (FR-007, FR-048). Do NOT create a
         second filtering path. Co-hosts flow through the existing
         `CO_HOST_ALLOWED` / `CO_HOST_CONTACT` logic.
      7. Return `{"properties": [...]}` (FR-005).
      The file MUST carry an SPDX header. (FR-003, FR-005, FR-006,
      FR-007, FR-008, FR-009, FR-010, FR-022, FR-048)
- [x] T022 [US1] Register `list_properties` in the
      `SERVICE_DEFINITIONS` tuple in
      `custom_components/hospitable/actions/__init__.py` as the sixth
      entry. Import `async_handle_list_properties` from
      `actions.list_properties` and `LIST_PROPERTIES_SCHEMA` from
      `actions.schemas`. Set `supports_response=SupportsResponse.ONLY`.
      (FR-003, FR-005)
- [x] T023 [US1] Add the `list_properties` service definition to
      `custom_components/hospitable/services.yaml`. The service has one
      optional field `config_entry_id` with a `config_entry` selector
      for `integration: hospitable`. It has NO `target` definition
      (spec OQ-002 — filtering to one property defeats the list
      purpose). (FR-023, FR-024)
- [x] T024 [US1] Add `list_properties` service name, description, and
      field descriptions to
      `custom_components/hospitable/strings.json` under the `services`
      key, following the pattern of the existing five services.
      Description: "Returns every known property for the account with
      curated metadata including listing co-host identifiers. Served
      from cache; no additional API request is made." (FR-023)
- [x] T025 [US1] Copy the exact same `list_properties` block into
      `custom_components/hospitable/translations/en.json`. These two
      files MUST be BYTE-IDENTICAL in their `services` sections.
      (FR-023)
- [x] T026 [US1] Run `uv run pytest tests/ -q` and confirm all tests
      pass (expected: 564 + new tests). Remove all `xfail` markers and
      `# type: ignore` comments from T008..T017 tests. Run again to
      confirm the tests genuinely pass. (FR-001)

**Exit criteria**: `list_properties` callable; all known properties
returned with curated shape; co-hosts present; zero API calls issued;
chokepoint filters co-host contact fields; multi-entry disambiguation
works; write-isolation tests green (all 20 in `test_no_writes.py`,
`test_write_isolation.py`, `test_isolation_discovery.py`).

---

## Phase 4: Deliverable B — `property_id` entity attribute (US2, Priority P2)

**Goal**: The property sensor's state attributes include `property_id`,
providing a passive discovery route visible in Developer Tools.

**Independent test**: Set up a property sensor and inspect its
`extra_state_attributes`. Confirm `property_id` is present alongside
the eight existing attributes.

**Requirements**: FR-011, FR-012, FR-013, FR-014.

### RED PHASE COMMIT — Deliverable B (tests only)

Both tests below fail with `AssertionError` because the module and
tuple exist — the behaviour is simply wrong (eight attributes instead
of nine). These are BEHAVIOURAL red-phase tests.

- [X] T027 [US2] In `tests/sensor/test_property_info.py`, add an xfail
      test (`raises=AssertionError`) asserting that
      `PROPERTY_INFO_ATTRIBUTES` contains `"property_id"`. Import the
      tuple (it exists at `sensor/property.py` line 42) and assert
      `"property_id" in PROPERTY_INFO_ATTRIBUTES`. This MUST fail with
      `AssertionError` because the tuple currently has eight entries
      and `"property_id"` is not among them. Verify:
      `uv run pytest --runxfail tests/sensor/test_property_info.py::<node>`.
      (FR-011, FR-012)
- [X] T028 [P] [US2] In `tests/sensor/test_property_info.py`, add an
      xfail test (`raises=AssertionError`) asserting that a property
      sensor's `extra_state_attributes` dict includes a `property_id`
      key with a string UUID value. Set up the sensor with a mock
      coordinator and assert the key is present. This MUST fail with
      `AssertionError` because the attribute is not returned today.
      Verify:
      `uv run pytest --runxfail tests/sensor/test_property_info.py::<node>`.
      (FR-011, FR-013)
- [X] T029 [P] [US2] In `tests/sensor/test_property_info.py`, add an
      xfail test (`raises=AssertionError`) asserting that the docstring
      of `HospitablePropertyInfoSensor.extra_state_attributes` contains
      "nine" (not "eight"). Import the class and read `__doc__` on the
      property. This MUST fail with `AssertionError` because the
      docstring currently says "eight". Verify:
      `uv run pytest --runxfail tests/sensor/test_property_info.py::<node>`.
      (FR-013)

### GREEN PHASE COMMIT — Deliverable B (implementation)

- [X] T030 [US2] Add `"property_id"` to `PROPERTY_INFO_ATTRIBUTES`
      tuple in `custom_components/hospitable/sensor/property.py`
      (currently at line 42). The tuple grows from eight to nine
      entries. (FR-011, FR-012)
- [X] T031 [US2] In `HospitablePropertyInfoSensor.extra_state_attributes`
      in `custom_components/hospitable/sensor/property.py`, add
      `"property_id": self._property_id` to the returned dict in BOTH
      code paths (the `property_model is None` fallback and the normal
      path). (FR-011)
- [X] T032 [US2] Update the docstring on `extra_state_attributes` from
      "Return exactly the eight property_info contract attributes" to
      "Return exactly the nine property_info contract attributes."
      (FR-013)
- [X] T033 [US2] Update any test docstrings in
      `tests/sensor/test_property_info.py` that reference "eight
      attributes" to "nine attributes". (FR-013)
- [X] T034 [US2] Remove all `xfail` markers and `# type: ignore`
      comments from T027..T029 tests. Run `uv run pytest tests/ -q` and
      confirm all tests pass. (FR-001)

**Exit criteria**: Nine attributes on the sensor. `property_id` value
is the correct UUID. All eight original attributes unchanged.
`test_property_info.py` green.

---

## Phase 5: Deliverable C — Entity/device targeting (US3, Priority P3)

**Goal**: `get_reservations` and `get_property_info` accept entity and
device targets via the standard HA picker, with conflict detection and
a shared `resolve_property_id` helper.

**Independent test**: Call `get_reservations` with
`target: entity_id: sensor.hospitable_test_property_status` and no
`property_id`. Confirm the property is resolved and the action succeeds.
Call with conflicting target and `property_id` and confirm
`ServiceValidationError`.

**Requirements**: FR-015 to FR-020, FR-024.

### RED PHASE COMMIT — Deliverable C (tests only)

**Import red-phase tests (ImportError)**: T035 fails with `ImportError`
because the function name does not yet exist in `actions/helpers.py`.

**Behavioural red-phase tests (AssertionError)**: T036, T037, T038,
T039, T040, T041 fail with genuine `AssertionError` because the
existing code does not support targeting.

- [X] T035 [US3] In `tests/actions/test_property_targeting.py`, add an
      xfail test (`raises=ImportError`) asserting that
      `resolve_property_id` can be imported from
      `custom_components.hospitable.actions.helpers`. Import inside the
      test body with `# type: ignore[attr-defined]` (the module exists
      but the name does not). Verify:
      `uv run pytest --runxfail tests/actions/test_property_targeting.py::<node>`.
      (FR-019)
- [X] T036 [P] [US3] In `tests/actions/test_property_targeting.py`, add
      xfail tests (`raises=AssertionError`) for the conflict rule
      (FR-017): when BOTH `property_id` and a target are supplied and
      they resolve to the SAME property, the call proceeds normally.
      When they resolve to DIFFERENT properties, a
      `ServiceValidationError` is raised naming the conflict. Set up
      mock device registry entries and call `resolve_property_id`.
      These MUST fail with `AssertionError` because the function does
      not exist. Verify:
      `uv run pytest --runxfail tests/actions/test_property_targeting.py::<node>`.
      (FR-017, FR-019)
- [X] T037 [P] [US3] In `tests/actions/test_property_targeting.py`, add
      an xfail test (`raises=AssertionError`) for FR-018: when NEITHER
      `property_id` NOR a target is supplied, a
      `ServiceValidationError` is raised explaining that at least one
      targeting method is required. Verify:
      `uv run pytest --runxfail tests/actions/test_property_targeting.py::<node>`.
      (FR-018, FR-019)
- [X] T038 [P] [US3] In `tests/actions/test_property_targeting.py`, add
      an xfail test (`raises=AssertionError`) for FR-016: when only
      `property_id` is supplied (no target), the action proceeds using
      the property_id directly. This tests the direct-ID scripting path
      (FR-016: `list_properties` returns IDs that callers feed straight
      back into property-scoped actions).
      Verify:
      `uv run pytest --runxfail tests/actions/test_property_targeting.py::<node>`.
      (FR-016, FR-019)
- [X] T039 [P] [US3] In `tests/actions/test_property_targeting.py`, add
      an xfail test (`raises=AssertionError`) for FR-020: when a target
      resolves to a device belonging to a different config entry than the
      one resolved for the call, a `ServiceValidationError` is raised.
      Verify:
      `uv run pytest --runxfail tests/actions/test_property_targeting.py::<node>`.
      (FR-020, FR-022)
- [X] T040 [P] [US3] In `tests/actions/test_property_targeting.py`, add
      an xfail test (`raises=AssertionError`) for the case where a
      target resolves to a device that is NOT a `hospitable` device
      (wrong integration domain). A `ServiceValidationError` is raised.
      Verify:
      `uv run pytest --runxfail tests/actions/test_property_targeting.py::<node>`.
      (FR-020)
- [X] T041 [P] [US3] In `tests/actions/test_property_targeting.py`, add
      an xfail test (`raises=AssertionError`) for entity target
      resolution: when a property sensor entity_id is supplied as
      target, the resolver looks up the entity's device and extracts the
      property_id via `parse_device_identifier`. Verify:
      `uv run pytest --runxfail tests/actions/test_property_targeting.py::<node>`.
      (FR-015, FR-019)
- [X] T042 [P] [US3] In `tests/actions/test_property_targeting.py`, add
      an xfail test (`raises=AssertionError`) for `get_reservations`
      with a device target and no `property_id`: the service call
      succeeds and the reservations for the targeted property are
      returned. Verify:
      `uv run pytest --runxfail tests/actions/test_property_targeting.py::<node>`.
      (FR-015, FR-024)
- [X] T043 [P] [US3] In `tests/actions/test_property_targeting.py`, add
      an xfail test (`raises=AssertionError`) for `get_property_info`
      with an entity target and no `property_id`: the service call
      succeeds and the property info for the targeted property is
      returned. Verify:
      `uv run pytest --runxfail tests/actions/test_property_targeting.py::<node>`.
      (FR-015, FR-024)

### GREEN PHASE COMMIT — Deliverable C (implementation)

- [X] T044 [US3] Add `resolve_property_id` to
      `custom_components/hospitable/actions/helpers.py`. The function
      signature follows D-04:
      ```python
      def resolve_property_id(
          hass: HomeAssistant,
          entry: ConfigEntry,
          *,
          property_id: str | None,
          target: dict[str, Any] | None,
      ) -> str:
      ```
      Implementation:
      1. If `target` is supplied, resolve device(s) → property_id via
         `parse_device_identifier` from `entity.py`. For entity targets,
         look up the entity's device in the device registry first.
      2. Validate the device's `config_entry_id` matches `entry.entry_id`
         (FR-020).
      3. Validate the device has a `hospitable` domain identifier
         (FR-020).
      4. If `property_id` is also supplied and differs →
         `ServiceValidationError` (FR-017).
      5. If both agree or only one is supplied → return the property_id.
      6. If neither yields a property_id →
         `ServiceValidationError` (FR-018).
      Confirm `wc -l helpers.py` stays under 440 after addition
      (~50 new lines → ~266 total). (FR-015, FR-016, FR-017, FR-018,
      FR-019, FR-020, FR-022)
- [X] T045 [US3] Change `property_id` from `vol.Required` to
      `vol.Optional` in `GET_RESERVATIONS_SCHEMA` and
      `GET_PROPERTY_INFO_SCHEMA` in
      `custom_components/hospitable/actions/schemas.py`. (FR-015,
      FR-016)
- [X] T046 [US3] Modify `async_handle_get_reservations` in
      `custom_components/hospitable/actions/get_reservations.py` to
      call `resolve_property_id(hass, entry, property_id=...,
      target=call.data.get("target"))` instead of reading `property_id`
      directly from `call.data`. Import `resolve_property_id` from
      `actions.helpers`. (FR-015, FR-017, FR-018, FR-019)
- [X] T047 [US3] Modify `async_handle_get_property_info` in
      `custom_components/hospitable/actions/get_property_info.py` to
      call `resolve_property_id` in the same manner as T046. Import
      `resolve_property_id` from `actions.helpers`. (FR-015, FR-017,
      FR-018, FR-019)
- [X] T048 [US3] Add a `target` definition to `get_reservations` and
      `get_property_info` in
      `custom_components/hospitable/services.yaml`:
      ```yaml
      target:
        entity:
          integration: hospitable
        device:
          integration: hospitable
      ```
      Change the existing `property_id` field from `required: true` to
      `required: false`. (FR-015, FR-024)
- [X] T049 [US3] Add target field descriptions to
      `custom_components/hospitable/strings.json` for
      `get_reservations` and `get_property_info`. Update the
      `property_id` field description to indicate it is now optional
      when a target is supplied. (FR-023, FR-024)
- [X] T050 [US3] Fix the CIRCULAR description of `get_property_info` in
      `custom_components/hospitable/strings.json`. The current
      description says "so the identifiers other actions need can be
      discovered" — but it requires a `property_id` to call. Replace
      with a description that points at `list_properties` as the
      discovery action, e.g.: "Returns a property's details together
      with its sales channels and their co-hosts. Use list_properties
      to discover property identifiers." (FR-023)
- [X] T051 [US3] Copy the exact same changes from T049 and T050 into
      `custom_components/hospitable/translations/en.json`. These two
      files MUST remain BYTE-IDENTICAL in their `services` sections.
      (FR-023)
- [X] T052 [US3] Remove all `xfail` markers and `# type: ignore`
      comments from T035..T043 tests. Run `uv run pytest tests/ -q` and
      confirm all tests pass. (FR-001)

**Exit criteria**: Both services accept targets. Conflict rule enforced.
Cross-entry rejection works. Direct `property_id` still works.
Write-isolation tests green. `strings.json` and
`translations/en.json` are byte-identical in `services` sections.

---

## Phase 6: Write-isolation and regression verification

**Purpose**: Verify that the new `list_properties` module is correctly
covered by the discovery-based write-isolation gate and that no
existing assertion was weakened.

**Principle XII status**: EXEMPT — test-only assertions of existing
behaviour. No red/green pair needed.

- [X] T053 Run the full write-isolation test suite — all three
      files: `test_no_writes.py`, `test_write_isolation.py`, and
      `test_isolation_discovery.py` under `tests/`, with `-v`.
      Confirm all 20 tests pass. In particular confirm that
      `test_isolation_discovery.py::discovered_polling_modules` does NOT
      include `actions/list_properties.py` (because
      `_is_write_path(path)` returns True for everything under
      `ACTIONS_PACKAGE`). The new module is on the WRITE side of the
      boundary, which is correct: it lives in `actions/` and that
      package is exempt from the polling-surface scan. (FR-001, FR-002)
- [X] T054 In `tests/test_isolation_discovery.py`, add an assertion
      confirming that `actions/list_properties.py` is NOT in
      `discovered_polling_modules()` — i.e., it is correctly classified
      as part of the write path (actions package). This is an ADDITIVE
      assertion, not a modification of any existing assertion. It
      prevents a future refactor from accidentally moving the module
      out of the actions package and into the polling surface without
      gate coverage. (FR-001, FR-002)
- [X] T055 Verify that `test_the_write_surface_is_exactly_two_consumers`
      in `tests/test_isolation_discovery.py` still passes. The new
      `list_properties.py` module does NOT import
      `HospitableWriteClient` or `api/write_client.py` (it reads from
      coordinator cache only), so it should NOT appear in the write
      surface. If it does, the implementation is wrong. (FR-001, FR-002,
      FR-009)

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation verification, `strings.json` sync check,
`get_property_info` description fix, traceability, and mutation
verification.

**Principle XII status**: EXEMPT — documentation-only and
verification-only tasks.

- [X] T056 Verify `strings.json` and `translations/en.json` are
      BYTE-IDENTICAL by running
      `diff <(python3 -c "...") <(python3 -c "...")`
      on the normalised JSON, or `cmp` on the raw files if they are
      already identical. If they differ, fix the divergence. Both files
      MUST carry the same service names, descriptions, and field
      descriptions for all six services. (FR-023)
- [X] T057 Verify that `tests/test_documentation.py` passes with the
      new service. In particular:
      - `test_every_registered_service_is_documented` will fail if
        `list_properties` is not documented in `README.md` and `info.md`.
      - Add a `### \`hospitable.list_properties\`` section to
        `README.md` and a mention in `info.md`.
      (FR-023)
- [X] T058 Update the traceability test in `tests/test_documentation.py`
      to ALSO validate spec 003's requirements. Currently it hardcodes
      paths to spec 002's `spec.md` and `tasks.md`. Either:
      (a) Parametrise it to also check spec 003's files, or
      (b) Add a second test function for spec 003.
      The test must confirm that every FR-001..FR-024 in spec 003's
      `spec.md` appears in spec 003's `tasks.md` traceability table.
      (FR-001..FR-024)
- [X] T059 Run `uv run pytest tests/ -q` — expect all tests pass
      (564 + new). Run `uv run reuse lint`. Run `markdownlint` over
      `specs/003-property-discovery/`.
- [X] T060 **Mutation verification.** This MUST be its own task and
      its own commit. Mutations catch defects that CI cannot; four of
      this project's defects were caught ONLY by mutation. Procedure:

      1. **Clear `__pycache__` FIRST**: `find . -type d -name __pycache__
         -exec rm -rf {} +` — a mutation that appeared to pass once
         turned out to be a stale cache artifact.
      2. **`grep`-confirm each mutation actually landed in the file**
         before running tests. A `sed` silently no-op'd once because it
         assumed a bare set literal where the source used
         `frozenset({...})`.
      3. Run each mutation, confirm the test suite catches it (at least
         one test FAILS), then revert.

      **Required mutations** (at minimum):

      - **M1: Make the co-host filter a pass-through.** In
        `actions/response.py`, change `_filter_one_co_host` to return
        the input dict unchanged. Confirm at least one test in
        `test_list_properties.py` fails (the co-host privacy test).
      - **M2: Drop `property_id` from the sensor attributes.** In
        `sensor/property.py`, remove `"property_id"` from
        `PROPERTY_INFO_ATTRIBUTES` and the returned dict. Confirm at
        least one test in `test_property_info.py` fails.
      - **M3: Make the FR-017 conflict check always pass.** In
        `actions/helpers.py`, in `resolve_property_id`, comment out the
        `if target_property_id != property_id:` branch. Confirm at
        least one test in `test_property_targeting.py` fails.
      - **M4: Return only selected rather than all known properties.**
        In `actions/list_properties.py`, iterate over
        `selected_property_ids` instead of `known_property_ids`.
        Confirm at least one test in `test_list_properties.py` fails
        (the unselected-property-appears test).

      For EACH mutation: `grep` the mutation in the file before running
      tests, run `uv run pytest tests/ -q`, confirm failure, revert
      with `git checkout -- <file>`. (FR-001, FR-007, FR-008, FR-011,
      FR-017)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all
  deliverables. The `api/models.py` extraction MUST complete and pass
  pre-commit before any model change.
- **Deliverable A (Phase 3)**: Depends on Phase 2 (needs room in
  `models.py` for `HospitableCoHost`)
- **Deliverable B (Phase 4)**: Depends on Phase 2 only. Independent of
  Phase 3.
- **Deliverable C (Phase 5)**: Depends on Phase 2 only. Independent of
  Phases 3 and 4.
- **Write-isolation (Phase 6)**: Depends on Phases 3, 4, and 5
- **Polish (Phase 7)**: Depends on all prior phases

### Within Each Deliverable

- Red-phase tests MUST land as a tests-only commit BEFORE the
  green-phase implementation commit.
- Models before services, services before handlers, handlers before
  registration.
- Schema changes and handler changes for the same service are in the
  same green-phase commit.

### Parallel Opportunities

Green-phase tasks marked [P] within a single deliverable can run in
parallel (different files, no dependencies). Red-phase tests marked [P]
can be written in parallel.

**Deliverables A, B, and C are independently implementable after
Phase 2**, though they share a single PR. The recommended order is
A → B → C because:

- A establishes the co-host model that C's targeting tests may
  reference.
- B is the smallest change and fastest to validate.
- C depends on the schema being stable (A and B don't change schemas
  C uses).

---

## Parallel example

    # Deliverable A red phase, multiple tests:
    uv run pytest --runxfail tests/api/test_models.py::test_co_host_import
    uv run pytest --runxfail tests/api/test_models.py::test_listing_has_co_hosts
    uv run pytest --runxfail tests/actions/test_list_properties.py::test_handler_import
    uv run pytest --runxfail tests/actions/test_list_properties.py::test_response_shape

    # each --runxfail scoped to node ids, never bare.

---

## Implementation strategy

**MVP = Phase 1 + Phase 2 + Deliverable A (Phase 3).** That delivers
a working `list_properties` service with co-host data, full
localisation, and all write-isolation gates verified. It is the primary
ask and solves the circular-description problem.

Recommended order after the MVP: Deliverable B (smallest change, fast
to validate), then Deliverable C (most complex, benefits from A and B
being stable).

One pull request containing all phases. Each deliverable has two commits
minimum — red then green. Phases 1, 2, 6, and 7 are exempt from
red/green splitting.

---

## Notes and known gaps

These are discrepancies or implementation considerations observed while
writing this file. They are **reported, not silently reconciled**.

- **`api/models.py` is at exactly 439 lines.** The `aislop` threshold
  is ~440. Adding `HospitableCoHost` (~20 lines) puts it at ~459. T006
  extracts `HospitableMessage` and `_optional_str` first. The `__all__`
  re-export pattern at the bottom of `models.py` already demonstrates
  this technique (it re-exports `HospitableGuest`, `HospitableTask`,
  etc. from `api/guest.py` and `api/task_model.py`).
- **The `get_property_info` description in `strings.json` is
  CIRCULAR.** It says "so the identifiers other actions need can be
  discovered" while requiring a `property_id` to call. T050 fixes this
  to point at `list_properties`.
- **`test_isolation_discovery.py` classifies everything under
  `ACTIONS_PACKAGE` as write-path.** `list_properties.py` lives there
  and is therefore correctly excluded from the polling-surface scan.
  It does NOT import `HospitableWriteClient` (it reads cache only), so
  it should not appear in the write-surface assertion either. T055
  verifies this.
- **`strings.json` and `translations/en.json` are currently
  byte-identical.** T056 verifies this is preserved after all changes.
- **`test_documentation.py::test_every_requirement_is_traceable`
  currently checks only spec 002's files.** T058 extends it to also
  validate spec 003.
- **`resolve_property_id` handles entity targets by looking up the
  entity's device.** The entity registry provides the device_id for an
  entity; the device registry then provides the identifiers tuple.
  `parse_device_identifier` (in `entity.py`) extracts the property_id
  from the `(DOMAIN, f"{namespace}_{property_id}")` identifier format.
- **No new API requests.** `list_properties` reads coordinator cache
  only (FR-009). The two modified services (`get_reservations`,
  `get_property_info`) already issue their own API requests; target
  resolution adds only a device-registry lookup, not an API call.
- **Co-host objects carry exactly `{channel_name, name, user_id}`
  today (CONFIRMED-BY-TEST 2026-08-13, 13 properties, 8 co-hosts).**
  No `email`, `phone_numbers`, or `profile_picture` key exists. The
  `HospitableCoHost` dataclass models only these three fields. The
  chokepoint handles future key additions via the allowlist.
- **This file does not claim complete coverage of every requirement's
  every nuance.** It claims that each of FR-001 through FR-024 is named
  by at least one task. Depth of coverage is a judgement the reviewer
  should make independently.

---

## Requirement to task traceability

Generated by extracting the `FR-0NN` tokens appearing in the task lines
of this file. A requirement listed here has at least one task naming
it; it does not follow that the task fully discharges it.

| Requirement | Tasks |
| --- | --- |
| FR-001 | T026, T034, T052, T053, T054, T055, T060 |
| FR-002 | T053, T054, T055 |
| FR-003 | T007, T012, T014, T021, T022 |
| FR-004 | T013, T017, T020, T021 |
| FR-005 | T003, T015, T021, T022 |
| FR-006 | T003, T008, T009, T010, T011, T016, T018, T019, T021 |
| FR-007 | T003, T008, T016, T018, T021, T060 |
| FR-008 | T003, T015, T021, T060 |
| FR-009 | T015, T021, T055 |
| FR-010 | T003, T015, T016, T021 |
| FR-011 | T027, T028, T030, T031, T060 |
| FR-012 | T027, T030 |
| FR-013 | T028, T029, T032, T033 |
| FR-014 | T031 |
| FR-015 | T041, T042, T043, T044, T045, T046, T047, T048 |
| FR-016 | T038, T044, T045 |
| FR-017 | T036, T044, T046, T047, T060 |
| FR-018 | T037, T044, T046, T047 |
| FR-019 | T035, T036, T037, T038, T039, T041, T044, T046, T047 |
| FR-020 | T039, T040, T044 |
| FR-021 | T005, T006, T008, T009, T010, T011, T018, T019 |
| FR-022 | T017, T021, T039, T044 |
| FR-023 | T023, T024, T025, T049, T050, T051, T056, T057 |
| FR-024 | T023, T042, T043, T048, T049 |

### Success criteria

| Item | Tasks |
| --- | --- |
| SC-001 | T015, T021, T026 |
| SC-002 | T016, T021 |
| SC-003 | T027, T028, T030, T031 |
| SC-004 | T042, T043, T048 |
| SC-005 | T053, T054, T055 |
| SC-006 | T038, T044 |
