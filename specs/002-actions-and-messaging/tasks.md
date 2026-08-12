<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Tasks: Actions and Messaging

**Input**: Design documents from `/specs/002-actions-and-messaging/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`, `quickstart.md`. Spec 001 is complete and merged; its
`tasks.md` is the format precedent for this file.

**Tests**: Test tasks are MANDATORY. Constitution Principle I
(NON-NEGOTIABLE) makes code-level TDD mandatory and Principle IX forbids
deferring unit-level TDD. Per Principle XII (Red-Phase Commit Protocol)
tests land as a red-phase commit containing tests only, with every test
marked `@pytest.mark.xfail(raises=..., reason="...", strict=True)`; the
implementation lands as a separate green-phase commit that removes those
markers and the `# type: ignore[...]` comments.

**Organization**: Tasks are grouped by user story so each story can be
implemented, tested, and shipped independently. One pull request per
user story, in priority order US1..US6.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story the task belongs to (US1..US6)
- Exact file paths are given in every task
- Trailing parentheses list the functional requirements the task serves

## Path Conventions

Single project. Integration code lives under
`custom_components/hospitable/`, tests under `tests/`, packaging files at
the repository root. Paths follow `plan.md` §Module layout.

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
   does not — which is the common case in this feature, because
   `api/client.py`, `coordinator.py`, and `sensor/` all already exist.
   `warn_unused_ignores = true` is the mypy analogue of `xfail_strict`
   and forces these to be removed at green phase.
5. **`tests/conftest.py` imports no not-yet-existing module at all.**
   Fixtures needing integration objects are factory fixtures returning a
   callable that performs its import inside its own body.
6. **A red phase where every test dies on `ModuleNotFoundError` proves
   nothing.** Wherever the module under test ALREADY EXISTS, the
   red-phase test MUST fail with a real `AssertionError` against real
   observed behaviour, not with an import error. Tasks below state which
   exception each group is expected to raise.
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
no new production behaviour. Phase 1, Phase 2, and Phase 9 below are
exempt on those grounds and are therefore NOT split red/green.

---

## Terminology that tasks MUST honour

- **202 means ACCEPTED, not DELIVERED.** The send is asynchronous. No
  service response, log line, `strings.json` string, `services.yaml`
  description, or docstring may say "sent" or "delivered". The only
  permitted phrasing is "accepted for delivery".
  `sent_reference_id` is a correlation handle, not proof of delivery.
- **Never "unread".** The upstream API has no read-state field. The
  indicator is "awaiting host reply".
- **A privacy control scoped to one surface does not protect another
  surface.** Entity attributes, the recorder, logs, diagnostics,
  exception text, and SERVICE RESPONSES are six distinct exposure
  surfaces. A task that cites an entity-attribute control does not
  thereby cover a service response. `profile_picture` has no permitted
  surface at all; contact details are gated per surface (FR-046).
- **`include=guest` is SINGULAR.** Plural `guests` is a silently-ignored
  no-op upstream.
- **The messages endpoint is NOT paginated** and IS rate limited. See
  the live-probe evidence block below.

---

## Live-probe evidence (2026-08-12, read-only GETs)

A read-only probe of `GET /reservations/{uuid}/messages` was performed
against the live account after this task list was first written. No POST
was issued. The findings below are **CONFIRMED-BY-TEST** and are
authoritative for the tasks that cite them.

1. **The endpoint is NOT paginated.** The envelope is `{data}` only —
   no `meta`, no `links`, unlike `/reservations` and `/tasks`, which
   carry all three. `per_page=1`, `per_page=2`, `page=1`, `page=2`, and
   `per_page=1&page=2` all returned the identical full set of 10 items.
   Both parameters are **silently ignored** — a further, newly
   observed instance of the silent-ignore behaviour class. Spec 001
   FR-075 records five distinct instances; this is not one of them and
   is not assigned an ordinal here, because FR-075's prose order and
   spec 001 `research.md`'s "the fifth" label do not agree and
   inventing a sixth number would entrench that disagreement.
   **Scope caveat, stated honestly**: the busiest conversation on this
   account holds only 10 messages, so behaviour above that volume was
   NOT observed. Pagination may appear above some threshold. Tasks
   therefore assert the observed contract AND require the code to
   tolerate a `meta`/`links` block appearing later rather than crashing.
   The practical consequence today is that there is no way to bound the
   payload: a very long conversation arrives in full, so no code may
   assume a small list.
2. **The endpoint is rate limited at 2 requests per 60 seconds, PER
   RESERVATION.** It returns `x-ratelimit-limit: 2` and
   `x-ratelimit-remaining: <n>`. On 429 it also returns
   `retry-after: 60` (observed 59–60) and `x-ratelimit-reset: <epoch>`.
   The buckets are independent per reservation: reservation A was burned
   to `remaining: 0` and returned 429, and reservation B immediately
   returned HTTP 200 with a fresh `remaining: 1`.
3. **The 429 body is the Laravel envelope with NO `errors` key**:
   `{"status_code": 429, "reason_phrase": "Too Many Attempts."}`. The
   shared envelope parser must tolerate the missing key.
4. **This is scoped to the messages endpoint ONLY.** `/properties`,
   `/reservations`, and `/tasks` were re-checked in the same session and
   expose NO `x-ratelimit-*` and NO `retry-after` headers. Spec 001's
   recorded finding remains CORRECT for the endpoints spec 001 tested.
   This is **not** a spec 001 defect, and spec 001 must not be edited.

---

## Phase 1: Setup (test scaffolding and fixtures)

**Purpose**: Test-tree scaffolding and synthetic fixtures that every
later phase depends on. **Ships in**: the US1 pull request.

**Principle XII status**: EXEMPT — test-only and fixture-only changes
that assert no new production behaviour. Do not force these into a
red/green pair.

- [X] T001 Create `tests/actions/__init__.py` and
      `tests/actions/conftest.py` as empty-but-valid modules. The
      `conftest.py` MUST NOT import any `custom_components.hospitable`
      module that does not yet exist at module level (protocol rule 5).
- [X] T002 [P] Create `tests/fixtures/messages_thread.json`: a synthetic
      multi-message thread with at least one host message and one guest
      message, each carrying `created_at`, `sender_type`/role, and
      `body`. Bodies MUST be obviously synthetic (no real guest text).
      (FR-020, FR-024)
- [X] T003 [P] Create `tests/fixtures/messages_empty.json`: a
      well-formed empty-thread response, used to prove the
      awaiting-host-reply and `last_message_at` sensors degrade
      gracefully. (FR-036, FR-037)
- [X] T004 [P] Create `tests/fixtures/tasks_page1.json` with a full
      first page including a `meta` block carrying BOTH `task_types` and
      `service_types` enum tables, and pagination metadata indicating a
      second page exists. The `meta` block MUST encode the real trap:
      Maintenance appears as `task_type` 5 and as `service_id` 8.
      (FR-030, FR-031, FR-033)
- [X] T005 [P] Create `tests/fixtures/tasks_page2.json` as the second and
      final page, with pagination metadata indicating no further pages.
      (FR-031)
- [X] T006 [P] Create `tests/fixtures/reservation_with_guest.json`
      containing three reservations: one with a complete `guest` object
      (`first_name`, `last_name`, `location`, `language`, `email`,
      `phone_numbers`, `profile_picture`), one whose `guest` object has
      NO `last_name` key (this genuinely occurs upstream), and one whose
      `guest` value is `null`. All values synthetic. (FR-039, FR-039b,
      FR-040)
- [X] T007 [P] Create `tests/fixtures/send_message_202_full.json` and
      `tests/fixtures/send_message_202_empty.json`. The first carries a
      `sent_reference_id`; the second is an empty body. **OQ-001 is
      UNVERIFIED** — no real send has been performed, so the exact 202
      body shape is unknown. Both fixtures exist precisely so the
      implementation is forced to handle either. Neither fixture may be
      described anywhere as the confirmed upstream shape. (FR-012,
      OQ-001)
- [X] T008 [P] Create `tests/fixtures/error_envelope_400.json` and
      `tests/fixtures/error_envelope_422.json`, both in the Laravel
      shape `{status_code, reason_phrase, errors: {field: [messages]}}`.
      They are deliberately structurally identical so that one parser
      demonstrably serves both the `/tasks` 400 and the send 422.
      (FR-015, FR-030, FR-045)
- [X] T008a [P] Create `tests/fixtures/error_envelope_429.json` holding
      the OBSERVED 429 body exactly: `status_code` and `reason_phrase`
      with NO `errors` key. This is the same Laravel envelope family
      with a field absent, and exists so the shared parser is forced to
      tolerate that absence rather than raising a `KeyError`. (FR-015,
      FR-045)
- [X] T009 Add SPDX headers or `REUSE.toml` coverage for every file
      created in T001..T008a and run `uv run reuse lint` to confirm the
      tree is compliant. JSON fixtures cannot carry comments, so they
      MUST be covered by a `REUSE.toml` annotation rather than an
      in-file header.

**Exit criteria**: `uv run pytest` collects cleanly, `uv run reuse lint`
passes, and no fixture contains real personal data.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: Constants, test helpers, and factory fixtures that all six
user stories consume. **Ships in**: the US1 pull request.

**Principle XII status**: EXEMPT — T010 and T011 are constant-only
additions with no behaviour; T012..T018 are test-only helpers. If any of
these acquires behaviour during implementation, it MUST be moved into a
red/green pair.

**⚠️ BLOCKS all user stories. Complete before starting Phase 3.**

- [X] T010 Add endpoint path constants to
      `custom_components/hospitable/api/const.py`: a single-reservation
      path, a reservation-messages path (used for both `GET` and
      `POST`), and a tasks path. Follow the existing naming style of
      `RESERVATIONS_PATH` and `PROPERTIES_PATH`. (FR-009, FR-020,
      FR-030)
- [X] T011 Add option keys and defaults to
      `custom_components/hospitable/const.py`: the awaiting-host-reply
      toggle (default `False`), the guest-contact-details toggle
      (default `False`), and the task poll interval (default 15 minutes,
      floor 5 minutes). Both toggles default OFF; that default is a
      requirement, not a preference. (FR-037, FR-038a, FR-038b, FR-034)
- [X] T012 Add factory fixtures to `tests/actions/conftest.py` that
      return callables performing their `custom_components.hospitable`
      imports inside the callable body, never at module scope. Provide
      at minimum: a write-client factory, a service-call factory, and a
      loaded-config-entry factory. (protocol rule 5)
- [X] T013 Add a `respx` route-builder helper to
      `tests/actions/conftest.py` for the messages endpoint that can
      serve a 202 with either body shape from T007, a 422 from T008, and
      a 403. (FR-012, FR-015, FR-016)
- [X] T013a Extend the T013 route builder so every messages-endpoint
      response can carry `x-ratelimit-limit`, `x-ratelimit-remaining`,
      and `x-ratelimit-reset` headers, and so it can serve a 429 with
      `retry-after` plus the T008a body. Headers must be settable per
      response so a test can walk `remaining` down to zero and then
      throttle. (FR-017, FR-019)
- [X] T013b Add a per-reservation route-builder mode so a test can hold
      two distinct reservation UUIDs with INDEPENDENT header budgets,
      matching the observed per-reservation bucketing. (FR-017)
- [X] T014 Create `tests/helpers/__init__.py` and
      `tests/helpers/ast_isolation.py`, a test-only helper that parses a
      Python source file with `ast` and returns the set of imported
      names, imported modules, and attribute names referenced. This is
      the machinery gate 3 of the write-isolation design depends on; it
      is a test helper and MUST NOT be imported by production code.
      (FR-001)
- [X] T015 Extend the fixture-scanning assertions in
      `tests/test_privacy.py` so the new fixtures from T002..T008 are
      included in the synthetic-data audit rather than silently skipped.
      (FR-024, FR-041)
- [X] T016 Add a test helper that loads `services.yaml` and
      `strings.json` and returns the set of service names and field
      names declared in each. This is the machinery for the
      localisation-parity assertions in every later phase. (FR-007)
- [X] T017 Add a token-hashing test helper that produces the same
      SHA-256 key the rate limiter will use, so tests can assert budget
      sharing without reaching into private state. The helper MUST NOT
      log or persist the raw token. (FR-018)
- [X] T018 Add a shared assertion helper
      `assert_no_delivery_language(text)` to `tests/helpers/` that fails
      if a string contains "sent", "delivered", or "delivery
      confirmed" in a claim-of-delivery sense. Every phase that adds
      user-facing text asserts against it. (FR-011)

**Exit criteria**: helpers importable, suite green, no production
behaviour changed.

---

## Phase 3: User Story 1 — Service infrastructure and send message (P1)

**Goal**: A user can send a guest message via a Home Assistant service
call and receive an explicit acceptance confirmation, with rate limits
enforced and the polling lifecycle proven still write-free.

**Independent test**: Call `hospitable.send_message` against a mocked
202 and assert the response reports acceptance (never delivery); call it
three times within a minute for one reservation and assert the third is
refused; run the full polling lifecycle and assert zero non-GET
requests.

**Requirements**: FR-001 to FR-019, FR-044, FR-045.

### RED PHASE COMMIT — US1 (tests only)

Expected failure modes are stated per task. Groups touching
`api/client.py`, `coordinator.py`, `sensor/`, and `config_flow.py` MUST
fail with `AssertionError`, because those modules already exist —
`ModuleNotFoundError` there means the test is wrong, not the code.

- [X] T019 [US1] In `tests/actions/test_write_client.py`, add xfail
      tests (`raises=AttributeError`) asserting that the base client
      class in `custom_components/hospitable/api/client.py` has NO
      `_post` attribute and that a new `HospitableWriteClient` subclass
      does. Import inside the test body. Note in the docstring that the
      real base class name is `HospitableApiClient`, not
      `HospitableClient` as written in `plan.md` and `research.md`.
      (FR-001, FR-003)
- [X] T020 [P] [US1] In `tests/actions/test_write_client.py`, add xfail
      tests (`raises=AttributeError`) that `HospitableWriteClient`
      inherits every existing GET helper from the base client and adds
      no second HTTP session, connection pool, or auth path. (FR-003)
- [X] T021 [P] [US1] In `tests/actions/test_write_client.py`, add an
      xfail test (`raises=AttributeError`) that `_post` raises the same
      classified errors as `_get` for 401/403/5xx, reusing the existing
      `_raise_for_status` and `classify_403` logic rather than
      duplicating it. (FR-016, FR-045)
- [X] T022 [US1] Write-isolation **gate 1** (typing): in
      `tests/test_write_isolation.py`, add an xfail test
      (`raises=AssertionError`) asserting that every coordinator class
      in `custom_components/hospitable/coordinator.py` annotates its
      client attribute as the BASE client type. **Observed
      discrepancy**: coordinators currently store the client privately
      as `self._client`, and `research.md` D-01 gate 2 is written
      against a public `coordinator.client`. This test asserts against
      the attribute that actually exists; see Notes and known gaps.
      (FR-001)
- [X] T023 [US1] Write-isolation **gate 2** (runtime): in
      `tests/test_write_isolation.py`, add an xfail test
      (`raises=AssertionError`) asserting, for every coordinator class,
      that its client instance is NOT an instance of
      `HospitableWriteClient`. (FR-001)
- [X] T024 [US1] Write-isolation **gate 3** (static AST scan): in
      `tests/test_write_isolation.py`, add an xfail test
      (`raises=AssertionError`) that uses the T014 helper to scan
      `custom_components/hospitable/coordinator.py`, every module under
      `custom_components/hospitable/sensor/`, and
      `custom_components/hospitable/config_flow.py`, failing if any
      imports `HospitableWriteClient`, imports from the `actions`
      package, or references `_post`. (FR-001)
- [X] T025 [US1] Write-isolation **gate 4** (lifecycle): add xfail tests
      (`raises=AssertionError`) covering the NARROWED form of
      `tests/test_no_writes.py` — the polling lifecycle still issues
      zero non-GET requests, while a service call is permitted to issue
      a POST. `tests/test_no_writes.py` MUST be preserved in narrowed
      form and MUST NOT be deleted. Its docstring currently cites spec
      001's "T140, FR-059"; update it to cite FR-001/FR-002. (FR-001,
      FR-002)
- [X] T026 [P] [US1] In `tests/actions/test_registration.py`, add xfail
      tests (`raises=ModuleNotFoundError`) that
      `custom_components/hospitable/actions/__init__.py` exposes a
      table-driven registration function registering every service in a
      single declarative table, following the Hostaway reference
      pattern. (FR-005)
- [X] T027 [P] [US1] In `tests/actions/test_registration.py`, add an
      xfail test (`raises=ModuleNotFoundError`) that registration is
      IDEMPOTENT: calling setup twice, or loading a second config entry,
      does not re-register, and the guard is an explicit
      `hass.services.has_service()` check. (FR-005)
- [X] T028 [US1] In `tests/actions/test_registration.py`, add an xfail
      test (`raises=AssertionError`) that services are removed ONLY when
      the LAST config entry for the domain unloads, and remain
      registered while any other entry is still loaded. **Observed
      discrepancy**: this integration uses `entry.runtime_data`, not
      `hass.data[DOMAIN]`, so the Hostaway guard
      `if not hass.data.get(DOMAIN)` cannot be copied verbatim; the test
      must count loaded entries via the config-entry registry. See Notes
      and known gaps. (FR-006)
- [X] T029 [P] [US1] In `tests/actions/test_disambiguation.py`, add
      xfail tests (`raises=ModuleNotFoundError`) for the multi-entry
      resolution helper: with exactly one loaded entry the
      `config_entry_id` field is optional; with two or more loaded
      entries omitting it raises `ServiceValidationError`; an unknown or
      unloaded id raises `ServiceValidationError`. (FR-008, FR-029,
      FR-045)
- [X] T030 [P] [US1] In `tests/actions/test_send_message.py`, add xfail
      tests (`raises=ModuleNotFoundError`) for the reservation target:
      the service accepts EITHER a reservation UUID directly OR an
      entity id that resolves to one, and rejects an entity id that does
      not belong to this integration. (FR-044)
- [X] T031 [US1] In `tests/actions/test_send_message.py`, add an xfail
      test (`raises=ModuleNotFoundError`) for the happy path against a
      mocked 202: the handler returns a response that reports the
      message was **accepted for delivery**. Assert with the T018
      helper that the response contains no delivery claim. (FR-009,
      FR-011)
- [X] T032 [US1] In `tests/actions/test_send_message.py`, add xfail
      tests (`raises=ModuleNotFoundError`) that the correlation handle
      is surfaced when present and that its ABSENCE is handled without
      error. Parameterise over both T007 fixtures. **OQ-001 is
      UNVERIFIED**: no real send has been made, so the test MUST NOT
      assert that either shape is the true upstream shape. (FR-012,
      OQ-001)
- [X] T033 [P] [US1] In `tests/actions/test_send_message.py`, add xfail
      tests (`raises=ModuleNotFoundError`) for the request body schema:
      `body` is a required non-empty string, `images` is an optional
      array of URIs with a maximum of 3, and `sender_id` is optional.
      Assert `body` is transmitted VERBATIM — in particular that no
      literal `/n` to newline substitution is performed. (FR-010,
      FR-014)
- [X] T034 [US1] In `tests/actions/test_send_message.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that `sender_id` is REJECTED
      with `ServiceValidationError` for a non-Airbnb reservation and
      accepted for an Airbnb one. The reservation model already carries
      the upstream `platform` value under the field name `channel`
      (`api/models.py:173`, populated from `payload.get("platform")`),
      so the test MUST key off `channel`; no new field is added.
      (FR-013)
- [X] T034a [US1] In `tests/actions/test_send_message.py`, add xfail
      tests (`raises=ModuleNotFoundError`) for platform resolution per
      FR-013: with NO `sender_id`, assert zero extra requests and no
      platform lookup at all; with `sender_id` and a cached
      reservation, assert the cached `channel` is used and zero extra
      requests are issued; with `sender_id` and an UNCACHED
      reservation, assert exactly one `GET /reservations/{uuid}` is
      issued; and when that lookup fails, 404s, or yields a null
      `channel`, assert `ServiceValidationError` is raised and NO POST
      is issued. The unresolved case must reject, never silently skip
      the check. (FR-013)
- [X] T035 [P] [US1] In `tests/actions/test_send_message.py`, add xfail
      tests (`raises=ModuleNotFoundError`) for the Laravel error
      envelope: a 422 from `error_envelope_422.json` maps to
      `ServiceValidationError` with the per-field messages preserved,
      and transport errors and 5xx map to `HomeAssistantError`.
      (FR-015, FR-045)
- [X] T035a [P] [US1] In `tests/actions/test_send_message.py`, add an
      xfail test (`raises=ModuleNotFoundError`) that the SAME parser
      handles `error_envelope_429.json`, which carries `status_code` and
      `reason_phrase` but NO `errors` key. A missing `errors` key must
      not raise. (FR-015, FR-045)
- [X] T036 [P] [US1] In `tests/actions/test_send_message.py`, add an
      xfail test (`raises=ModuleNotFoundError`) that a 403 on the send
      endpoint surfaces as an actionable `HomeAssistantError` whose
      message tells the user the token may lack the send scope.
      **OQ-005 is UNVERIFIED**: whether the PAT actually carries the
      send scope has not been established by any real send. The test
      must not assert that it does. (FR-016, OQ-005)
- [X] T037 [P] [US1] In `tests/actions/test_rate_limit.py`, add xfail
      tests (`raises=ModuleNotFoundError`) for the per-reservation
      budget: 2 messages per rolling 60 seconds, third refused, budget
      recovering as the window slides. This figure is CONFIRMED-BY-TEST
      for the messages GET and documented for the send. (FR-017,
      FR-019)
- [X] T038 [P] [US1] In `tests/actions/test_rate_limit.py`, add xfail
      tests (`raises=ModuleNotFoundError`) for the per-token budget: 50
      per rolling 300 seconds. This figure is DOCUMENTED ONLY and has
      not been tested; the test asserts the implementation honours the
      documented number, not that upstream enforces it. (FR-017,
      FR-019)
- [X] T038a [US1] In `tests/actions/test_rate_limit.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that the tracker is
      TWO-DIMENSIONAL and that BOTH gates are evaluated before every
      send: the per-(token, reservation) 2-per-60s gate and the
      per-token 50-per-300s gate. Exhausting either one alone must
      refuse the call. The original framing of "keys on the token" is
      correct for the 50/5min budget but incomplete — there are two
      distinct dimensions. (FR-017, FR-018, FR-019)
- [X] T038b [US1] In `tests/actions/test_rate_limit.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that per-reservation buckets
      are INDEPENDENT: exhausting reservation A leaves reservation B
      immediately callable. This is CONFIRMED-BY-TEST upstream — A
      returned 429 while B returned 200 with a fresh remaining count.
      (FR-017)
- [X] T038c [US1] In `tests/actions/test_rate_limit.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that `x-ratelimit-remaining`
      and `x-ratelimit-reset` from a response are fed back into the
      tracker, and that when the server's remaining count DISAGREES with
      the locally-counted budget the SERVER value wins. Blind local
      counting is a floor, not the authority. (FR-017, FR-019)
- [X] T038d [US1] In `tests/actions/test_rate_limit.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that a 429 is treated as
      RETRYABLE-WITH-BACKOFF driven by `retry-after`, and not as a hard
      failure. See OQ-007: it is unknown whether reads and writes share
      one per-reservation bucket, so the send path must survive being
      throttled by a poll. (FR-019, OQ-007)
- [X] T039 [US1] In `tests/actions/test_rate_limit.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that accounting keys on the
      TOKEN, not the config entry: two distinct config entries holding
      the SAME token share one budget, and entries with different tokens
      have independent budgets. Use the T017 hashing helper; assert the
      raw token never appears in the tracker's keys. (FR-018)
- [X] T040 [US1] In `tests/actions/test_rate_limit.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that a refusal raises
      `ServiceValidationError` BEFORE any HTTP request is issued, and
      that the budget is recorded only on acceptance, never on failure.
      (FR-019, FR-045)

**Red-phase gate**: run `uv run pytest --runxfail` scoped to the node
ids above and confirm each fails with its declared exception. Commit
tests only.

### GREEN PHASE COMMIT — US1

- [X] T041 [US1] Create `custom_components/hospitable/api/write_client.py`
      with `HospitableWriteClient` subclassing the existing
      `HospitableApiClient`, adding `_post` and reusing the inherited
      session, auth, timeout, `_raise_for_status`, and `classify_403`.
      (FR-003, FR-016)
- [X] T042 [US1] Create `custom_components/hospitable/api/messages.py`
      with the send helper that builds and issues the message POST and
      returns the parsed acceptance result. (FR-009, FR-010)
- [X] T043 [US1] Add a shared Laravel error-envelope parser to
      `custom_components/hospitable/api/responses.py` returning
      structured field errors. ONE parser serves both the send 422 and
      the `/tasks` 400 — do not write a second. It MUST tolerate an
      absent `errors` key, which the observed 429 body demonstrates.
      (FR-015, FR-045)
- [X] T044 [US1] Create `custom_components/hospitable/actions/__init__.py`
      with table-driven registration and removal, an idempotent
      `hass.services.has_service()` guard, and removal only when the
      last loaded entry unloads. (FR-005, FR-006)
- [X] T045 [US1] Create `custom_components/hospitable/actions/helpers.py`
      with multi-entry resolution and reservation-target resolution
      (UUID or entity id). Adapt, do not copy, the Hostaway
      `_resolve_entry_data` pattern: this integration stores state on
      `entry.runtime_data`, so resolution enumerates loaded config
      entries for the domain. (FR-008, FR-029, FR-044)
- [X] T046 [US1] Create `custom_components/hospitable/actions/schemas.py`
      with the voluptuous schema for `send_message`: required `body`,
      optional `images` (max 3 URIs), optional `sender_id`, optional
      `config_entry_id`, and the reservation target. (FR-010, FR-014)
- [X] T047 [US1] Create
      `custom_components/hospitable/actions/rate_limit.py` with the
      module-level tracker keyed on SHA-256 of the token, holding a
      per-(token, reservation) deque and a per-token deque. Never store
      or log the raw token. (FR-017, FR-018)
- [X] T047a [US1] Surface response headers from the API client. `_get`
      currently returns only the parsed JSON body and DISCARDS the
      `httpx.Response`, so `x-ratelimit-*` is unreachable today. Add a
      way for callers that need them to obtain the headers, without
      changing the return type of the existing GET helpers used by
      spec 001's coordinators. (FR-017)
- [X] T047b [US1] Feed `x-ratelimit-limit`, `x-ratelimit-remaining`, and
      `x-ratelimit-reset` into the tracker whenever a messages-endpoint
      response carries them, with the server's value overriding the
      local count. Absence of the headers must be tolerated — no other
      endpoint sends them. (FR-017, FR-019)
- [X] T047c [US1] Handle 429 on the messages endpoint as a
      retryable-with-backoff condition driven by `retry-after`. **Reuse
      the EXISTING `parse_retry_after` in
      `custom_components/hospitable/api/retry.py`** — it is present and
      already wired into `_raise_for_status`, and it already parses both
      the delta-seconds and HTTP-date forms and caps at `MAX_BACKOFF`.
      Do not write a second parser. What is genuinely new is reading the
      `x-ratelimit-*` family, which nothing currently does. (FR-019)
- [X] T048 [US1] Create
      `custom_components/hospitable/actions/send_message.py` with the
      handler: validate, check rate limit, resolve platform for the
      `sender_id` rule per FR-013 (skip entirely without `sender_id`;
      cache first; one direct `GET /reservations/{uuid}` otherwise;
      reject on unresolved), POST, record the budget on acceptance, and
      return the acceptance result. Uses `SupportsResponse.ONLY` per
      plan Deviation 2. (FR-009, FR-011, FR-013, FR-019)
- [X] T049 [US1] Implement defensive handling of the 202 body in the
      send path: extract the correlation handle if present, proceed
      normally if the body is empty or unparsable. Add an inline
      comment naming OQ-001 as the reason. (FR-012, OQ-001)
- [X] T050 [US1] Implement the Airbnb-only `sender_id` rule, sourcing
      the candidate identifier from the property listings' co-host
      entries and rejecting `sender_id` for any non-Airbnb reservation.
      (FR-013)
- [X] T051 [US1] Extend the listing model in
      `custom_components/hospitable/api/models.py` to carry co-host
      identifiers, which the current model does not have. This model
      extension is required by FR-013 but is NOT recorded in
      `data-model.md`; see Notes and known gaps. (FR-013)
- [X] T052 [US1] Register the services from `async_setup_entry` in
      `custom_components/hospitable/__init__.py` and remove them from
      `async_unload_entry` only when no other entry for the domain
      remains loaded. (FR-005, FR-006)
- [X] T053 [US1] Create `custom_components/hospitable/services.yaml`
      describing `send_message` with every field, selector, and example.
      No such file currently exists and `plan.md`'s module layout omits
      it; it is nonetheless required by FR-007. (FR-007)
- [X] T054 [US1] Add service name, description, and per-field labels and
      descriptions for `send_message` to
      `custom_components/hospitable/strings.json`. Omitting this is the
      Hostaway anti-pattern we explicitly do not copy. (FR-007)
- [X] T055 [US1] Mirror the T054 additions into
      `custom_components/hospitable/translations/en.json`. (FR-007)
- [X] T056 [US1] Audit all text added in T053..T055 with the T018 helper
      so no string claims the message was sent or delivered; the only
      permitted phrasing is "accepted for delivery". Include the
      asynchronous nature explicitly in the service description.
      (FR-011)
- [X] T057 [US1] Document in `services.yaml` and `strings.json` that
      each image must be at most 5 MB, and note in the handler that this
      limit is NOT client-side enforceable because images are supplied
      as URIs rather than uploads. Do not implement a fake size check.
      (FR-010, FR-014)
- [X] T058 [US1] Narrow `tests/test_no_writes.py` per T025: assert the
      polling lifecycle issues zero non-GET requests while permitting
      service-call POSTs. Preserve the file; update its docstring to
      cite FR-001/FR-002. (FR-002)
- [X] T059 [US1] Ensure no service handler triggers a coordinator
      refresh; add the assertion to `tests/actions/test_send_message.py`
      and keep handlers free of `async_request_refresh` calls. (FR-004)
- [X] T060 [US1] Remove every US1 xfail marker and `# type: ignore`
      comment added in T019..T040, run the full suite plus
      `uv run mypy` and `uv run ruff check`, and confirm green.

**Exit criteria**: `send_message` callable and rate-limited; all four
write-isolation gates passing; `tests/test_no_writes.py` present in
narrowed form; `services.yaml`, `strings.json`, and `translations/en.json`
all carry the service text; suite, mypy, and ruff green.

---

## Phase 4: User Story 2 — Read messages and lookup services (P2)

**Goal**: All five services are operational. Users can query message
threads, reservations, and properties on demand. Everything in this
phase is GET-only.

**Independent test**: Call each of `get_messages`, `find_reservation`,
`get_reservations`, and `get_property_info` against mocked responses and
assert the returned data; call each against a not-found condition and
assert a return value rather than an exception.

**Requirements**: FR-020 to FR-029.

### RED PHASE COMMIT — US2 (tests only)

- [X] T061 [P] [US2] In `tests/actions/test_get_messages.py`, add xfail
      tests (`raises=ModuleNotFoundError`) for the happy path against
      `messages_thread.json`: the handler returns the thread with
      timestamps and sender roles preserved in upstream order.
      (FR-020)
- [X] T062 [P] [US2] In `tests/actions/test_get_messages.py`, add an
      xfail test (`raises=ModuleNotFoundError`) that the service is
      declared `SupportsResponse.ONLY`. (FR-021)
- [X] T063 [P] [US2] In `tests/actions/test_get_messages.py`, add xfail
      tests (`raises=ModuleNotFoundError`) that the reservation target
      is accepted as either a UUID or an entity id. (FR-022, FR-044)
- [X] T064 [US2] In `tests/actions/test_get_messages.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that the messages response is
      consumed in ONE request: assert the envelope carries `data` only,
      with NO `meta` and NO `links`, and that exactly one HTTP request
      is issued. **OQ-002 is CLOSED — CONFIRMED-BY-TEST**: this endpoint
      is not paginated, unlike `/reservations` and `/tasks`. Do NOT
      write a pagination loop here. (FR-023)
- [X] T064a [US2] In `tests/actions/test_get_messages.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that the handler never sends
      `page` or `per_page` to this endpoint. Both are SILENTLY IGNORED
      upstream — `per_page=1`, `page=2`, and `per_page=1&page=2` all
      returned the identical full set. Sending them would create a false
      impression that the payload is bounded. (FR-023)
- [X] T064b [US2] In `tests/actions/test_get_messages.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that a LARGE thread — build a
      fixture with several hundred messages — is handled without
      truncation and without assuming a small list, because there is no
      upstream mechanism to bound the payload. (FR-023)
- [X] T064c [US2] In `tests/actions/test_get_messages.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that a response which DOES
      carry a `meta` or `links` block is tolerated rather than crashing.
      The observed non-pagination was measured against a busiest thread
      of only 10 messages, so pagination appearing above some unobserved
      threshold cannot be ruled out. This test guards forward
      compatibility; it must not be written as if pagination were the
      expected behaviour. (FR-023)
- [X] T064d [US2] In `tests/actions/test_get_messages.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that the GET honours the
      CONFIRMED per-reservation limit of 2 requests per 60 seconds and
      that a 429 surfaces as a clear, retryable condition rather than a
      crash or a silent empty result. (FR-017, FR-019, FR-023)
- [X] T065 [US2] In `tests/actions/test_get_messages.py`, add an xfail
      test (`raises=AssertionError`) that message bodies never appear in
      any log record emitted during the call, at any level. This must
      fail on real captured log output, not on an import error.
      (FR-024)
- [X] T066 [P] [US2] In `tests/actions/test_get_messages.py`, add an
      xfail test (`raises=ModuleNotFoundError`) that an empty thread
      (`messages_empty.json`) returns an empty collection rather than
      raising. (FR-020, FR-028)
- [X] T067 [P] [US2] In `tests/actions/test_lookups.py`, add xfail tests
      (`raises=ModuleNotFoundError`) for `find_reservation`: located by
      the documented lookup key, returning the reservation payload.
      (FR-025)
- [X] T068 [P] [US2] In `tests/actions/test_lookups.py`, add xfail tests
      (`raises=ModuleNotFoundError`) for `get_reservations` including
      its filter arguments. (FR-026)
- [X] T069 [P] [US2] In `tests/actions/test_lookups.py`, add xfail tests
      (`raises=ModuleNotFoundError`) for `get_property_info`, including
      the listings and co-host structure that FR-013 depends on.
      (FR-027)
- [X] T070 [US2] In `tests/actions/test_lookups.py`, add xfail tests
      (`raises=ModuleNotFoundError`) that not-found is a RETURN VALUE
      for every lookup service — an explicit empty or `found: false`
      result — and never an exception. (FR-028)
- [X] T071 [P] [US2] In `tests/actions/test_lookups.py`, add xfail tests
      (`raises=ModuleNotFoundError`) that every lookup service accepts
      the optional `config_entry_id` and applies the same disambiguation
      rules proven in T029. (FR-029)
- [X] T072 [P] [US2] In `tests/actions/test_registration.py`, extend the
      xfail registration-table tests (`raises=AssertionError`) to expect
      all five services present in the table, each with its declared
      `SupportsResponse` value. (FR-005, FR-020)
- [X] T072a [P] [US2] Create `tests/actions/test_response_privacy.py`
      and add an xfail test (`raises=ModuleNotFoundError`) that
      `profile_picture` is ABSENT from the response of EVERY registered
      service, under EVERY combination of the guest-contact-details and
      awaiting-host-reply options. Drive the fixture from
      `reservation_with_guest.json`, whose complete guest DOES carry a
      `profile_picture`, so the assertion fails if the key is passed
      through. Enumerate services from the registration table rather
      than a hard-coded list, so a sixth service added later is covered
      automatically. (FR-046, FR-047, FR-048, SC-003a)
- [X] T072b [US2] In `tests/actions/test_response_privacy.py`, add xfail
      tests (`raises=ModuleNotFoundError`) that `email` and
      `phone_numbers` are ABSENT from `find_reservation` and
      `get_reservations` responses when the guest-contact-details option
      is OFF (the default) and PRESENT when it is ON, while
      `first_name`, `last_name`, `location`, and `language` are returned
      in both cases. This is the service-response half of the control
      whose entity-attribute half is FR-039c. (FR-047, SC-003a)
- [X] T072c [US2] In `tests/actions/test_response_privacy.py`, add an
      xfail test (`raises=ModuleNotFoundError`) that an UNKNOWN guest
      key injected into the fixture (simulating a new upstream field) is
      DROPPED from the response. The serialiser is an allowlist, not a
      denylist: a denylist would leak the next PII field Hospitable adds
      by default. (FR-047, FR-048)
- [X] T072d [US2] In `tests/actions/test_response_privacy.py`, add an
      xfail test (`raises=ModuleNotFoundError`) that `get_messages`
      never returns the opaque `sender` object, and that `sender_type`
      and `sender_role` ARE returned. `sender` may carry guest identity
      and contact fields; the role discriminators may not. (FR-047a,
      SC-003a)
- [X] T072e [US2] In `tests/actions/test_response_privacy.py`, add an
      xfail test (`raises=AssertionError`) that every service handler
      module routes its return value through the shared serialiser:
      scan the AST of `custom_components/hospitable/actions/*.py` and
      fail if any handler constructs a response dict containing a
      `guest` or `sender` key without calling the serialiser. This is
      what stops a future service from silently bypassing the
      chokepoint. (FR-048)
- [X] T073 [US2] In `tests/actions/test_localisation.py`, add xfail
      tests (`raises=AssertionError`) using the T016 helper that every
      service in the registration table has a matching `services.yaml`
      entry AND matching `strings.json` and `translations/en.json` text
      for the service and for every one of its fields. This must fail on
      a real parity assertion. (FR-007)

**Red-phase gate**: `uv run pytest --runxfail` scoped to the above.

### GREEN PHASE COMMIT — US2

- [X] T074 [US2] Extend `custom_components/hospitable/api/messages.py`
      with a SINGLE-REQUEST thread-fetch helper. No pagination loop:
      OQ-002 is closed by live probe and the endpoint returns the whole
      thread in one `{data}` envelope. Tolerate an unexpected
      `meta`/`links` block without crashing, and record in a comment
      that non-pagination was observed only up to a 10-message thread.
      (FR-023)
- [X] T074a [US2] Apply the per-reservation rate-limit accounting and
      the `x-ratelimit-*` header feedback from T047b to the messages
      GET, so reads and writes share one tracker. Handle 429 with
      `retry-after` backoff. (FR-017, FR-019, OQ-007)
- [X] T075 [US2] Add the `HospitableMessage` model to
      `custom_components/hospitable/api/models.py` per `data-model.md`.
      (FR-020)
- [X] T075a [US2] Create
      `custom_components/hospitable/actions/response.py`: the SINGLE
      response serialiser every handler returns through, per
      `research.md` D-16. It emits an explicit ALLOWLIST — guest
      `first_name`, `last_name`, `location`, `language`, plus `email`
      and `phone_numbers` only when the guest-contact-details option is
      enabled on the config entry serving the call — drops
      `profile_picture` unconditionally, drops the opaque message
      `sender` object unconditionally, and drops any key not on the
      allowlist. It MUST NOT be duplicated per handler and MUST NOT
      rely on callers to filter. (FR-046, FR-047, FR-047a, FR-048)
- [X] T076 [US2] Create
      `custom_components/hospitable/actions/get_messages.py` with the
      handler, `SupportsResponse.ONLY`, and no logging of message
      bodies at any level. (FR-020, FR-021, FR-024)
- [X] T077 [US2] Create
      `custom_components/hospitable/actions/find_reservation.py`.
      (FR-025, FR-028)
- [X] T078 [US2] Create
      `custom_components/hospitable/actions/get_reservations.py`.
      (FR-026, FR-028)
- [X] T079 [US2] Create
      `custom_components/hospitable/actions/get_property_info.py`,
      returning listings including co-host identifiers so operators can
      discover the values FR-013 requires. (FR-027, FR-028, FR-013)
- [X] T079a [US2] Route `get_messages`, `find_reservation`,
      `get_reservations`, `get_property_info`, and the `send_message`
      acceptance payload through the T075a serialiser. No handler
      serialises an upstream payload itself. (FR-048)
- [X] T080 [US2] Extend
      `custom_components/hospitable/actions/schemas.py` with the four
      new service schemas, each carrying the optional
      `config_entry_id`. (FR-022, FR-029, FR-044)
- [X] T081 [US2] Add all four services to the registration table in
      `custom_components/hospitable/actions/__init__.py`. (FR-005)
- [X] T082 [US2] Extend `custom_components/hospitable/services.yaml`
      with all four services and every field. (FR-007)
- [X] T083 [US2] Extend `custom_components/hospitable/strings.json` and
      `custom_components/hospitable/translations/en.json` with matching
      service and field text for all four. (FR-007)
- [X] T084 [US2] Remove every US2 xfail marker and `# type: ignore`
      comment, then run the full suite, `uv run mypy`, and
      `uv run ruff check`.

**Exit criteria**: all five services registered, tested, localised, and
documented; not-found is a return value everywhere; the thread is
fetched in a single request with no pagination loop while tolerating an
unexpected `meta`/`links` block; and every service response passes
through the one serialiser, with `profile_picture` and the raw `sender`
object absent unconditionally and contact details gated on the opt-in.

---

## Phase 5: User Story 3 — Guest identity on reservation entities (P3)

**Goal**: Guest first and last name appear on reservation sensors, with
contact details behind an opt-in that defaults OFF, no guest data in
logs, diagnostics, or the recorder, and `profile_picture` never exposed.

**Independent test**: Load the integration against
`reservation_with_guest.json` and assert guest attributes on the
reservation status entity for the complete guest, graceful degradation
for the guest missing `last_name`, and no guest attributes at all for
the null guest; assert email and phone are absent until the option is
enabled.

**Requirements**: FR-038b, FR-039 to FR-043, and spec 001 FR-075.

### RED PHASE COMMIT — US3 (tests only)

- [X] T085 [US3] In `tests/api/test_guest_model.py`, add xfail tests
      (`raises=AttributeError`) that a `HospitableGuest` model parses
      `first_name`, `last_name`, `location`, and `language` from the
      upstream guest object per `data-model.md`. (FR-039)
- [X] T086 [P] [US3] In `tests/api/test_guest_model.py`, add xfail tests
      (`raises=AttributeError`) that a guest object with no `last_name`
      key parses successfully with the surname absent — this genuinely
      occurs upstream — and that a `null` guest yields no guest data
      rather than an error. (FR-039b, FR-040)
- [X] T087 [US3] In `tests/api/test_reservations_request.py`, add an
      xfail test (`raises=AssertionError`) that the reservation polling
      request sends `include=guest` — SINGULAR — stacked
      comma-separated with the existing `properties` include. Assert the
      literal parameter value; plural `guests` is a silently-ignored
      upstream no-op. (FR-039)
- [X] T088 [US3] In `tests/api/test_reservations_request.py`, add an
      xfail test (`raises=AssertionError`) that the code ASSERTS the
      `guest` key is actually present in each returned item rather than
      assuming the include was honoured, because unrecognised include
      names are silently ignored upstream. Reuse the existing
      include-assertion helper in `api/responses.py`. (FR-040, spec 001
      FR-075)
- [X] T089 [P] [US3] In `tests/sensor/test_reservation.py`, add xfail
      tests (`raises=AssertionError`) that the reservation status entity
      exposes the four default guest attributes when available and omits
      them when the guest is null. (FR-039a)
- [X] T090 [US3] In `tests/sensor/test_reservation.py`, add an xfail
      test (`raises=AssertionError`) that guest email and phone numbers
      are ABSENT by default and present only when the
      guest-contact-details option is enabled. Default OFF is a
      requirement. (FR-039c, FR-038b)
- [X] T091 [US3] In `tests/sensor/test_reservation.py`, add an xfail
      test (`raises=AssertionError`) that `profile_picture` is NEVER
      exposed as an entity attribute under ANY option combination.
      (FR-039d)
- [X] T092 [US3] In `tests/sensor/test_reservation.py`, add an xfail
      test (`raises=AssertionError`) that EVERY guest attribute — both
      default and opt-in — appears in the entity's
      `_unrecorded_attributes`. Follow the existing precedent in
      `custom_components/hospitable/sensor/availability.py`. (FR-039e,
      FR-042)
- [X] T093 [P] [US3] In `tests/sensor/test_reservation.py`, add an xfail
      test (`raises=AssertionError`) that the reservation UUID is
      exposed as an entity attribute so service calls can target the
      entity. (FR-044)
- [X] T094 [US3] In `tests/test_privacy.py`, add xfail tests
      (`raises=AssertionError`) that no guest name, email, phone,
      location, or language appears in any log record at any level
      during a full poll cycle. Must fail on real captured output.
      (FR-041)
- [X] T095 [US3] In `tests/test_diagnostics.py`, add xfail tests
      (`raises=AssertionError`) that every guest field is redacted from
      the diagnostics payload, including the opt-in fields and
      `profile_picture`. (FR-042, FR-043)
- [X] T096 [P] [US3] In `tests/test_config_flow.py`, add xfail tests
      (`raises=AssertionError`) that the options flow exposes the
      guest-contact-details toggle, that it defaults to disabled, and
      that its description states the privacy implication. (FR-038b)

**Red-phase gate**: `uv run pytest --runxfail` scoped to the above. Note
that most of these MUST fail with `AssertionError`, not an import error
— every module involved already exists.

### GREEN PHASE COMMIT — US3

- [X] T097 [US3] Add `HospitableGuest` to
      `custom_components/hospitable/api/models.py` with tolerant parsing
      for a missing surname and a null guest. (FR-039, FR-039b, FR-040)
- [X] T098 [US3] Attach the parsed guest to the reservation model. Take
      care: `HospitableReservation.guests` already exists and holds
      NUMERIC occupancy counts; the new field is singular `guest` and is
      a different thing. (FR-039)
- [X] T099 [US3] Change the reservation request builder in
      `custom_components/hospitable/api/reservations.py` to send
      `include=guest,properties`. (FR-039)
- [X] T100 [US3] Assert the `guest` key is present on returned items
      using the existing include-assertion helper, and surface a clear
      error when it is not. (FR-040, spec 001 FR-075)
- [X] T101 [US3] Extend
      `custom_components/hospitable/sensor/reservation.py` with the four
      default guest attributes and the reservation UUID attribute.
      (FR-039a, FR-044)
- [X] T102 [US3] Gate email and phone attributes behind the
      guest-contact-details option, default OFF. (FR-039c, FR-038b)
- [X] T103 [US3] Ensure `profile_picture` is never read into an entity
      attribute at all. (FR-039d)
- [X] T104 [US3] Add every guest attribute name to the entity's
      `_unrecorded_attributes`. (FR-039e, FR-042)
- [X] T105 [US3] Extend `custom_components/hospitable/diagnostics.py` to
      redact all guest fields. (FR-042, FR-043)
- [X] T106 [US3] Add the guest-contact-details toggle to the options
      flow in `custom_components/hospitable/config_flow.py`. (FR-038b)
- [X] T107 [US3] Add the option label and description to
      `strings.json` and `translations/en.json`, stating plainly that
      enabling it places guest contact details into entity attributes.
      (FR-038b, FR-043)
- [X] T108 [US3] Remove every US3 xfail marker and `# type: ignore`
      comment, then run the full suite, `uv run mypy`, and
      `uv run ruff check`.

**Exit criteria**: guest names on entities when available, absent when
null, tolerant of a missing surname; contact details opt-in and OFF by
default; `profile_picture` never exposed; all guest attributes
unrecorded; nothing in logs or diagnostics.

---

## Phase 6: User Story 4 — Task sensors (P4)

**Goal**: Per-property task sensors are operational, the poll fans out
to one request per property so failures stay isolated, all pages are
fetched per property, and the task-type / service-type enums are kept
distinct.

**Independent test**: Load the integration against `tasks_page1.json`
and `tasks_page2.json` and assert the task count equals the combined
total across both pages and that a Maintenance task is labelled from the
task-type table rather than the service-type table.

**Requirements**: FR-030 to FR-035.

### RED PHASE COMMIT — US4 (tests only)

- [X] T109 [US4] In `tests/api/test_tasks.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that the tasks request ALWAYS sends
      a non-empty `properties[]` parameter — a bare request is a 400
      upstream. (FR-030)
- [X] T109a [US4] In `tests/api/test_tasks.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that a refresh across N selected
      properties issues N SEPARATE `/tasks` requests, each carrying
      exactly ONE property in `properties[]` — assert the request count
      and that no single request names two properties. This is the
      fan-out that makes per-property failure isolation possible.
      (FR-030, FR-034)
- [X] T110 [US4] In `tests/api/test_tasks.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that the request ALWAYS carries
      explicit `start_date` and `end_date` derived from the
      `task_window_days` option: `start_date` is today and `end_date`
      is today plus `task_window_days` (default 14). Also assert a
      dates-only request (no `properties[]`) is never constructed,
      because it too is a 400. (FR-030)
- [X] T111 [US4] In `tests/api/test_tasks.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that a 400 response parsed with the
      shared Laravel envelope parser from T043 surfaces as a clear
      error, proving one parser serves both the `/tasks` 400 and the
      send 422. (FR-030, FR-045)
- [X] T112 [US4] In `tests/api/test_tasks.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that pagination is exercised from
      day one: both fixture pages are fetched and the combined result
      contains every task from both. (FR-031)
- [X] T112a [US4] In `tests/api/test_tasks.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that pagination is followed PER
      PROPERTY: mock one property returning `meta.last_page: 2` and
      another returning `meta.last_page: 1`, and assert the first is
      fetched twice and the second exactly once. A shared page count
      taken from whichever property answered first would either lose
      tasks or issue a pointless request. (FR-031)
- [X] T113 [P] [US4] In `tests/api/test_tasks.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that the authoritative enum tables
      are read from the response `meta` block rather than hardcoded.
      (FR-033)
- [X] T114 [US4] In `tests/api/test_tasks.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that the task-type and service-type
      maps are SEPARATE and NOT interchangeable, asserting the concrete
      meta-vocabulary trap: Maintenance is task_type 5 with service_id
      8, while service_type 5 is Owner. A synthetic task with task_type
      5 must never be labelled by looking up 5 in the service-type
      table. (FR-033)
- [X] T115 [P] [US4] In `tests/api/test_tasks.py`, add xfail tests
      (`raises=ModuleNotFoundError`) that the `HospitableTask` model
      parses every field named in `data-model.md`, including nested
      `task_assignment.status`, nullable `progress_status`, ISO
      `start_date` / `end_date`, `timezone`, `duration_hours`, nested
      `reservation`, and allowed teammate fields. Assert
      `teammate.name` is not parsed into the model. (FR-035)
- [X] T115a [US4] In `tests/api/test_tasks.py`, add an xfail test
      (`raises=ModuleNotFoundError`) asserting the parser reads the
      property association from nested `property.id` and rejects a flat
      `property_id`. The recorded `/tasks` fixture must contain only the
      live-confirmed nested shape. The parser MUST NOT accept both
      shapes — a permissive reader would hide future drift permanently.
      (FR-032, FR-035)
- [X] T116 [US4] In `tests/test_coordinator.py`, add xfail tests
      (`raises=AttributeError`) for the tasks coordinator: it exists,
      polls on its own cadence, and holds a BASE client — the
      write-isolation gates from T022..T024 must cover it too.
      (FR-034, FR-001)
- [X] T117 [P] [US4] In `tests/test_coordinator.py`, add an xfail test
      (`raises=AttributeError`) that the task interval defaults to 15
      minutes and is clamped to a 5-minute floor. (FR-034)
- [X] T117a [US4] In `tests/test_coordinator.py`, add an xfail test
      (`raises=AttributeError`) for per-property failure isolation:
      with three properties selected and the SECOND returning a 500,
      assert the refresh still succeeds, that the failing property
      retains its previous (last-good) task data rather than being
      cleared or dropped, and that the other two properties reflect
      their new data. Mirrors the spec 001 D-15 calendar behaviour.
      (FR-034)
- [X] T118 [P] [US4] In `tests/sensor/test_tasks.py`, add xfail tests
      (`raises=ModuleNotFoundError`) for a per-property next-task sensor
      per `data-model.md`. (FR-032)
- [X] T119 [P] [US4] In `tests/sensor/test_tasks.py`, add xfail tests
      (`raises=ModuleNotFoundError`) for a per-property task-count
      sensor whose value equals the number of tasks for that property
      across ALL pages. (FR-031, FR-032)
- [X] T120 [P] [US4] In `tests/sensor/test_tasks.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that assignment status is exposed
      as an attribute, teammate identifiers may be exposed, and
      teammate personal names are never parsed into the model or
      surfaced in diagnostics. Treat `note` and `reservation.code` as
      protected unless a later requirement explicitly exposes them.
      (FR-035, FR-042)
- [X] T121 [P] [US4] In `tests/test_config_flow.py`, add an xfail test
      (`raises=AssertionError`) that the options flow exposes the task
      interval with the correct default and floor. (FR-034)
- [X] T121a [P] [US4] In `tests/test_options_bounds.py`, add an xfail
      test (`raises=AssertionError`) that `task_window_days` defaults
      to 14 and is bounds-validated in `options_bounds.py` with a
      named error key, rejecting 0 and any value above the maximum so
      `end_date` can never breach the upstream three-year ceiling.
      (FR-030)

**Red-phase gate**: `uv run pytest --runxfail` scoped to the above.

### GREEN PHASE COMMIT — US4

- [X] T122 [US4] Create `custom_components/hospitable/api/tasks.py` with
      the request builder — mandatory `properties[]` carrying exactly
      one property, plus explicit `start_date` (today) and `end_date`
      (today + `task_window_days`) — and a paginating fetch for that
      single property that follows its own `meta.last_page`.
      (FR-030, FR-031)
- [X] T123 [US4] Add `HospitableTask` to
      `custom_components/hospitable/api/models.py` per `data-model.md`.
      (FR-035)
- [X] T124 [US4] Build the two enum maps from the response `meta` block
      as SEPARATE structures with distinct names, with a comment
      recording that Maintenance is task_type 5 and service_id 8.
      (FR-033)
- [X] T125 [US4] Add `HospitableTasksCoordinator` to
      `custom_components/hospitable/coordinator.py`, annotated with the
      BASE client type, with a 15-minute default and 5-minute floor.
      (FR-034, FR-001)
- [X] T125a [US4] Make the tasks coordinator refresh fan out over the
      selected properties, awaiting one per-property fetch each and
      gathering results so a single property's exception cannot abort
      the others. On a per-property failure, log at debug and carry that
      property's previous data forward unchanged; raise only if EVERY
      property fails. Follow the spec 001 calendar coordinator's
      last-good retention rather than inventing a second pattern.
      (FR-030, FR-034)
- [X] T126 [US4] Create `custom_components/hospitable/sensor/tasks.py`
      with the next-task and task-count sensors. (FR-032)
- [X] T127 [US4] Register the new sensors in
      `custom_components/hospitable/sensor/__init__.py`. (FR-032)
- [X] T128 [US4] Add the task interval option and the
      `task_window_days` option to the options flow, with bounds
      validation in `options_bounds.py`, and wire both into the
      coordinator. (FR-034, FR-030)
- [X] T129 [US4] Add task sensor names, task interval option text, and
      state translations to `strings.json` and `translations/en.json`.
      (FR-007, FR-034)
- [X] T130 [US4] Extend the write-isolation gates from T022..T024 to
      include the tasks coordinator and the new sensor module.
      (FR-001)
- [X] T131 [US4] Remove every US4 xfail marker and `# type: ignore`
      comment, then run the full suite, `uv run mypy`, and
      `uv run ruff check`.

**Exit criteria**: one request per property, never a batched request;
all pages fetched for every property using that property's own
`meta.last_page`; task count matches the combined total; a single
property's failure leaves the others updating and preserves that
property's last-good data; Maintenance labelled from the task-type
table; 15-minute default with a 5-minute floor honoured.

---

## Phase 7: User Story 5 — Message presence indicators (P5)

**Goal**: A per-property last-message timestamp derived from data the
integration already holds, plus an opt-in awaiting-host-reply indicator
with a bounded, documented API cost.

**Independent test**: Assert the last-message sensor reports a timestamp
with no additional HTTP requests, and that the awaiting-host-reply
sensor is absent with the option off and performs at most one message
fetch per property per cycle with it on.

**Requirements**: FR-036, FR-037, FR-038, FR-038a.

### RED PHASE COMMIT — US5 (tests only)

- [ ] T132 [P] [US5] In `tests/sensor/test_messages.py`, add xfail tests
      (`raises=ModuleNotFoundError`) for a per-property last-message
      timestamp sensor. (FR-036)
- [ ] T133 [US5] In `tests/sensor/test_messages.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that the last-message sensor is
      derived from data ALREADY held by the reservation coordinator and
      issues ZERO additional HTTP requests. Assert on the recorded
      request count. (FR-036, FR-038)
- [ ] T134 [P] [US5] In `tests/sensor/test_messages.py`, add an xfail
      test (`raises=ModuleNotFoundError`) that the sensor degrades to an
      unknown state, not an error, when no messages exist. (FR-036)
- [ ] T135 [US5] In `tests/sensor/test_messages.py`, add xfail tests
      (`raises=ModuleNotFoundError`) that the awaiting-host-reply entity
      is ABSENT when the option is off and present when it is on, and
      that the option defaults OFF. (FR-037, FR-038a)
- [ ] T136 [US5] In `tests/sensor/test_messages.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that with the option enabled the
      integration performs AT MOST ONE message fetch per property per
      polling cycle. Assert on the recorded request count. (FR-037)
- [ ] T136a [US5] In `tests/sensor/test_messages.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that the EFFECTIVE per-reservation
      message-fetch interval is at least 60 seconds. The confirmed
      upstream limit of 2 requests per 60 seconds per reservation would
      mathematically permit a 30-second interval; 60 seconds is a
      DELIBERATELY CONSERVATIVE choice that consumes at most one of the
      two slots, leaving the other free for a user-initiated send. See
      OQ-007: if reads and writes share one bucket, polling at the
      mathematical maximum would starve the send path. (FR-037, FR-017,
      OQ-007)
- [ ] T136b [US5] In `tests/sensor/test_messages.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that a rapid double refresh — two
      manual coordinator refreshes back to back — does NOT exceed the
      per-reservation budget: the second fetch for the same reservation
      is skipped or deferred rather than issued. (FR-037, FR-017,
      FR-019)
- [ ] T136c [US5] In `tests/sensor/test_messages.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that fanning out across MANY
      DIFFERENT reservations in one cycle is permitted, because the
      buckets are per-reservation and independent. The constraint is
      per reservation, not global. (FR-037, FR-017)
- [ ] T136d [US5] In `tests/sensor/test_messages.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that a 429 on the message fetch is
      handled gracefully: `retry-after` is respected, the last-good
      indicator value is retained, and the entity is NOT marked
      unavailable. A throttle is not an outage. (FR-037, FR-019)
- [ ] T137 [US5] In `tests/sensor/test_messages.py`, add an xfail test
      (`raises=ModuleNotFoundError`) that the indicator computes from
      the sender role of the most recent message, and add an assertion
      over the entity name, `strings.json` text, and `translations`
      text that the word "unread" never appears — the upstream API has
      no read-state field. (FR-037)
- [ ] T138 [P] [US5] In `tests/sensor/test_messages.py`, add an xfail
      test (`raises=AssertionError`) that message bodies are never
      stored as entity attributes and never logged; only the derived
      indicator and timestamp are exposed. (FR-024, FR-041)
- [ ] T139 [P] [US5] In `tests/test_config_flow.py`, add an xfail test
      (`raises=AssertionError`) that the options flow exposes the
      awaiting-host-reply toggle, defaulting off, with a description
      stating the additional API cost and the read-state limitation.
      (FR-038a)

**Red-phase gate**: `uv run pytest --runxfail` scoped to the above.

### GREEN PHASE COMMIT — US5

- [ ] T140 [US5] Create `custom_components/hospitable/sensor/messages.py`
      with the last-message timestamp sensor derived from existing
      coordinator data. (FR-036, FR-038)
- [ ] T141 [US5] Add the awaiting-host-reply sensor to the same module,
      created only when the option is enabled. Per
      `contracts/entities.md` this is a SENSOR, not a `binary_sensor` —
      spec 002 introduces no new platform. (FR-037, FR-038a)
- [ ] T142 [US5] Add the bounded optional message fetch to the
      reservation coordinator in
      `custom_components/hospitable/coordinator.py`, capped at one fetch
      per property per cycle and skipped entirely when the option is
      off. (FR-037)
- [ ] T142a [US5] Enforce a per-reservation message-fetch floor of 60
      seconds in the coordinator, independent of the configured
      reservation poll interval — the reservation interval floor is 1
      minute, so an aggressively configured entry could otherwise reach
      the upstream limit. The floor is a conservative budget reservation,
      not the upstream maximum: 2 per 60 seconds would permit 30
      seconds, and the second slot is deliberately left unused so a
      user-initiated send is not starved (OQ-007). Route the fetch
      through the shared tracker from T047 rather than a second counter.
      (FR-037, FR-017, OQ-007)
- [ ] T142b [US5] Handle 429 on the optional message fetch without
      failing the whole reservation update: retain the previous
      indicator value, respect `retry-after`, and do not raise
      `UpdateFailed` for the reservation data that was fetched
      successfully. Note that the existing coordinator behaviour logs a
      429 and does NOT reschedule; the message fetch needs its own
      handling rather than inheriting that path. (FR-037, FR-019)
- [ ] T143 [US5] Register the new sensors in
      `custom_components/hospitable/sensor/__init__.py`. (FR-036,
      FR-037)
- [ ] T144 [US5] Add the awaiting-host-reply toggle to the options flow.
      (FR-038a)
- [ ] T145 [US5] Add sensor names, state text, and option text to
      `strings.json` and `translations/en.json`, stating the API cost
      and that the API exposes no read state. Never use "unread".
      (FR-007, FR-037, FR-038a)
- [ ] T146 [US5] Extend the write-isolation static scan to cover
      `sensor/messages.py` and the modified reservation coordinator.
      (FR-001)
- [ ] T147 [US5] Remove every US5 xfail marker and `# type: ignore`
      comment, then run the full suite, `uv run mypy`, and
      `uv run ruff check`.

**Exit criteria**: last-message timestamp reported with zero extra
requests; awaiting-host-reply correct when enabled and absent when
disabled; no user-facing text says "unread".

---

## Phase 8: User Story 6 — Integration testing and polish (P6)

**Goal**: Every success criterion has evidence, every `quickstart.md`
validation scenario is automated, and no spec 001 behaviour regressed.

**Independent test**: The full suite, plus each `quickstart.md` scenario
run individually.

**Requirements**: SC-001 to SC-009 verification; FR-001 to FR-045
regression.

**Principle XII status**: predominantly EXEMPT — test-only
strengthening of existing behaviour. If any task here uncovers a
behaviour change, that change gets its own red/green pair inside this
phase.

- [ ] T148 [US6] Add `tests/test_quickstart_vs.py` automating VS-1
      (polling lifecycle remains write-free) as an executable assertion
      against the narrowed `tests/test_no_writes.py` machinery.
      (FR-001, FR-002)
- [ ] T149 [P] [US6] Automate VS-2 (send message, mocked) and VS-3 (read
      messages, mocked) from `quickstart.md`. (FR-009, FR-020)
- [ ] T150 [P] [US6] Automate VS-4 (lookup services, mocked) from
      `quickstart.md`. (FR-025, FR-026, FR-027, FR-028)
- [ ] T150a [US6] Add the SC-007 side-effect assertion: subscribe a
      catch-all listener to the Home Assistant event bus, call every
      lookup service, and assert it captured no integration-fired
      event; assert no coordinator refresh was triggered and no entity
      state was written. SC-007 promises this and nothing currently
      asserts it. Latency is deliberately NOT asserted — under `respx`
      the response is already in memory, so a timing bound would
      measure the mock. (FR-025 to FR-028, SC-007)
- [ ] T151 [P] [US6] Automate VS-5 (task sensors) from `quickstart.md`.
      (FR-030, FR-031, FR-032, FR-033)
- [ ] T152 [P] [US6] Automate VS-6 (guest attributes on the reservation
      entity) from `quickstart.md`. (FR-039, FR-039a, FR-039b)
- [ ] T153 [US6] Automate VS-7 (PII audit) from `quickstart.md`,
      covering logs, diagnostics, and recorder exclusion for guest and
      message data in one pass. (FR-024, FR-041, FR-042, FR-043)
- [ ] T153a [US6] Automate VS-11 (service-response PII audit) from
      `quickstart.md`: call every registered service under both settings
      of the guest-contact-details option and assert `profile_picture`
      and the raw message `sender` object are absent in all cases, and
      that `email`/`phone_numbers` track the option. This is the
      service-response surface; T153 covers logs, diagnostics, and the
      recorder, and does NOT reach this one. (FR-046, FR-047, FR-047a,
      SC-003a)
- [ ] T154 [P] [US6] Automate VS-8 (multi-entry disambiguation) from
      `quickstart.md`. (FR-008, FR-029)
- [ ] T155 [P] [US6] Automate VS-9 (rate-limit enforcement) from
      `quickstart.md`. (FR-017, FR-019)
- [ ] T155a [P] [US6] Add an end-to-end throttling test: with the
      awaiting-host-reply option on, drive a reservation's
      `x-ratelimit-remaining` to zero across polling cycles, serve a
      429, and assert the entity keeps its last-good value, the poll
      does not fail, and the next fetch waits for `retry-after`.
      (FR-017, FR-019, FR-037)
- [ ] T156 [P] [US6] Automate VS-10 (static import isolation) from
      `quickstart.md`, reusing the T014 AST helper. (FR-001)
- [ ] T157 [US6] Add a genuine end-to-end test in
      `tests/test_e2e_actions.py` using a real `hass` instance, a
      `MockConfigEntry`, and `respx` — following the pattern already
      established in `tests/sensor/test_platform.py` — that sets up the
      integration, calls `send_message`, then `get_messages`, then a
      lookup service, and asserts entity state afterwards. No mocked
      coordinator, no monkeypatched handler. (SC-001, SC-002, SC-003)
- [ ] T158 [US6] Add a multi-entry rate-limit sharing test: two config
      entries with the SAME token share one budget end to end, through
      the real service call path rather than by poking the tracker.
      (FR-018)
- [ ] T159 [US6] Run a final localisation audit with the T016 helper:
      every registered service, every service field, every new option,
      and every new sensor has text in `services.yaml` where applicable
      and in BOTH `strings.json` and `translations/en.json`. Fail the
      build on any gap. (FR-007)
- [ ] T160 [US6] Run a final acceptance-language audit with the T018
      helper across `services.yaml`, `strings.json`,
      `translations/en.json`, and every handler docstring: nothing
      claims a message was sent or delivered, and nothing says
      "unread". (FR-011, FR-037)
- [ ] T161 [US6] Confirm all four write-isolation gates are green
      simultaneously and that `tests/test_no_writes.py` still exists in
      narrowed form. Add a comment to the file recording that FR-002
      forbids its deletion. (FR-001, FR-002)
- [ ] T162 [US6] Run the full spec 001 test suite unchanged and confirm
      no regression. Any spec 001 test that must change requires an
      explicit note in the PR description explaining why.
- [ ] T163 [US6] Verify each of SC-001 to SC-009 against a concrete
      test node id and record the mapping in the PR description. Any
      criterion that cannot be verified without a live account MUST be
      declared unverified rather than claimed. In particular, the
      SC-001 and SC-007 latency statements are MANUAL quickstart checks
      and MUST be reported as such, never as suite-verified.

**Exit criteria**: full suite, mypy, and ruff green; every quickstart
scenario automated; every success criterion either evidenced or
explicitly declared unverifiable without a live account.

---

## Phase 9: Polish and cross-cutting concerns

**Ships in**: the US6 pull request. **Principle XII status**: EXEMPT —
docs-only and test-only.

Phase 8 keeps the name `plan.md` gives the US6 phase ("Integration
testing and polish"). The division of labour between the two is:
Phase 8 is the automated evidence — quickstart scenarios, end-to-end
tests, and success-criteria verification. Phase 9 is the non-test
cross-cutting work — user documentation, licensing, and coverage
checks. Both ship in the same pull request.

- [ ] T164 [P] Update `README.md` with the five services, their
      arguments, and a worked automation example. State plainly that
      `send_message` returns acceptance, not delivery confirmation.
      (FR-007, FR-011)
- [ ] T165 [P] Document the two new options and the task interval in
      `README.md`, including the privacy implication of the
      guest-contact-details opt-in and the API cost of the
      awaiting-host-reply opt-in. (FR-038a, FR-038b, FR-043)
- [ ] T166 [P] Document the rate limits in `README.md`: the per-token
      50-per-5-minutes budget shared by every config entry using the
      same token, AND the per-reservation 2-per-60-seconds limit that
      applies to reading and sending messages. State that enabling the
      awaiting-host-reply option consumes per-reservation budget.
      (FR-017, FR-018, FR-037)
- [ ] T167 [P] Update `info.md` for HACS with a summary of the new
      capabilities.
- [ ] T168 Confirm `uv run reuse lint` passes over every file added or
      modified across all six phases.
- [ ] T169 Confirm coverage thresholds are met and that no new module is
      excluded from coverage or from mypy.
- [ ] T170 Record the still-open questions in the PR description:
      OQ-001 and OQ-005 remain UNVERIFIED and can only be closed by
      performing a real send, which has not been done. OQ-007 (whether
      reads and writes share one per-reservation bucket) is likewise
      unclosable without a real POST. OQ-002 is CLOSED by the
      2026-08-12 read-only probe. (OQ-001, OQ-005, OQ-007)
- [ ] T170a Raise OQ-007 for the record: the confirmed GET limit is 2
      per 60 seconds per reservation and the DOCUMENTED send limit is
      also 2 per 60 seconds per reservation, which makes a SHARED
      per-reservation bucket plausible but unproven. If shared, an
      awaiting-host-reply poll could consume budget a user needs to
      send a message, and vice versa. It cannot be tested without
      issuing a real POST to a real guest, which is prohibited. The
      design must be defensive in BOTH directions and must assert
      neither answer: the send path treats 429 as
      retryable-with-backoff rather than a hard failure (T038d,
      T047c), and the polling path must never starve the send path
      (T142a, T142b). (OQ-007)
- [ ] T171 Re-read this task list against `spec.md` and confirm every FR
      from FR-001 to FR-045 is still named by at least one task after
      any in-flight edits, using the traceability table below.

---

## Dependencies

- **Phase 1 (Setup)** → blocks everything.
- **Phase 2 (Foundational)** → blocks all user stories.
- **US1** → blocks US2 (services table, disambiguation helper, schema
  module, error parser) and provides the write-isolation gate machinery
  that US4 and US5 extend.
- **US2** → independent of US3, US4, US5 once US1 lands.
- **US3** → independent of US2, US4, US5 once Phase 2 lands. It touches
  the reservation coordinator, which US5 also touches; if both are in
  flight, US3 lands first to avoid a conflict in
  `coordinator.py`.
- **US4** → independent of US2, US3, US5 once Phase 2 lands.
- **US5** → depends on US2's message-fetch helper in
  `api/messages.py`. Do not start US5 before US2 lands.
- **US6** → depends on all of US1..US5.

Within every user story: RED PHASE COMMIT strictly precedes GREEN PHASE
COMMIT. No exceptions.

## Parallel opportunities

- Phase 1: T002..T008a are all independent fixture files.
- Phase 2: T012..T018 are independent test helpers.
- US1 red phase: T020, T021, T026, T027, T029, T030, T033, T035, T035a,
  T036, T037, T038 touch distinct files or distinct test classes.
  T038a..T038d all edit `tests/actions/test_rate_limit.py` and are NOT
  parallel with each other or with T037/T038.
- US2 red phase: T061, T062, T063, T066, T067, T068, T069, T071, T072.
  T064..T064d all edit `tests/actions/test_get_messages.py` and must be
  serialised.
- US3 red phase: T086, T089, T093, T096.
- US4 red phase: T113, T115, T117, T118, T119, T120, T121.
- US5 red phase: T132, T134, T138, T139. T136..T136d all edit
  `tests/sensor/test_messages.py` and must be serialised.
- US6: T149..T156 are independent scenario files.
- Phase 9: T164..T167 are independent documents.

Green-phase tasks that edit the SAME file are never parallel. In
particular `actions/__init__.py`, `actions/schemas.py`, `services.yaml`,
`strings.json`, `translations/en.json`, `coordinator.py`,
`api/models.py`, and `sensor/__init__.py` are each touched by several
phases and must be serialised.

## Parallel example

```text
# US1 red phase, one developer, four terminals:
uv run pytest tests/actions/test_write_client.py::test_base_has_no_post
uv run pytest tests/actions/test_rate_limit.py::test_per_reservation
uv run pytest tests/actions/test_disambiguation.py::test_two_entries
uv run pytest tests/actions/test_send_message.py::test_body_verbatim

# each with --runxfail, scoped to node ids, never bare.
```

## Implementation strategy

**MVP = Phase 1 + Phase 2 + US1.** That delivers a working
`send_message` service with rate limiting, full localisation, and all
four write-isolation gates. It is shippable on its own and every
subsequent phase builds on its infrastructure.

Recommended order after the MVP: US2 (unlocks US5 and is zero-risk,
GET-only), then US3 (highest user-visible value, isolated to the
reservation path), then US4 (fully isolated new coordinator), then US5,
then US6.

One pull request per USER STORY, six in total. Phases 1, 2, and 9 are
not separate pull requests: Phases 1 and 2 ship inside the US1 pull
request and Phase 9 ships inside the US6 pull request, as each of those
phase headers states. Each pull request is two commits minimum — red
then green — and more where a story has several red/green cycles.

---

## Notes and known gaps

These are discrepancies between the merged design artifacts and the code
that actually exists in this repository, observed while writing this
file. They are **reported, not silently reconciled**. Each one deserves
a decision before the phase that touches it starts; several may need a
documentation-fix pull request against `plan.md`, `research.md`, or
`data-model.md`.

- **The base client class is named `HospitableApiClient`, not
  `HospitableClient`.** `plan.md` §Architecture and `research.md` D-01
  originally named it `HospitableClient`, which never existed; both were
  corrected to `HospitableApiClient` during US2. The real class in
  `custom_components/hospitable/api/client.py` is `HospitableApiClient`.
  Tasks in this file use the real name. `HospitableWriteClient` is a new
  name and is unaffected.
- **The reservation UUID is published as the `reservation_id` entity
  attribute, not `reservation_uuid`.** `contracts/services.md` and D-10
  named the attribute `reservation_uuid`; `sensor/reservation.py`
  already ships it as `reservation_id`. Both documents were corrected
  during US2. The SERVICE FIELD name `reservation_uuid` is unchanged —
  only the attribute the resolver reads differs.
- **Coordinators hold the client as a private `self._client`, not a
  public `coordinator.client`.** D-01 gate 2 is written as
  `not isinstance(coordinator.client, HospitableWriteClient)` and cannot
  be written verbatim today. T022 and T023 target the attribute that
  actually exists. Adding a public read-only accessor is an acceptable
  alternative, but that is a design decision, not a silent fix.
- **This integration stores per-entry state on `entry.runtime_data`, not
  on `hass.data[DOMAIN]`.** The Hostaway reference's
  `_resolve_entry_data` helper and its unload guard
  `if not hass.data.get(DOMAIN)` therefore CANNOT be copied verbatim.
  T045 and T052 adapt the pattern by enumerating loaded config entries
  for the domain. This is the single most likely place for a
  copy-paste bug.
- **`HospitableReservation` already carries the upstream `platform`
  value, under the field name `channel`** (with `channel_confirmation`
  for `platform_id`), verified at `api/models.py:173` and its
  `from_api` construction. This is now RESOLVED: `data-model.md` no
  longer adds a duplicate `platform` field and FR-013's Airbnb check
  reads `channel`. Note `channel` is `str | None`, so a null value is
  an unresolved platform and therefore a rejection.
- **Name collision risk: `HospitableReservation.guests` already exists
  and holds NUMERIC occupancy counts.** The new guest-identity field is
  singular `guest`. These are entirely different things and are one
  character apart.
- **`HospitableListing` has only `platform` and `platform_id` — it has
  no `co_hosts`.** FR-013's `sender_id` discovery requires
  `listings[].co_hosts[].user_id`, and `contracts/services.md`'s
  `get_property_info` promises co-host data. This model extension is
  required but is NOT recorded in `data-model.md`. T051 adds it and this
  note records the documentation gap.
- **No `services.yaml` exists in `custom_components/hospitable/`, and
  `plan.md`'s module layout does not list one**, yet FR-007 and
  `contracts/services.md` require it. T053 creates it; the plan's layout
  is incomplete.
- **FR-013 needs the reservation's platform before the POST.** This is
  now RESOLVED in FR-013 itself: no lookup at all without `sender_id`;
  coordinator cache first; exactly one `GET /reservations/{uuid}` when
  uncached; `ServiceValidationError` when unresolved. T034a pins all
  four branches.
- **The awaiting-host-reply indicator is a `sensor`, not a
  `binary_sensor`.** `contracts/entities.md` states explicitly that spec
  002 introduces no new platform. This looks like a mistake to a
  reviewer and is not one.
- **"Images max 5 MB each" is not client-side enforceable.** Images are
  supplied as URIs, not uploads. T057 documents the limit; it does not
  pretend to validate it.
- **The `body` field is transmitted verbatim.** Live upstream
  documentation shows a string containing `/n` in a sentence about line
  breaks. Nothing in the merged spec-002 artifacts mentions this. This
  file takes no position on whether that is a typo for `\n`; T033
  requires only that the integration performs NO substitution of any
  kind on `body`, which is correct under either reading.
- **`tests/test_no_writes.py` currently documents itself against spec
  001's "T140, FR-059".** T058 updates the docstring to FR-001/FR-002
  while PRESERVING the file. FR-002 forbids deleting it.
- **OQ-001 and OQ-005 are UNVERIFIED and cannot be closed by this task
  list.** They can only be closed by performing a real send, which has
  NOT been performed. Specifically: the exact shape of the 202 response
  body (OQ-001) and whether the personal access token actually carries
  the send scope (OQ-005). Every task touching them requires handling
  BOTH possibilities and forbids asserting either as fact. If a reviewer
  asks for one branch to be deleted as dead code, the answer is no.
- **OQ-002 is now CLOSED — CONFIRMED-BY-TEST.** The 2026-08-12
  read-only probe established that the messages endpoint is not
  paginated. `spec.md` still lists OQ-002 as open. That is a
  documentation divergence this file is not permitted to fix; it needs
  its own documentation-fix pull request against `spec.md` and
  `research.md`. It is reported here, not silently reconciled.
- **OQ-007 is NEW and OPEN.** The confirmed GET limit and the
  documented send limit are both 2 per 60 seconds per reservation, so
  reads and writes may share ONE per-reservation bucket. If they do, a
  poll can consume budget a send needs. This cannot be tested without
  issuing a real POST to a real guest. It is not recorded in `spec.md`;
  raising it there is likewise a job for a documentation-fix pull
  request.
- **`parse_retry_after` was NOT removed and is NOT dead code.** It
  exists at `custom_components/hospitable/api/retry.py`, handles both
  the delta-seconds and HTTP-date forms, caps at `MAX_BACKOFF`, and is
  already wired into `_raise_for_status` in `api/client.py` and into
  `HospitableRateLimitError.retry_after`, which
  `coordinator._log_rate_limit_once` consumes. It does not need to be
  reintroduced. What is genuinely new is that **nothing currently reads
  the `x-ratelimit-*` family**, and that `_get` discards the
  `httpx.Response` entirely, so response headers are unreachable to
  callers today — that is the gap T047a closes.
- **The existing coordinator logs a 429 but deliberately does NOT
  reschedule**, recovering on the next scheduled poll instead. That
  behaviour is correct for the spec 001 endpoints, which never send
  `retry-after`. The messages endpoint does, so T142b gives the
  optional message fetch its own handling rather than inheriting that
  path. This is an addition, not a correction.
- **The observed non-pagination was measured against a 10-message
  thread**, the busiest on the account. Behaviour above that volume was
  not observed. T064c requires tolerating a `meta`/`links` block if one
  ever appears, without treating pagination as expected.
- **This file does not claim complete coverage of every requirement's
  every nuance.** It claims that each of FR-001 through FR-045,
  including the lettered sub-requirements, is named by at least one
  task. Depth of coverage is a judgement the reviewer should make
  independently.

---

## Requirement to task traceability

Generated by extracting the `FR-0NN` tokens appearing in the task lines
of this file. A requirement listed here has at least one task naming
it; it does not follow that the task fully discharges it.

| Requirement | Tasks |
| --- | --- |
| FR-001 | T014, T019, T022, T023, T024, T025, T058, T116, T125, T130, T146, T148, T156, T161, T171 |
| FR-002 | T025, T058, T148, T161 |
| FR-003 | T019, T020, T041 |
| FR-004 | T059 |
| FR-005 | T026, T027, T044, T052, T072, T081 |
| FR-006 | T028, T044, T052 |
| FR-007 | T016, T053, T054, T055, T073, T082, T083, T129, T145, T159, T164 |
| FR-008 | T029, T045, T154 |
| FR-009 | T010, T031, T042, T048, T149 |
| FR-010 | T033, T042, T046, T057 |
| FR-011 | T018, T031, T048, T056, T160, T164 |
| FR-012 | T007, T013, T032, T049 |
| FR-013 | T034, T048, T050, T051, T069, T079 |
| FR-014 | T033, T046, T057 |
| FR-015 | T008, T008a, T013, T035, T035a, T043 |
| FR-016 | T013, T021, T036, T041 |
| FR-017 | T013a, T013b, T037, T038, T038a, T038b, T038c, T047, T047a, T047b, T064d, T074a, T136a, T136b, T136c, T142a, T155, T155a, T166 |
| FR-018 | T017, T038a, T039, T047, T158, T166 |
| FR-019 | T013a, T037, T038, T038a, T038c, T038d, T040, T047b, T047c, T048, T064d, T074a, T136b, T136d, T142b, T155, T155a |
| FR-020 | T002, T010, T061, T066, T072, T075, T076, T149 |
| FR-021 | T062, T076 |
| FR-022 | T063, T080 |
| FR-023 | T064, T064a, T064b, T064c, T064d, T074 |
| FR-024 | T002, T015, T065, T076, T138, T153 |
| FR-025 | T067, T077, T150 |
| FR-026 | T068, T078, T150 |
| FR-027 | T069, T079, T150 |
| FR-028 | T066, T070, T077, T078, T079, T150 |
| FR-029 | T029, T045, T071, T080, T154 |
| FR-030 | T004, T008, T010, T109, T110, T111, T122, T151 |
| FR-031 | T004, T005, T112, T119, T122, T151 |
| FR-032 | T118, T119, T126, T127, T151 |
| FR-033 | T004, T113, T114, T124, T151 |
| FR-034 | T011, T116, T117, T121, T125, T128, T129 |
| FR-035 | T115, T120, T123 |
| FR-036 | T003, T132, T133, T134, T140, T143 |
| FR-037 | T003, T011, T135, T136, T136a, T136b, T136c, T136d, T137, T141, T142, T142a, T142b, T143, T145, T155a, T160, T166 |
| FR-038 | T133, T140 |
| FR-038a | T011, T135, T139, T141, T144, T145, T165 |
| FR-038b | T011, T090, T096, T102, T106, T107, T165 |
| FR-039 | T006, T085, T087, T097, T098, T099, T152 |
| FR-039a | T089, T101, T152 |
| FR-039b | T006, T086, T097, T152 |
| FR-039c | T090, T102 |
| FR-039d | T091, T103 |
| FR-039e | T092, T104 |
| FR-040 | T006, T086, T088, T097, T100 |
| FR-041 | T015, T094, T138, T153 |
| FR-042 | T092, T095, T104, T105, T120, T153 |
| FR-043 | T095, T105, T107, T153, T165 |
| FR-044 | T030, T045, T063, T080, T093, T101 |
| FR-045 | T008, T008a, T021, T029, T035, T035a, T040, T043, T111, T171 |

### Success criteria and open questions

| Item | Tasks |
| --- | --- |
| SC-001 | T149, T157 (latency: manual, not automated) |
| SC-002 | T148, T156, T161 |
| SC-003 | T153, T157 |
| SC-003a | T072a, T072b, T072c, T072d, T072e, T153a |
| SC-004 | T112, T112a, T117a, T119, T151 |
| SC-005 | T155, T155a, T158 |
| SC-006 | T154 |
| SC-007 | T150, T150a (latency: manual, not automated) |
| SC-008 | T114, T124, T151 |
| SC-009 | T152, T153 |
| All SC, final audit | T163 |
| OQ-001 (202 body shape) — OPEN | T007, T032, T049, T170 |
| OQ-002 (message pagination) — CLOSED | T064, T064a, T064b, T064c, T074 |
| OQ-005 (PAT send scope) — OPEN | T036, T170 |
| OQ-007 (shared read/write bucket) — OPEN, NEW | T038d, T047c, T074a, T136a, T142a, T142b, T170, T170a |

OQ-001, OQ-005, and OQ-007 are **UNVERIFIED**. No real send has been
performed, and none of them can be closed without one. The tasks above
require defensive handling of both possibilities; none of them may
assert an unverified answer as fact.

OQ-002 is **CLOSED — CONFIRMED-BY-TEST** by the 2026-08-12 read-only
probe: the messages endpoint is not paginated and silently ignores
`page` and `per_page`. `spec.md` has not been updated to reflect this
and still lists OQ-002 as open; correcting it is a separate
documentation-fix pull request, not this file's job.

OQ-003, OQ-004, and OQ-006 are outside the scope of this task list as
written and are not claimed to be closed by it.
