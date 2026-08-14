<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Tasks: Polish and Observability

**Input**: Design documents from `/specs/004-polish-observability/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`,
`data-model.md`, `quickstart.md`, `contracts/`. Specs 001–003 are
complete and merged; spec 003's `tasks.md` (60 tasks, 7 phases) is
the structural precedent for this file.

**Tests**: Test tasks are MANDATORY. Constitution Principle I
(NON-NEGOTIABLE) makes code-level TDD mandatory and Principle IX
forbids deferring unit-level TDD. Per Principle XII (Red-Phase
Commit Protocol) tests land as a red-phase commit containing tests
only, with every test marked
`@pytest.mark.xfail(raises=..., reason="...", strict=True)` so
the suite reports XFAIL and stays green; the implementation lands
as a separate green-phase commit that removes those markers and
the `# type: ignore[...]` comments.

**Organization**: Tasks are grouped by deliverable. Each
deliverable is INDEPENDENT and ships in its own PR. The
recommended ordering follows the plan: D3 → D1 → D2 → D4 → D5
(smallest risk first). Each deliverable-phase carries its own
setup, red, green, and verification tasks.

**Checkbox flips**: Task-list checkbox flips (`- [ ]` → `- [X]`)
ride each implementation PR as a SEPARATE atomic commit, per this
project's atomic-commit rule. They are documentation changes, not
code changes, and must not be mixed into red-phase or green-phase
commits.

**Release status**: This integration has NEVER been released. No
git tags, no published releases, no known third-party
installations. No backwards-compatibility, migration, or
upgrade-path constraint applies. Do NOT justify any task with
backwards compatibility, migration, or upgrade paths.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story / deliverable the task belongs to
  (D1, D2, D3, D4, D5)
- Exact file paths are given in every task
- Trailing parentheses list the functional requirements the task
  serves

## Path Conventions

Integration code lives under `custom_components/hospitable/`,
tests under `tests/`, packaging files at the repository root.
Paths follow `plan.md` §Project Structure.

---

## Red/green phase protocol (read before starting any phase)

Every deliverable phase where Principle XII applies is split into
a **RED PHASE** group and a **GREEN PHASE** group. They are
separate commits. The rules are mechanical and non-negotiable:

1. **Red-phase commit contains tests only.** No production module
   may be created or edited in it.
2. **Every red-phase test carries `raises=` naming a specific
   exception type.** `strict=True` alone does not check *why* a
   test failed; when `xfailed.raises is None` any exception
   raised during setup or call counts as an expected failure.
   `raises=` is MANDATORY on every marker in this file.
3. **Imports of not-yet-existing modules go inside the test
   body.** A module-level import breaks *collection*.
   `pytest.importorskip` is PROHIBITED.
4. **Deferred imports carry `# type: ignore[import-not-found]`.**
   Use `# type: ignore[attr-defined]` where the module exists but
   the name does not. `warn_unused_ignores = true` forces these
   to be removed at green phase.
5. **`tests/conftest.py` imports no not-yet-existing module.**
6. **A red phase where every test dies on `ImportError` proves
   nothing behavioural.** Every deliverable needs at least one
   BEHAVIOURAL red-phase test failing with a genuine
   `AssertionError` (or a domain exception). Import tests and
   behavioural tests BOTH belong in the red phase.
7. **Before every red-phase commit** run
   `uv run pytest --runxfail <node ids>` scoped to the new tests
   only and confirm each fails with the declared exception.
8. **The green-phase commit removes markers and ignores in the
   same commit that adds the implementation.**
9. **Every commit leaves the suite green.**

**Exemptions (Principle XII §Exemptions)**: pure refactors,
docs-only, CI-only, packaging-only, config-only, and test-only
changes. Phase 1 and Phase 7 are exempt. D3 (Phase 3) is
XII-EXEMPT per the plan — configuration-only change.

---

## Phase 1: Setup (shared scaffolding and baseline)

**Purpose**: Verify baseline, scaffold test files, create fixtures
for all deliverables.

**Principle XII status**: EXEMPT — test scaffolding and fixture
creation asserting no new production behaviour.

- [X] T001 Verify baseline: run `uv run pytest tests/ -q` and
      confirm 590 tests pass. Run
      `uv run ruff check custom_components/ tests/` and
      `uv run mypy custom_components/ tests/` clean. Record the
      commit SHA (`0796f8c`).
- [X] T002 [P] Measure current line counts for all files the plan
      identifies as modified. Record in the commit message:
      `api/client.py` 410, `sensor/tasks.py` 298,
      `diagnostics.py` 282, `coordinator_tasks.py` 148,
      `coordinator.py` 406, `actions/response.py` 142,
      `actions/get_reservations.py` 132,
      `actions/get_property_info.py` 88, `actions/schemas.py` 98,
      `api/exceptions.py` 95, `services.yaml` 124,
      `strings.json` 246, `translations/en.json` 246.
      Note that `api/client.py` at 410 has only ~30 lines of
      headroom before the ~440 `aislop` ceiling — D4 adds ~10
      lines, projected ~420 (safe, but measure after
      implementation and include a contingency note: if D4 pushes
      past 440, extract the `_raise_for_status` helper into a
      separate module before committing).
- [X] T003 [P] Create
      `tests/sensor/test_task_count_cancelled.py` as an empty
      test module with SPDX header and module docstring stating
      it covers D1 (cancelled progress bucket, FR-001 to FR-008).
      The file MUST NOT import any
      `custom_components.hospitable` module at module level.
- [X] T004 [P] Create
      `tests/actions/test_listing_privacy.py` as an empty test
      module with SPDX header and module docstring stating it
      covers D2 (listing field privacy gating, FR-009 to FR-014).
- [X] T005 [P] Create `tests/api/test_trace_header.py` as an
      empty test module with SPDX header and module docstring
      stating it covers D4 (trace header capture, FR-017 to
      FR-022).
- [X] T006 [P] Create
      `tests/actions/test_get_reservations_window.py` as an empty
      test module with SPDX header and module docstring stating
      it covers D5 (relative-day window override, FR-023 to
      FR-032).
- [X] T007 [P] Add SPDX headers or `REUSE.toml` coverage for
      every file created in T003..T006 and run
      `uv run reuse lint` to confirm compliance.

**Exit criteria**: `uv run pytest` collects cleanly, 590 tests
pass, all new files REUSE-compliant.

---

## Phase 2: Deliverable 3 — Bare `uv run mypy` works (US3, P2)

**Goal**: `uv run mypy` with no arguments checks
`custom_components/` and `tests/`, identical to the explicit
invocation.

**Independent test**: Run both invocations and confirm identical
output.

**Requirements**: FR-015, FR-016.

**Principle XII status**: EXEMPT — configuration-only change to
`pyproject.toml`. The plan explicitly rules D3 XII-EXEMPT. Do
NOT invent a hollow red phase.

- [X] T008 [D3] Add `files = ["custom_components", "tests"]` to
      the `[tool.mypy]` section in `pyproject.toml` (after line
      62, the existing `[tool.mypy]` header). (FR-015)
- [X] T009 [D3] Verify equivalence: run `uv run mypy` and
      `uv run mypy custom_components/ tests/` and confirm both
      produce identical output. Record the comparison in the
      commit message. (FR-016)

**Exit criteria**: Bare `uv run mypy` works. Both invocations
produce the same output. 590 tests still pass.

---

## Phase 3: Deliverable 1 — Cancelled task progress bucket (US1, P1)

**Goal**: A fourth `CANCELLED_STATUSES` bucket in
`sensor/tasks.py` so that the four breakdown attributes sum to
`task_count` and a vocabulary drift guard logs unknown statuses.

**Independent test**: Supply a task fixture containing all six
known `progress_status` values (including `cancelled` and `null`).
Confirm `pending_count + in_progress_count + completed_count +
cancelled_count` equals `task_count`.

**Requirements**: FR-001 to FR-008.

### RED PHASE COMMIT — Deliverable 1 (tests only)

All tests below are in
`tests/sensor/test_task_count_cancelled.py`.

**Import red-phase test**: T010 fails with `ImportError` because
`CANCELLED_STATUSES` does not yet exist in `sensor/tasks.py`.

**Behavioural red-phase tests**: T011–T015 fail with
`KeyError` or `AssertionError` against existing code.

- [X] T010 [P] [D1] Add an xfail test (`raises=ImportError`)
      asserting that `CANCELLED_STATUSES` can be imported from
      `custom_components.hospitable.sensor.tasks`. Import inside
      the test body with `# type: ignore[attr-defined]` (the
      module exists but the name does not). Also assert its value
      equals `frozenset({"cancelled"})`. Verify:
      `uv run pytest --runxfail <node>`. (FR-001)
- [X] T011 [P] [D1] Add an xfail test (`raises=ImportError`)
      asserting that the union of all four frozensets
      (`PENDING_STATUSES | IN_PROGRESS_STATUSES |
      COMPLETED_STATUSES | CANCELLED_STATUSES`) equals exactly
      `{"not_started", "on_the_way", "arrived", "in_progress",
      "completed", "cancelled"}`. Import `CANCELLED_STATUSES`
      inside the test body with
      `# type: ignore[attr-defined]`. Fails with `ImportError`
      because `CANCELLED_STATUSES` does not exist. Verify:
      `uv run pytest --runxfail <node>`. (FR-007)
- [X] T012 [D1] Add an xfail test (`raises=KeyError`) that sets
      up a task-count sensor with fixtures containing a task with
      `progress_status="cancelled"` (SYNTHETIC — no cancelled
      task has been observed in live data, per spec assumptions).
      Assert `"cancelled_count"` is present in
      `extra_state_attributes`. Fails with `KeyError` because
      the attribute is not returned by the current three-bucket
      implementation. Verify:
      `uv run pytest --runxfail <node>`. (FR-003)

      **Why `raises=KeyError`**: The test accesses
      `attrs["cancelled_count"]` on the dict returned by
      `extra_state_attributes`. The current implementation
      returns only three keys; subscripting a missing key raises
      `KeyError`.
- [X] T013 [D1] Add an xfail test (`raises=KeyError`) asserting
      that a cancelled task increments `cancelled_count` and
      does NOT increment `pending_count`, `in_progress_count`,
      or `completed_count`. Uses the same synthetic fixture.
      Fails with `KeyError` for the same reason as T012. Verify:
      `uv run pytest --runxfail <node>`. (FR-002, FR-003)

      **Bucket keying**: The test MUST assert on
      `progress_status`, NOT `assignment_status`. Both
      vocabularies contain `cancelled`, but they are different
      dimensions. The fixture task MUST have
      `progress_status="cancelled"` and may have any
      `assignment_status` (e.g. `null`).
- [X] T014 [D1] Add an xfail test (`raises=KeyError`) asserting
      that the sum `pending_count + in_progress_count +
      completed_count + cancelled_count` equals `task_count`
      (the sensor's `native_value`). Provide a fixture with
      tasks spanning all six statuses plus a null. Fails with
      `KeyError` (missing `cancelled_count`). Verify:
      `uv run pytest --runxfail <node>`. (FR-005)
- [X] T015 [D1] Add an xfail test (`raises=AssertionError`) for
      the vocabulary drift guard: supply a task with
      `progress_status="teleported"` (an unknown value, not
      `null`). Assert that a warning is logged naming
      `"teleported"`. Fails with `AssertionError` because no
      drift guard exists and no warning is logged. Verify:
      `uv run pytest --runxfail <node>`. (FR-006)

      **Why `raises=AssertionError`**: The test imports existing
      sensor code (no `ImportError`), sets up the sensor, and
      asserts on `caplog`. The assertion fails because the drift
      guard does not exist.
- [X] T016 [P] [D1] Add an xfail test (`raises=KeyError`)
      asserting that `progress_status=None` still increments
      `pending_count` (existing behaviour, unchanged) AND that
      all four buckets sum to `task_count`. The test accesses
      `attrs["cancelled_count"]` which does not exist yet, so it
      raises `KeyError` before reaching the assertion logic.
      Verify: `uv run pytest --runxfail <node>`. (FR-004, FR-005)

      **Why `raises=KeyError`**: The test's assertion logic
      requires all four bucket keys; accessing `cancelled_count`
      fails first with `KeyError`.

### GREEN PHASE COMMIT — Deliverable 1 (implementation)

- [X] T017 [D1] Add `CANCELLED_STATUSES = frozenset({"cancelled"})`
      to `custom_components/hospitable/sensor/tasks.py` below
      `COMPLETED_STATUSES` (after line 43). (FR-001)
- [X] T018 [D1] Rewrite the comment block above the frozenset
      definitions (lines 35–42 of `sensor/tasks.py`). Remove the
      statement "A CANCELLED task falls in no bucket, so the
      buckets deliberately need not sum to the total." Replace
      with text describing the four-bucket reconciliation
      guarantee: the four buckets sum to `task_count` while all
      `progress_status` values are members of the known
      six-value vocabulary. Document that `cancelled` is keyed on
      `progress_status`, NOT `assignment_status` — both
      vocabularies contain `cancelled` but they are different
      dimensions. (FR-002, FR-008)
- [X] T019 [D1] Add `"cancelled_count"` to the
      `_unrecorded_attributes` frozenset on
      `HospitableTaskCountSensor` in `sensor/tasks.py` (line
      228). (FR-003)
- [X] T020 [D1] In `HospitableTaskCountSensor.extra_state_attributes`
      in `sensor/tasks.py`:
      1. Add a `cancelled` counter:
         `sum(1 for task in tasks if task.progress_status in
         CANCELLED_STATUSES)`.
      2. Add `"cancelled_count": cancelled` to the returned dict.
      3. Add a vocabulary drift guard: after computing all four
         counts, iterate tasks and for any task where
         `progress_status is not None` and `progress_status` is
         not a member of `PENDING_STATUSES |
         IN_PROGRESS_STATUSES | COMPLETED_STATUSES |
         CANCELLED_STATUSES`, log a warning:
         `_LOGGER.warning("Unknown progress_status %r on task
         %s", task.progress_status, task.task_id)`. Import
         `logging` and create `_LOGGER` at module level if not
         already present.
      (FR-003, FR-005, FR-006)
- [X] T021 [D1] Rewrite the `extra_state_attributes` docstring on
      `HospitableTaskCountSensor` from "A cancelled task appears
      in no bucket, so these deliberately need not sum to the
      state" to describe the four-bucket sum guarantee. (FR-008)
- [X] T022 [D1] Remove all `xfail` markers and
      `# type: ignore[...]` comments from T010–T016 tests. Run
      `uv run pytest tests/ -q` and confirm all tests pass.
- [X] T023 [D1] Run the write-isolation test suite:
      `uv run pytest tests/test_no_writes.py
      tests/test_write_isolation.py
      tests/test_isolation_discovery.py -v`. Confirm all 20
      tests pass. (SC-005)

### MUTATION VERIFICATION — Deliverable 1

- [X] T024 [D1] **Mutation verification for D1.** Procedure:

      1. **Clear `__pycache__`**: `find . -type d -name
         __pycache__ -exec rm -rf {} +` — a mutation can appear
         to pass from a stale cache artifact.
      2. **Copy the source**: `cp
         custom_components/hospitable/sensor/tasks.py
         /dev/shm/tasks.py.bak`
      3. **M1 — Remove `CANCELLED_STATUSES` from the
         frozensets**: In `sensor/tasks.py`, change
         `CANCELLED_STATUSES = frozenset({"cancelled"})` to
         `CANCELLED_STATUSES = frozenset()`. `grep` the mutated
         line to confirm it landed. Run
         `uv run pytest tests/sensor/test_task_count_cancelled.py -q`.
         At least one test MUST fail. Record which.
      4. **Restore**: `cp /dev/shm/tasks.py.bak
         custom_components/hospitable/sensor/tasks.py`. Run
         `git status --short` to confirm clean.
      5. **M2 — Disable the drift guard**: Comment out the
         `_LOGGER.warning(...)` line in
         `extra_state_attributes`. `grep` the mutation. Run
         `uv run pytest tests/sensor/test_task_count_cancelled.py -q`.
         The drift-guard test (T015) MUST fail.
      6. **Restore**: same as step 4. `git status --short`.
      (FR-001, FR-006, FR-007)

**Exit criteria**: Four buckets sum to `task_count`. Drift guard
logs warnings for unknown statuses. Exhaustiveness test passes.
Null progress still counted as pending. Write-isolation green.
Mutations caught.

---

## Phase 4: Deliverable 2 — Listing field privacy gating (US2, P1)

**Goal**: `platform_email` and `platform_picture` on listing
objects are gated behind `guest_contact_details` via the existing
chokepoint in `actions/response.py`.

**Independent test**: Invoke `get_property_info` with
`guest_contact_details` disabled, confirm `platform_email` and
`platform_picture` absent from every listing. Re-invoke with
option enabled, confirm both present.

**Requirements**: FR-009 to FR-014.

### RED PHASE COMMIT — Deliverable 2 (tests only)

All tests below are in `tests/actions/test_listing_privacy.py`.

**Import red-phase test**: T025 fails with `ImportError` because
`LISTING_KEYS` does not yet exist.

**Behavioural red-phase tests**: T026–T030 fail with
`AssertionError` because the current chokepoint does not filter
listings.

- [ ] T025 [P] [D2] Add an xfail test (`raises=ImportError`)
      asserting that `LISTING_KEYS` can be imported from
      `custom_components.hospitable.actions.response`. Import
      inside the test body with
      `# type: ignore[attr-defined]`. Verify:
      `uv run pytest --runxfail <node>`. (FR-011)
- [ ] T026 [D2] Add an xfail test (`raises=AssertionError`)
      that constructs a payload containing `"listings":
      [{"platform": "airbnb", "platform_id": "123",
      "platform_email": "x@y.com", "platform_picture":
      "http://pic", "co_hosts": []}]`, passes it through
      `serialize_response(payload, guest_contact=False)`, and
      asserts that `"platform_email"` is ABSENT from the first
      listing in the result AND `"platform_picture"` is ABSENT.
      Fails with `AssertionError` because the current chokepoint
      recurses listings without applying any listing allowlist —
      all keys pass through. Verify:
      `uv run pytest --runxfail <node>`. (FR-009)

      **Why `raises=AssertionError`**: `serialize_response` is
      importable and callable; the payload recurses through the
      dict/list branches. The assertion on the result fails
      because both keys survive.
- [ ] T027 [D2] Add an xfail test (`raises=AssertionError`)
      that passes the same payload through
      `serialize_response(payload, guest_contact=True)` and
      asserts `"platform_email"` IS present and
      `"platform_picture"` IS present when the opt-in is
      enabled. This test currently PASSES against the existing
      code (both keys survive regardless), so it needs to be
      structured to fail in the red phase. **Solution**: also
      assert that `"platform"` and `"platform_id"` are the ONLY
      non-contact keys on the listing (fail-closed check). The
      current code passes through ALL keys, so an unknown key
      like `"secret_field"` would also survive — add
      `"secret_field": "oops"` to the fixture and assert it is
      ABSENT. Fails with `AssertionError`. Verify:
      `uv run pytest --runxfail <node>`. (FR-009, FR-011)
- [ ] T028 [D2] Add an xfail test (`raises=AssertionError`) for
      the **list-of-dicts path** (THE critical trap — FR-012,
      Hazard C from the brief). Supply `"listings":
      [{"platform": "airbnb", "platform_email": "a@b"},
      {"platform": "vrbo", "platform_email": "c@d"}]` — a LIST
      of listing dicts. Pass through
      `serialize_response(payload, guest_contact=False)`. Assert
      BOTH entries have `platform_email` ABSENT. Fails with
      `AssertionError` because `_filter_identity`'s `if not
      isinstance(value, dict): return serialize_response(...)`
      branch recursively serializes the list WITHOUT applying
      the listing allowlist, so `platform_email` survives on
      every entry.

      **This is the mutation target.** The test MUST be
      structured so that removing the listing filter makes it
      fail. Verify: `uv run pytest --runxfail <node>`.
      (FR-012)

      **Why `raises=AssertionError`**: Both `serialize_response`
      and the payload are valid; the assertion on the filtered
      output fails.
- [ ] T029 [D2] Add an xfail test (`raises=AssertionError`) for
      the **`co_hosts[].user_id` regression** (Hazard D from the
      brief — spec 003 FR-007 dependency). Supply a payload with
      `"listings": [{"platform": "airbnb", "platform_id": "X",
      "co_hosts": [{"user_id": "U1", "channel_name": "C",
      "name": "N"}]}]`. Pass through `serialize_response(payload,
      guest_contact=False)`. Assert `co_hosts[0]["user_id"]`
      equals `"U1"`. Also assert `platform_email` is ABSENT
      (gating test). Fails with `AssertionError` because the
      current code does not route `listings` through the listing
      allowlist — the listing dict passes through as-is, so
      while `user_id` may survive, the assertion on
      `platform_email` being absent fails. Verify:
      `uv run pytest --runxfail <node>`. (FR-013)

      **Why `raises=AssertionError`**: The test combines a
      regression assertion (user_id survives) with a gating
      assertion (platform_email absent). The gating assertion
      fails.
- [ ] T030 [P] [D2] Add an xfail test (`raises=AssertionError`)
      that constructs a payload with an unknown listing key:
      `"listings": [{"platform": "airbnb", "platform_id": "X",
      "co_hosts": [], "totally_new_field": "surprise"}]`. Pass
      through `serialize_response(payload,
      guest_contact=False)`. Assert `"totally_new_field"` is
      ABSENT (fail-closed). Fails with `AssertionError`. Verify:
      `uv run pytest --runxfail <node>`. (FR-011)

### GREEN PHASE COMMIT — Deliverable 2 (implementation)

- [ ] T031 [D2] In `custom_components/hospitable/actions/response.py`,
      add the following constants below the existing
      `CO_HOST_CONTACT` line:

      ```python
      # Listing objects use a SEPARATE allowlist (FR-011).
      # ``listings`` is the dict key under which a LIST of
      # listing dicts appears.
      LISTING_KEYS = frozenset({"listings"})
      LISTING_ALLOWED = ("platform", "platform_id", "co_hosts")
      LISTING_CONTACT = ("platform_email", "platform_picture")
      ```

      (FR-011)
- [ ] T032 [D2] In `serialize_response`'s dict comprehension in
      `response.py`, add a third conditional branch BEFORE the
      `else serialize_response(...)` fallback:

      ```python
      else _filter_listings(value, guest_contact=guest_contact)
      if key in LISTING_KEYS
      ```

      (FR-010)
- [ ] T033 [D2] Add `_filter_listings` and
      `_filter_one_listing` functions to `response.py`.
      `_filter_listings` MUST handle the list-of-dicts shape
      (mirroring `_filter_co_hosts`): check `isinstance(value,
      list)`, iterate, apply the listing allowlist per entry via
      `_filter_one_listing`. `_filter_one_listing` builds a dict
      from `LISTING_ALLOWED` keys (always) plus
      `LISTING_CONTACT` keys (when `guest_contact` is True). The
      `co_hosts` value within each filtered listing MUST be
      further processed through `_filter_co_hosts` (or via
      recursive `serialize_response` on the filtered dict so
      that `co_hosts` hits the `CO_HOST_KEYS` branch). A
      non-list value is recursed through `serialize_response`.
      (FR-010, FR-012, FR-013)
- [ ] T034 [D2] Update the `get_property_info` handler's module
      docstring in
      `custom_components/hospitable/actions/get_property_info.py`
      (lines 10–14). Remove the statement that
      `platform_email` and `platform_picture` are "not
      filtered." Replace with text reflecting the new gating:
      both fields are now gated behind `guest_contact_details`
      through the response chokepoint. (FR-014)
- [ ] T035 [D2] Remove all `xfail` markers and
      `# type: ignore[...]` comments from T025–T030 tests. Run
      `uv run pytest tests/ -q` and confirm all tests pass.
- [ ] T036 [D2] Run the write-isolation test suite. Confirm all
      20 tests pass. (SC-005)

### MUTATION VERIFICATION — Deliverable 2

- [ ] T037 [D2] **Mutation verification for D2.** Procedure:

      1. **Clear `__pycache__`**: `find . -type d -name
         __pycache__ -exec rm -rf {} +`
      2. **Copy the source**: `cp
         custom_components/hospitable/actions/response.py
         /dev/shm/response.py.bak`
      3. **M1 — Disable the listing filter on a LIST**: In
         `response.py`, in `_filter_listings`, change the
         `isinstance(value, list)` branch to return `value`
         unchanged (pass-through). `grep` the mutated line to
         confirm it landed. Run
         `uv run pytest tests/actions/test_listing_privacy.py -q`.
         T028 (the list-of-dicts test) MUST fail. Record which
         tests fail.
      4. **Restore**: `cp /dev/shm/response.py.bak
         custom_components/hospitable/actions/response.py`. Run
         `git status --short` to confirm clean.
      5. **M2 — Remove listing contact gating**: In
         `_filter_one_listing`, always include `LISTING_CONTACT`
         keys regardless of `guest_contact`. `grep` the
         mutation. Run
         `uv run pytest tests/actions/test_listing_privacy.py -q`.
         T026 (opt-in disabled) MUST fail.
      6. **Restore**: same as step 4. `git status --short`.
      (FR-009, FR-012)

**Exit criteria**: `platform_email` and `platform_picture` absent
when opt-in disabled, present when enabled. Unknown listing keys
dropped. `co_hosts[].user_id` survives. List-of-dicts path
exercises per-entry filtering. Docstring updated. Mutations
caught. Write-isolation green.

---

## Phase 5: Deliverable 4 — Trace header capture (US4, P2)

**Goal**: `x-hospitable-trace` captured on `HospitableError`,
per-coordinator `last_trace_id`, surfaced in diagnostics.

**Independent test**: Mock an API response with an
`x-hospitable-trace` header and confirm it appears in the
diagnostics payload. Mock an error response with the header and
confirm the logged error includes the trace ID.

**Requirements**: FR-017 to FR-022.

### RED PHASE COMMIT — Deliverable 4 (tests only)

Tests below are in `tests/api/test_trace_header.py` and
`tests/test_diagnostics.py` (existing file, new tests).

- [ ] T038 [P] [D4] In `tests/api/test_trace_header.py`, add an
      xfail test (`raises=TypeError`) asserting that
      `HospitableError` accepts a `trace_id` keyword argument.
      Construct `HospitableError("test", trace_id="abc123")`
      and assert `exc.trace_id == "abc123"`. Fails with
      `TypeError` because the current `__init__` does not
      accept `trace_id`. Verify:
      `uv run pytest --runxfail <node>`. (FR-017)

      **Why `raises=TypeError`**: Python raises `TypeError:
      __init__() got an unexpected keyword argument 'trace_id'`
      when the constructor does not declare the parameter.
- [ ] T039 [P] [D4] In `tests/api/test_trace_header.py`, add an
      xfail test (`raises=AssertionError`) that mocks an error
      response carrying `x-hospitable-trace: trace-xyz` via
      `respx`. Trigger a client call that hits
      `_raise_for_status`. Catch the `HospitableError` and
      assert `exc.trace_id == "trace-xyz"`. Fails with
      `AssertionError` because `_raise_for_status` does not
      pass `trace_id` today. Verify:
      `uv run pytest --runxfail <node>`. (FR-018)

      **Why `raises=AssertionError`**: The `HospitableError` IS
      raised (the status triggers it), but `trace_id` is not
      set — it defaults to `None`, and the assertion
      `None == "trace-xyz"` fails.

      **Wait — T038 pins `TypeError` for the same constructor.**
      If T038 ships in the same red phase, the constructor does
      NOT accept `trace_id` yet, so T039's
      `HospitableError("test", trace_id=...)` would also raise
      `TypeError`, not `AssertionError`. **Resolution**: T039
      catches the exception raised by `_raise_for_status` and
      asserts on its `trace_id` attribute. The existing
      constructor does not accept `trace_id`, so the attribute
      does not exist — `getattr(exc, "trace_id", None)` returns
      `None`, and the assertion fails with `AssertionError`.
      Pin `raises=AssertionError`. The test MUST use
      `getattr(exc, "trace_id", None)` rather than
      `exc.trace_id` to avoid `AttributeError`.
- [ ] T040 [P] [D4] In `tests/api/test_trace_header.py`, add an
      xfail test (`raises=AssertionError`) that mocks a
      successful API response carrying
      `x-hospitable-trace: trace-abc`. Trigger a coordinator
      refresh. Assert the coordinator has
      `last_trace_id == "trace-abc"`. Fails with
      `AssertionError` because coordinators do not store trace
      IDs today. Verify:
      `uv run pytest --runxfail <node>`. (FR-019)
- [ ] T041 [P] [D4] In `tests/api/test_trace_header.py`, add an
      xfail test (`raises=AssertionError`) that mocks a
      response WITHOUT the `x-hospitable-trace` header.
      Trigger a coordinator refresh. Assert `last_trace_id is
      None` (not empty string). Fails with `AssertionError`
      because the attribute does not exist. Use
      `getattr(coordinator, "last_trace_id", "MISSING")` and
      assert the result is `None`. `"MISSING" != None` →
      `AssertionError`. Verify:
      `uv run pytest --runxfail <node>`. (FR-020)
- [ ] T042 [P] [D4] In `tests/test_diagnostics.py` (or
      `tests/api/test_trace_header.py`), add an xfail test
      (`raises=AssertionError`) asserting the diagnostics
      payload includes a `last_trace_id` key in each
      coordinator section after a successful poll with the
      header present. Mock the response with the header, build
      diagnostics, assert presence. Fails with `AssertionError`
      because `_coordinator_section` does not include
      `last_trace_id`. Verify:
      `uv run pytest --runxfail <node>`. (FR-019, FR-021)
- [ ] T043 [P] [D4] In `tests/api/test_trace_header.py`, add an
      xfail test (`raises=AssertionError`) that the trace ID
      passes through the diagnostics redactor unredacted.
      Build a diagnostics payload with a trace ID, run it
      through the redactor, assert the trace value survives
      unchanged. Fails with `AssertionError`. Verify:
      `uv run pytest --runxfail <node>`. (FR-021)
- [ ] T044 [D4] In `tests/test_diagnostics.py`, add a PLAIN
      test (NO xfail — this is a characterization test of
      EXISTING behaviour) asserting that the
      `async_get_config_entry_diagnostics` entrypoint is
      importable and callable. This tests FR-022 and ships
      GREEN in the red commit because the entrypoint already
      exists. (FR-022)

### GREEN PHASE COMMIT — Deliverable 4 (implementation)

- [ ] T045 [D4] In
      `custom_components/hospitable/api/exceptions.py`, add a
      `trace_id: str | None = None` keyword parameter to
      `HospitableError.__init__` and store it as
      `self.trace_id`. (FR-017)
- [ ] T046 [D4] In `HospitableRateLimitError.__init__` in
      `exceptions.py`, add `trace_id: str | None = None` to
      the parameter list and forward it to
      `super().__init__(..., trace_id=trace_id)`. Same for
      `HospitableRequestValidationError.__init__`. (FR-017)
- [ ] T047 [D4] In `_raise_for_status` in
      `custom_components/hospitable/api/client.py`, before
      raising any `HospitableError` subclass, extract
      `trace_id = response.headers.get("x-hospitable-trace")`
      and pass it as the `trace_id` keyword argument to every
      exception constructor call. Measure `wc -l client.py`
      after the change — it MUST stay under 440. (FR-018)

      **File-size contingency**: If `client.py` exceeds 440
      lines after this change, extract `_raise_for_status` and
      its helpers (`classify_403`, `parse_error_envelope`)
      into a new `api/status.py` module before committing.
- [ ] T048 [D4] Add a `last_trace_id: str | None = None`
      attribute to each coordinator class. In
      `HospitableDataUpdateCoordinator` (the base class in
      `coordinator.py`), add it as an instance attribute
      initialized to `None`. After each successful
      `_get_with_response` call (or wherever headers are
      available post-fetch), read
      `headers.get("x-hospitable-trace")` and store it. If
      the header is absent, store `None` — never an empty
      string. (FR-019, FR-020)
- [ ] T049 [D4] In `_coordinator_section` in
      `custom_components/hospitable/diagnostics.py`, add
      `"last_trace_id": getattr(coordinator, "last_trace_id",
      None)` to the returned dict. Since this is nested inside
      `"coordinators"` which is in `ALLOWED_TOP_LEVEL`, the
      trace passes through the redactor unredacted. (FR-019,
      FR-021)
- [ ] T050 [D4] Remove all `xfail` markers and
      `# type: ignore[...]` comments from T038–T043 tests. Run
      `uv run pytest tests/ -q` and confirm all tests pass.
- [ ] T051 [D4] Run the write-isolation test suite. Confirm all
      20 tests pass. (SC-005)
- [ ] T052 [D4] Measure `wc -l client.py` and record in the
      commit message. Confirm it remains under 440.

**Exit criteria**: Error responses with trace header produce logs
containing the trace. Diagnostics payload includes
per-coordinator trace IDs. Absent header produces `None`.
Trace passes through redactor unredacted. Entrypoint callable.
Write-isolation green. `client.py` under 440 lines.

---

## Phase 6: Deliverable 5 — Relative-day window override (US5, P2)

**Goal**: `lookforward_days` and `lookbackward_days` optional
parameters on `get_reservations` for per-call window overrides.

**Independent test**: With `lookahead_days` at default 90, invoke
`get_reservations` with `lookforward_days: 400`. Confirm the
API is called with an end date 400 days out.

**Requirements**: FR-023 to FR-032.

### RED PHASE COMMIT — Deliverable 5 (tests only)

All tests below are in
`tests/actions/test_get_reservations_window.py`.

**Critical trap (FR-028)**: `ServiceNotFound` SUBCLASSES
`ServiceValidationError`. Every test asserting
`ServiceValidationError` MUST first assert the service IS
registered via `hass.services.has_service(DOMAIN,
"get_reservations")`.

**Note on `vol.Schema` rejection**: The current
`GET_RESERVATIONS_SCHEMA` uses `vol.Schema({...})` which by
default REJECTS unknown keys. Passing `lookforward_days` to the
service before the field is added to the schema will raise
`ServiceValidationError` (from Voluptuous via HA). This is a
real red-phase failure for T054, but NOT the same assertion as
"out of range" — T054 tests that the window actually extends,
which requires the field to be accepted AND the handler to use
it. Both conditions fail. Pin `raises=AssertionError` for
behavioural tests that assert on the API call parameters.

- [ ] T053 [D5] Add an xfail test (`raises=ServiceValidationError`)
      that first asserts the service IS registered:
      `assert hass.services.has_service(DOMAIN,
      "get_reservations")`. Then calls `get_reservations` with
      `lookforward_days: 400`. Fails with
      `ServiceValidationError` because the schema rejects the
      unknown key. Verify:
      `uv run pytest --runxfail <node>`. (FR-023)

      **Why `raises=ServiceValidationError`**: `vol.Schema`
      rejects unknown keys by default. HA catches
      `vol.MultipleInvalid` and raises
      `ServiceValidationError`. The `has_service` assertion
      passes first (service exists), then `async_call` raises
      `ServiceValidationError`. The service IS registered, so
      this is not `ServiceNotFound`.
- [ ] T054 [D5] Add an xfail test
      (`raises=ServiceValidationError`) that first asserts the
      service IS registered, then calls `get_reservations` with
      `lookbackward_days: 30`. Mocks the API and would assert
      the API was called with a start date 30 days ago. In the
      red phase, fails with `ServiceValidationError` because
      the schema rejects the unknown `lookbackward_days` key.
      Verify: `uv run pytest --runxfail <node>`.
      (FR-023, FR-025)
- [ ] T055 **MOVED TO GREEN PHASE.** See T055 in the green
      phase section below. (FR-027, FR-028)

      **Why moved**: In the red phase the schema field does
      not exist, so `vol.Schema` rejects `lookforward_days`
      as an unknown key with `ServiceValidationError` — the
      same exception type the xfail marker pins. The test
      therefore XFAILs for the wrong reason (unknown-key
      rejection, not `vol.Range` validation), producing a
      meaningless red phase that cannot verify range-boundary
      behaviour. These tests belong in the green phase as
      plain passing tests, where `vol.Range` produces the
      rejection after the schema field exists.
- [ ] T056 **MOVED TO GREEN PHASE.** See T056 below.
      Same wrong-reason XFAIL issue as T055. (FR-026, FR-028)
- [ ] T057 **MOVED TO GREEN PHASE.** See T057 below.
      Same wrong-reason XFAIL issue as T055. (FR-027, FR-028)
- [ ] T058 **MOVED TO GREEN PHASE.** See T058 below.
      Same wrong-reason XFAIL issue as T055. (FR-026, FR-028)
- [ ] T059 [D5] Add an xfail test
      (`raises=ServiceValidationError`) asserting that
      `lookbackward_days: 0` is VALID — future-only search.
      First assert service is registered. Call with
      `lookbackward_days: 0`, expect success. The test asserts
      the API was called with `start == today`. In the red
      phase, `ServiceValidationError` fires (schema rejects
      unknown key). Pin `raises=ServiceValidationError`.
      Verify: `uv run pytest --runxfail <node>`. (FR-026)
- [ ] T060 [D5] Add an xfail test (`raises=AssertionError`)
      for the deliberate backward-default asymmetry: call
      `get_reservations` with NO `lookforward_days` or
      `lookbackward_days` (both omitted, no schema rejection).
      The current handler runs normally. Assert the API was
      called with `start == today - timedelta(days=7)`. The
      current handler uses config `lookback_days` (default 90),
      so the actual start is `today - timedelta(days=90)` and
      the assertion fails with `AssertionError`. Verify:
      `uv run pytest --runxfail <node>`. (FR-025)

      **This is the key behavioural red test for D5.** The
      deliberate asymmetry — backward defaults to 7, not the
      config's `lookback_days` — is the exact behaviour being
      introduced.
- [ ] T061 [D5] Add an xfail test (`raises=AssertionError`)
      asserting that the docstring of
      `async_handle_get_reservations` no longer contains the
      phrase "the service and the entities describe the same
      span of time" (FR-031). Currently it does contain that
      phrase. Pin `raises=AssertionError`. Verify:
      `uv run pytest --runxfail <node>`. (FR-031)

### GREEN PHASE COMMIT — Deliverable 5 (implementation)

- [ ] T062 [D5] In
      `custom_components/hospitable/actions/schemas.py`, add
      two constants and two schema fields:

      ```python
      ATTR_LOOKFORWARD_DAYS = "lookforward_days"
      ATTR_LOOKBACKWARD_DAYS = "lookbackward_days"
      ```

      Add to `GET_RESERVATIONS_SCHEMA`:

      ```python
      vol.Optional(ATTR_LOOKFORWARD_DAYS): vol.All(
          vol.Coerce(int), vol.Range(min=1, max=1095)
      ),
      vol.Optional(ATTR_LOOKBACKWARD_DAYS): vol.All(
          vol.Coerce(int), vol.Range(min=0, max=365)
      ),
      ```

      (FR-023, FR-026, FR-027)
- [ ] T063 [D5] In `async_handle_get_reservations` in
      `custom_components/hospitable/actions/get_reservations.py`,
      modify the window calculation to use per-call overrides:

      ```python
      lookforward = call.data.get(
          ATTR_LOOKFORWARD_DAYS,
          int(entry.options.get(
              CONF_LOOKAHEAD_DAYS, LOOKAHEAD_DEFAULT
          )),
      )
      lookbackward = call.data.get(
          ATTR_LOOKBACKWARD_DAYS, 7
      )
      today = dt_util.utcnow().date()
      start = today - timedelta(days=lookbackward)
      end = today + timedelta(days=lookforward)
      ```

      Import `ATTR_LOOKFORWARD_DAYS` and
      `ATTR_LOOKBACKWARD_DAYS` from `actions.schemas`.
      (FR-023, FR-024, FR-025)

      **Deliberate asymmetry — document in a comment**:
      `lookforward` inherits config `lookahead_days`;
      `lookbackward` defaults to fixed 7. This is intentional.
      See FR-025 justification. Do NOT "correct" it to
      symmetry.
- [ ] T064 [D5] Rewrite the `async_handle_get_reservations`
      docstring in `get_reservations.py`. Remove the sentence
      "The queried window matches the one the reservation
      coordinator polls, so the service and the entities
      describe the same span of time." Replace with:

      > When both parameters are omitted the forward reach
      > matches the reservation coordinator's
      > `lookahead_days`; the backward reach defaults to 7
      > days (not `lookback_days`). Callers who need the
      > sensors' exact window must pass both parameters
      > explicitly.

      (FR-031)
- [ ] T065 [D5] Add the `lookforward_days` and
      `lookbackward_days` field definitions to
      `custom_components/hospitable/services.yaml` under the
      `get_reservations` service. Both are optional. Add
      appropriate selectors (number with min/max/step).
      (FR-023)
- [ ] T066 [D5] Add field name and description strings for
      `lookforward_days` and `lookbackward_days` to
      `custom_components/hospitable/strings.json` under
      `services.get_reservations.fields`. Description for
      `lookforward_days`: "Number of days to look forward
      (1–1095). Defaults to the integration's lookahead_days
      option." Description for `lookbackward_days`: "Number
      of days to look backward (0–365). Defaults to 7 — not
      the integration's lookback_days option." (FR-023)
- [ ] T067 [D5] Copy the exact same field blocks into
      `custom_components/hospitable/translations/en.json`.
      The `services` sections of `strings.json` and
      `translations/en.json` MUST remain BYTE-IDENTICAL.
      (FR-023)
- [ ] T055 [P] [D5] Add a test (NO xfail — plain passing test)
      that first asserts the service IS registered, then calls
      `get_reservations` with `lookforward_days: 1096` (above
      the 1095-day ceiling). Assert `ServiceValidationError`
      is raised. Now that the schema field exists,
      `vol.Range(max=1095)` rejects the value and HA raises
      `ServiceValidationError`. Verify:
      `uv run pytest <node> -v`. (FR-027, FR-028)
- [ ] T056 [P] [D5] Add a test (NO xfail) that first asserts
      the service IS registered, then calls
      `get_reservations` with `lookbackward_days: 366` (above
      365). Assert `ServiceValidationError` is raised via
      `vol.Range(max=365)`. Verify:
      `uv run pytest <node> -v`. (FR-026, FR-028)
- [ ] T057 [P] [D5] Add a test (NO xfail) that first asserts
      the service IS registered, then calls
      `get_reservations` with `lookforward_days: 0` (below 1).
      Assert `ServiceValidationError` is raised via
      `vol.Range(min=1)`. Verify:
      `uv run pytest <node> -v`. (FR-027, FR-028)
- [ ] T058 [P] [D5] Add a test (NO xfail) that first asserts
      the service IS registered, then calls
      `get_reservations` with `lookbackward_days: -1` (below
      0). Assert `ServiceValidationError` is raised via
      `vol.Range(min=0)`. Verify:
      `uv run pytest <node> -v`. (FR-026, FR-028)
- [ ] T068 [D5] Remove all `xfail` markers and
      `# type: ignore[...]` comments from T053–T061 tests.
      Run `uv run pytest tests/ -q` and confirm all tests
      pass.
- [ ] T069 [D5] Run the write-isolation test suite. Confirm
      all 20 tests pass. (SC-005)

**Exit criteria**: `lookforward_days: 400` extends window.
`lookbackward_days: 30` extends backward. Out-of-range values
raise `ServiceValidationError`. Defaults match FR-024/FR-025.
`date_query` unchanged (FR-029). Response through chokepoint
(FR-030). Docstring rewritten (FR-031). `services.yaml`,
`strings.json`, `translations/en.json` updated and in sync.
Write-isolation green.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, sync verification, traceability,
and comprehensive validation.

**Principle XII status**: EXEMPT — verification-only and
documentation-only tasks.

- [ ] T070 Verify `strings.json` and `translations/en.json` are
      BYTE-IDENTICAL in their `services` sections by running
      `diff` on the normalized JSON or `cmp` on the raw files.
      Fix any divergence. (FR-023, SC-005)
- [ ] T071 Verify that `tests/test_documentation.py` passes
      with all changes. In particular confirm service
      descriptions are documented in `README.md` and `info.md`
      where required by existing documentation tests.
- [ ] T072 Run the full write-isolation test suite one final
      time across all three files: `test_no_writes.py`,
      `test_write_isolation.py`,
      `test_isolation_discovery.py`. Confirm all 20 tests
      pass. **No existing assertion may be deleted, weakened,
      renamed, or skipped** — if a gate fails, the design is
      wrong, not the gate. (SC-005)
- [ ] T073 Run the full test suite: `uv run pytest tests/ -q`.
      Confirm all tests pass (590 + new). Run
      `uv run ruff check custom_components/ tests/`. Run
      `uv run mypy custom_components/ tests/`. Run
      `uv run mypy` (bare — should now work after D3).
- [ ] T074 **Traceability table**: Verify the table below covers
      all 32 FRs (FR-001 to FR-032) and all 7 SCs (SC-001 to
      SC-007). Any gap is a defect in this file.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **D3 (Phase 2)**: Independent — can start after Phase 1.
- **D1 (Phase 3)**: Independent — can start after Phase 1.
- **D2 (Phase 4)**: Independent — can start after Phase 1.
- **D4 (Phase 5)**: Independent — can start after Phase 1.
- **D5 (Phase 6)**: Independent — can start after Phase 1.
- **Polish (Phase 7)**: Depends on all prior phases.

### Deliverable Independence

All five deliverables are INDEPENDENT. Each ships in its own PR.
No deliverable depends on another. The recommended ordering
(D3 → D1 → D2 → D4 → D5) is a risk/size gradient, not a
dependency chain.

### Within Each Deliverable

- Red-phase tests MUST land as a tests-only commit BEFORE the
  green-phase implementation commit.
- Constants before functions, functions before registration.
- Schema changes and handler changes for the same service are in
  the same green-phase commit.

### Parallel Opportunities

Tasks marked `[P]` within a single deliverable can run in
parallel (different files, no dependencies). Red-phase tests
marked `[P]` can be written in parallel.

---

## Parallel example

    # D1 red phase, parallel tests:
    uv run pytest --runxfail tests/sensor/test_task_count_cancelled.py::test_cancelled_statuses_import
    uv run pytest --runxfail tests/sensor/test_task_count_cancelled.py::test_exhaustiveness
    uv run pytest --runxfail tests/sensor/test_task_count_cancelled.py::test_cancelled_count_present

    # D2 red phase, parallel tests:
    uv run pytest --runxfail tests/actions/test_listing_privacy.py::test_listing_keys_import
    uv run pytest --runxfail tests/actions/test_listing_privacy.py::test_listing_filter_disabled
    # each --runxfail scoped to node ids, never bare.

---

## Implementation strategy

**Each deliverable is its own PR.** Recommended ordering:

1. **D3** (Phase 2) — 1-line config change, zero risk, XII-exempt
2. **D1** (Phase 3) — self-contained in `sensor/tasks.py`
3. **D2** (Phase 4) — self-contained in `actions/response.py` +
   docstring fix
4. **D4** (Phase 5) — cross-cutting but small changes per file
5. **D5** (Phase 6) — most surface area (5 files)

**MVP = D3 alone** — simplest possible PR to validate the
workflow. Then D1 and D2 (both P1 priority) as the first
substantive deliverables.

---

## Notes and known gaps

- **`api/client.py` at 410 lines — D4 headroom.** The plan
  projects ~420 after D4's trace extraction. Measure after
  implementation (T052). If it exceeds 440, extract
  `_raise_for_status` before committing.
- **`vol.Schema` rejects unknown keys by default.** The D5
  red-phase tests that pass `lookforward_days` or
  `lookbackward_days` to the service before the field is added
  fail with `ServiceValidationError` from schema rejection.
  This means range-boundary tests (T055–T058) cannot use
  `xfail(raises=ServiceValidationError)` in the red phase —
  they would XFAIL for the wrong reason (unknown-key rejection
  rather than `vol.Range` validation), making the red phase
  meaningless. These tests are therefore placed in the green
  phase as plain passing tests, where `vol.Range` produces the
  rejection.
- **`ServiceNotFound` subclasses `ServiceValidationError`.**
  Every D5 test that asserts `ServiceValidationError` first
  asserts the service IS registered. This is mandated by
  FR-028 and hardened by experience.
- **The two `cancelled` concepts (D1).** `progress_status` and
  `assignment_status` BOTH contain `cancelled`. The bucket
  MUST key on `progress_status`. Fixtures are SYNTHETIC — no
  cancelled task has been observed in live data.
- **D5 backward default asymmetry is DELIBERATE.** Forward
  inherits config `lookahead_days`; backward defaults to fixed
  7. Do NOT "correct" this to symmetry.
- **D5 lookforward_days 1095 ceiling.** 1095 ≈ 3 years is the
  live-confirmed upstream ceiling. Beyond it, Hospitable
  returns HTTP 400 with a misleading message about
  "prices and availabilities."

---

## Requirement to task traceability

| Requirement | Tasks |
| --- | --- |
| FR-001 | T010, T017 |
| FR-002 | T013, T018 |
| FR-003 | T012, T013, T019, T020 |
| FR-004 | T016 |
| FR-005 | T014, T016, T020 |
| FR-006 | T015, T020, T024 |
| FR-007 | T011, T024 |
| FR-008 | T018, T021 |
| FR-009 | T026, T027, T037 |
| FR-010 | T032, T033 |
| FR-011 | T025, T027, T030, T031 |
| FR-012 | T028, T033, T037 |
| FR-013 | T029, T033 |
| FR-014 | T034 |
| FR-015 | T008, T009 |
| FR-016 | T009 |
| FR-017 | T038, T045, T046 |
| FR-018 | T039, T047 |
| FR-019 | T040, T042, T048, T049 |
| FR-020 | T041, T048 |
| FR-021 | T042, T043, T049 |
| FR-022 | T044 |
| FR-023 | T053, T054, T062, T065, T066, T067 |
| FR-024 | T054, T063 |
| FR-025 | T060, T063 |
| FR-026 | T056, T058, T059, T062 |
| FR-027 | T055, T057, T062 |
| FR-028 | T053, T055, T056, T057, T058 |
| FR-029 | (no task needed — `date_query` is unchanged, verified by existing tests) |
| FR-030 | (verified by existing `serialize_response` call path — no change) |
| FR-031 | T061, T064 |
| FR-032 | (no task needed — no changes to options or sensors by design) |

### Success criteria

| Criterion | Tasks |
| --- | --- |
| SC-001 | T014, T020 |
| SC-002 | T026, T028, T037 |
| SC-003 | T008, T009 |
| SC-004 | T042, T049 |
| SC-005 | T001, T023, T036, T051, T069, T072, T073 |
| SC-006 | T027, T030 |
| SC-007 | T053, T054 |
