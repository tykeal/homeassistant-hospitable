# Tasks: Hospitable Home Assistant Integration

**Input**: Design documents from `/specs/001-hospitable-ha-integration/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`,
`contracts/`, `quickstart.md`

**Tests**: Test tasks are MANDATORY. Constitution Principle I
(NON-NEGOTIABLE) makes code-level TDD mandatory and Principle IX forbids
deferring unit-level TDD. Per Principle XII (Red-Phase Commit Protocol)
tests land as a red-phase commit containing tests only, with every test
marked `@pytest.mark.xfail(raises=..., reason="...", strict=True)`; the
implementation lands as a separate green-phase commit that removes those
markers and the `# type: ignore[import-not-found]` comments.

**Organization**: Tasks are grouped by user story so each story can be
implemented, tested, and shipped independently. One pull request per
user story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story the task belongs to (US1..US7)
- Exact file paths are given in every task
- Trailing parentheses list the functional requirements the task serves

## Path Conventions

Single project. Integration code lives under
`custom_components/hospitable/`, tests under `tests/`, packaging files at
the repository root. Paths follow `plan.md` §Module layout.

---

## Red/green phase protocol (read before starting any phase)

Every phase below is split into a **RED PHASE** group and a **GREEN
PHASE** group. They are separate commits. The rules are mechanical and
non-negotiable:

1. **Red-phase commit contains tests only.** No production module may be
   created or edited in it.
2. **Every red-phase test carries `raises=`.** `strict=True` alone does
   not check *why* a test failed; when `xfailed.raises is None` any
   exception raised during setup or call counts as an expected failure,
   so a test that fails for the wrong reason still passes the gate.
3. **Imports of not-yet-existing modules go inside the test body.** A
   module-level import breaks collection before any marker applies.
   `pytest.importorskip` is PROHIBITED here: it yields SKIP, which hides
   the gap instead of recording it.
4. **Deferred imports carry `# type: ignore[import-not-found]`.** Use
   `# type: ignore[attr-defined]` where the module exists but the name
   does not. `warn_unused_ignores = true` is the mypy analogue of
   `xfail_strict` and forces these to be removed at green phase.
5. **`tests/conftest.py` imports no not-yet-existing module at all.**
   Fixtures needing integration objects are factory fixtures returning a
   callable that performs its import inside its own body.
6. **Before every red-phase commit** run
   `uv run pytest --runxfail <node ids>` scoped to the new tests and
   confirm each fails with the declared exception.
7. **The green-phase commit removes the markers and the ignores in the
   same commit that adds the implementation.** `xfail_strict = true`
   turns an unexpected pass into a failure, so a forgotten marker breaks
   the build. That is the intended gate.
8. **Every commit leaves the suite green.** A clone at any commit is
   valid.

---

## Phase 1: Setup (packaging and configuration)

**Purpose**: Repository scaffolding, packaging metadata, and the test
harness configuration that the red-phase protocol depends on.

**Ships in**: the US1 pull request. This phase is a structural
divergence from `plan.md`, which describes seven phases (US1..US7) and
folds this work into US1. It is broken out here because the tasks
template requires a Setup and a Foundational phase, and because these
tasks are Principle XII **exempt** (packaging-only and
configuration-only changes) and therefore must not be forced into a
red/green pair.

- [ ] T001 Create `pyproject.toml` at the repository root with
      `[tool.pytest.ini_options]` setting `xfail_strict = true`,
      `asyncio_mode = "auto"`, and `testpaths = ["tests"]`;
      `[tool.mypy]` setting `warn_unused_ignores = true` and
      `strict = true` with no `exclude` key; a
      `[[tool.mypy.overrides]]` block for `module = "tests.*"` for any
      needed narrowing; `[tool.coverage.run]` with
      `source = ["custom_components"]`; and dev dependencies
      `pytest`, `pytest-asyncio`, `pytest-homeassistant-custom-component`,
      `respx`, `mypy`, `interrogate`. Copy the exact settings block from
      `plan.md` §Test strategy. (Principle XII exempt: config-only.)
- [ ] T002 Generate `uv.lock` from `pyproject.toml` with `uv lock` and
      commit it. `REUSE.toml` already annotates `uv.lock`.
      (Principle XII exempt: packaging-only.)
- [ ] T003 [P] Create `custom_components/hospitable/manifest.json`
      declaring `domain: hospitable`, `name: Hospitable`,
      `iot_class: cloud_polling`, `config_flow: true`,
      `integration_type: hub`, `documentation` and `issue_tracker` URLs,
      `codeowners`, `version`, a pinned `httpx` entry in `requirements`,
      and `homeassistant: "2026.8.0"` as the minimum supported Home
      Assistant version (the manifest key is `homeassistant`; there is
      no `min_ha_version` manifest key). (FR-066, FR-067)
- [ ] T004 [P] Create `hacs.json` at the repository root with `name`,
      `homeassistant` minimum `2026.8.0`, `render_readme: true`, and
      `zip_release: false`. (FR-066)
- [ ] T005 [P] Add brand assets under
      `custom_components/hospitable/brand/` (`icon.png`, `logo.png`)
      referenced by the existing CC-BY-SA-4.0 `REUSE.toml` annotation.
- [ ] T006 [P] Create `custom_components/hospitable/strings.json` and
      `custom_components/hospitable/translations/en.json` with the
      config-flow, options-flow, reauth, error, and entity-name keys
      enumerated in `contracts/config-entry.md`. All user-facing text
      says "property", never "listing"; token help text explains where
      to obtain a Personal Access Token and what scopes it needs.
      (FR-007, FR-064, FR-068)
- [ ] T007 [P] Create the package skeleton: empty
      `custom_components/hospitable/api/__init__.py`,
      `custom_components/hospitable/services/__init__.py`, and
      `custom_components/hospitable/sensor/__init__.py` so the
      three-package split exists from the first commit. `services/` here
      is DOMAIN LOGIC ONLY — this feature registers no Home Assistant
      services. (FR-069)
- [ ] T008 Add `REUSE.toml` annotations for every new path that cannot
      carry an inline SPDX header. `specs/**`,
      `custom_components/**/*.json`, `hacs.json`, `uv.lock`, and
      `custom_components/hospitable/brand/**` are already annotated;
      verify each new path is covered and add any that is not, in the
      same commit that creates the path.

---

## Phase 2: Foundational (test harness, fixtures, PII guard, probes)

**Purpose**: Everything every later phase depends on — the test package
tree, synthetic fixtures, the fixture PII pre-commit guard, and the live
probes that pin the unverified upstream assumptions.

**Ships in**: the US1 pull request.

**⚠️ CRITICAL**: No user story work can begin until this phase is
complete. In particular T019–T021 (live probes) MUST complete before the
US1 green phase, because the field bindings they pin appear in
`api/models.py`.

- [ ] T009 Create the test package tree: `tests/__init__.py`,
      `tests/api/__init__.py`, `tests/services/__init__.py`,
      `tests/sensor/__init__.py`, mirroring the reference integration's
      layout. (Principle XII exempt: test-only, asserts no behavior.)
- [ ] T010 Create `tests/conftest.py` providing the `respx` mock router,
      a synthetic-token fixture, an `enable_custom_integrations`
      autouse fixture, and factory fixtures for integration objects.
      `conftest.py` MUST NOT import any not-yet-existing module at
      module level or inside a plain fixture body that is evaluated at
      collection; factory fixtures return a callable that imports inside
      its own body.
- [ ] T011 Create `tests/helpers.py` with helpers to load a JSON fixture
      by name, build a Laravel paginator envelope, and assert that a
      captured `respx` request carries an expected query key/value.
      The query-assertion helper is the mechanism every FR-075 honored-
      request assertion uses. (FR-075)
- [ ] T012 [P] Create synthetic property fixtures under
      `tests/fixtures/`: `properties_page1.json`,
      `properties_page2.json`, `properties_single.json`. Shapes mirror
      the live API; ALL VALUES ARE SYNTHETIC. Include a `timezone` field
      holding a fixed UTC offset such as `"-0700"` (the value the
      integration must never consume), a `capacity` object, an address
      block using documentation-reserved values, and `meta.path` plus
      `links[].url` values that use `http://` so the never-follow test
      has real material. (FR-024, FR-025, FR-026, FR-027)
- [ ] T013 [P] Create synthetic reservation fixtures under
      `tests/fixtures/`: one file per status category covering all six
      — `request`, `accepted`, `cancelled`, `not accepted`, `unknown`,
      `checkpoint` — plus `reservations_page1.json` with mixed
      statuses, `reservation_missing_checkin_time.json`,
      `reservation_missing_checkout_time.json`,
      `reservation_unparsable_time.json`,
      `reservation_overlapping.json`, `reservation_owner_stay.json`,
      and `reservations_include_missing.json` (a response where the
      requested `include=properties` key is absent, to exercise
      `IncludeMissingError`). `request` and `unknown` were never
      observed in a 621-reservation census; that is absence of evidence,
      not evidence of absence, so both MUST be fixture-exercised.
      (FR-032, FR-043, FR-048, FR-075)
- [ ] T014 [P] Create the remaining synthetic fixtures under
      `tests/fixtures/`: `calendar_property.json` (aggregate across
      sales channels, with `listing_id` and `provider` present as
      cosmetic metadata only), `user.json`, `error_401.json`,
      `error_403_scope.json` (body containing
      `"Invalid scope(s) provided."`), `error_403_other.json`,
      `error_403_unparsable.txt` (a non-JSON 403 body), `error_404.json`,
      `error_429.json`, and `error_500.json`. (FR-035, FR-038, FR-058)
- [ ] T015 Add a `REUSE.toml` annotation covering `tests/fixtures/**`,
      in the SAME commit that creates that path. Fixture files are JSON
      and cannot carry an inline SPDX header, so without this the
      `reuse` pre-commit hook fails.
- [ ] T016 **RED** Create `tests/test_check_fixture_pii.py` asserting
      that `scripts/check_fixture_pii.py` flags: an email address at a
      non-documentation domain; the strings `tykeal` or `bardicgrove`;
      a bearer-token-shaped literal; latitude/longitude outside the
      synthetic box; a street address or postcode outside the allowlist;
      and any `.json` fixture located outside `tests/fixtures/`. Also
      assert the checker's output NEVER echoes the matched value, only
      file, line, and rule name. Import the module inside each test body
      with `# type: ignore[import-not-found]` and mark each test
      `@pytest.mark.xfail(raises=ModuleNotFoundError, strict=True,
      reason="TDD red phase: T016 fixture PII guard")`.
- [ ] T017 **GREEN** Implement `scripts/check_fixture_pii.py` satisfying
      T016 and remove T016's markers and type-ignores in the same
      commit. Exit non-zero listing file, line, and rule for each hit.
- [ ] T018 Register the guard in `.pre-commit-config.yaml` as a local
      hook `check-fixture-pii` with `files: ^tests/.*\.json$` plus a
      pass over the repository for stray fixtures. Confirm the
      repository-level `exclude` does not shadow it — this is why
      fixtures live in `tests/fixtures/` and NOT `tests/resources/`,
      which the existing top-level `exclude: ^tests/resources` would
      silently disable, taking `check-json` and this guard with it.
- [ ] T019 **LIVE PROBE (A-1)** Determine the reservation date-filter
      mode parameter on `GET /reservations`. `research.md` assumes
      `date_query=checkin`; this is UNVERIFIED. Issue two live requests
      differing only in that parameter against a real PAT and compare
      the returned sets. Record the outcome in `research.md` under A-1.
      **Fallback if unconfirmed or if the parameter proves to be
      silently ignored: NEVER SEND IT.** Client-side filtering of the
      returned window is authoritative in either case. This task gates
      the US1 green phase because `api/reservations.py` encodes the
      answer. (FR-030, FR-075)
- [ ] T020 **LIVE PROBE (A-2, A-3)** In the same live session, pin the
      scheduled check-in/check-out field names (A-2), the time-string
      format (A-3), and the inner key names of the `capacity` object.
      Record each in `data-model.md`'s field binding table, replacing
      the UNVERIFIED confidence marker with the observed value. Any
      binding still unconfirmed stays UNVERIFIED and its consumer MUST
      degrade to `unknown` with a warning rather than guess.
      (FR-024, FR-034)
- [ ] T021 Update `research.md` (A-1..A-3 outcomes) and `data-model.md`
      (field binding table) with the probe results, and note in
      `spec.md` any open question the probes closed. Documentation-only;
      Principle XII exempt.
- [ ] T022 Verify the red-phase machinery itself before relying on it:
      confirm `xfail_strict = true` converts an unexpected pass into a
      failure, that an `async def` test body actually executes under
      `asyncio_mode = "auto"`, and that `warn_unused_ignores = true`
      flags a stale `# type: ignore`. Record the three commands in
      `quickstart.md` so any later contributor can re-verify.

**Checkpoint**: Test harness, synthetic fixtures, PII guard, and pinned
field bindings are in place. User story work can begin.

---

## Phase 3: User Story 1 — Connect an account and pick properties (P1) 🎯 MVP

**Goal**: A manager installs the integration, pastes a Personal Access
Token, picks properties, and gets a verified connection plus one Home
Assistant device per selected property. Diagnostics, reauth, and options
all work.

**Independent Test**: Install into a clean Home Assistant, add the
integration with a valid PAT, select two properties, and confirm two
devices appear, the entry loads without error, and the diagnostics
download contains neither the token nor any personal data.

**Why it is large**: Principle VII requires the config flow to
implement the user step, a reauth flow, and an options flow at minimum;
Principle IX requires the API client layer to be delivered and proven
before dependent platforms. Recorded in `plan.md` Complexity Tracking.

**Coordinator wiring (preserve this distinction)**: all three
coordinator CLASSES ship and are tested in US1, but
`async_setup_entry` INSTANTIATES ONLY the properties coordinator.
Reservations wire in US2, calendar in US7. Instantiating all three now
would ship a release spending roughly 1,700 requests per day rendering
nothing.

### Tests for User Story 1 (RED-PHASE COMMIT) ⚠️

> Tests only. Every test `@pytest.mark.xfail(raises=..., strict=True,
> reason="TDD red phase: T0NN <behavior>")`, imports deferred into the
> test body with `# type: ignore[import-not-found]`. Run
> `uv run pytest --runxfail <new node ids>` before committing.

- [ ] T023 [P] [US1] `tests/api/test_const.py`: assert a single base URL
      constant `https://public.api.hospitable.com/v2`, that no other
      host or API version literal exists in the package, and that
      endpoint path constants exist for `/user`, `/properties`,
      `/reservations`, and `/properties/{id}/calendar`.
      (FR-001, FR-002)
- [ ] T024 [P] [US1] `tests/api/test_exceptions.py`: assert the
      hierarchy from `contracts/errors-and-diagnostics.md` —
      `HospitableError` base carrying status, endpoint, and a redacted
      body excerpt, with subclasses `HospitableAuthError` (401),
      `HospitableScopeError` (403 scope), `HospitableForbiddenError`
      (403 other), `HospitableNotFoundError` (404),
      `HospitableRateLimitError` (429, carrying `retry_after`),
      `HospitableConnectionError` (transport and 5xx), and
      `HospitableResponseError` (shape) with subclass
      `HospitableIncludeMissingError`. (FR-035)
- [ ] T025 [P] [US1] `tests/api/test_auth.py`: assert the credential
      interface sets `Authorization: Bearer <token>` on every request,
      that the token is never placed in a query string or logged, and
      that the interface takes a token provider rather than a bare
      string so an OAuth provider could be substituted later without a
      call-site change. Assert no OAuth credential type is accepted
      today. (FR-001, FR-003, FR-005, FR-008)
- [ ] T026 [P] [US1] `tests/api/test_client_403.py`: assert the 403
      classifier parses the body and takes `reason_phrase`, else
      `message`, else `error`; that a case-insensitive `scope`
      substring yields `HospitableScopeError`; and that EVERY other
      case — absent body, empty body, non-JSON body
      (`error_403_unparsable.txt`), unrecognized shape — defaults to
      `HospitableForbiddenError`. Assert neither branch triggers
      reauth. (FR-038)
- [ ] T027 [P] [US1] `tests/api/test_pagination.py`: register a `respx`
      route matching `http://` (non-TLS) to ANY Hospitable host whose
      side effect RAISES, so following an upstream-supplied
      `links[].url` or `meta.path` verbatim fails the test loudly.
      Assert the client constructs each page request itself from
      `page` and `per_page`, asserts the echoed `meta.current_page`
      matches what was requested, stops at `meta.last_page`, and caps
      `per_page` at 100. (FR-025, FR-026, FR-027, FR-075)
- [ ] T028 [P] [US1] `tests/api/test_retry.py`: assert HTTP 429 is
      authoritative and its `Retry-After` is honored when present;
      that `X-RateLimit-*` headers are read if present but that their
      absence changes nothing and no code path depends on them; that
      retries are bounded with jittered backoff; and that exhausting
      retries raises rather than looping. (FR-036, FR-037)
- [ ] T029 [P] [US1] `tests/api/test_redaction.py`: assert the token,
      any bearer-shaped string, and every personal field are redacted
      from exception text, log records, and body excerpts. (FR-006)
- [ ] T030 [P] [US1] `tests/api/test_responses.py`: assert the shape
      validator rejects a missing or mistyped envelope; and assert the
      FR-075 honored-request register — `include=listings` on
      `/properties` and `include=properties` on `/reservations` are
      SENT and their keys ASSERTED present in the response, raising
      `HospitableIncludeMissingError` otherwise
      (`reservations_include_missing.json`); `page`/`per_page` are sent
      and `meta.current_page` asserted; `properties[]` is sent and
      returned membership asserted; `start_date`/`end_date` are sent and
      the window re-filtered locally. Assert that `include=guests`, any
      other include, a calendar `listing_id`, and `status[]` are NEVER
      SENT. HTTP 200 is not proof a parameter was honored.
      (FR-033, FR-034, FR-075)
- [ ] T031 [P] [US1] `tests/api/test_models.py`: assert models parse the
      synthetic fixtures; that money is retained as INTEGER MINOR UNITS
      alongside `currency` and `formatted`; that personal fields are
      dropped at the model boundary so they cannot reach an entity, a
      log, or diagnostics; that `ical_imports` and channel data are
      discarded; and the **D-11 regression guard** —
      `HospitableProperty` has NO `timezone` attribute at all, so the
      fixed UTC offset upstream publishes cannot be consumed by
      accident. (FR-024, FR-039, FR-062, FR-073)
- [ ] T032 [P] [US1] `tests/api/test_properties.py`: assert
      `GET /properties` pages correctly, sends `include=listings` and
      asserts the key, and returns models keyed by `property_id`.
      (FR-025, FR-075)
- [ ] T033 [P] [US1] `tests/api/test_reservations.py`: assert
      `GET /reservations` ALWAYS sends `properties[]` and
      `start_date`/`end_date`; that property IDs are batched at no more
      than fifty per request; that the A-1 date-filter mode parameter
      is sent only if T019 confirmed it and is otherwise absent; and
      that the returned window is re-filtered client-side regardless,
      so correctness never depends on the parameter.
      (FR-028, FR-029, FR-030, FR-031)
- [ ] T034 [P] [US1] `tests/api/test_client_methods.py`: assert every
      client entry point is `async`, that the client exposes no
      method issuing a non-`GET` request, that it uses
      `homeassistant.helpers.httpx_client.get_async_client`, and that
      no TLS-verification-disabling option exists. (FR-027, FR-040)
- [ ] T035 [P] [US1] `tests/services/test_window.py`: assert the
      reservation window defaults to 90 days back and 90 forward, that
      lookback accepts 7–365 and lookahead 1–730, and that
      out-of-bounds values are rejected with a message naming the
      bound. (FR-021, FR-022)
- [ ] T036 [P] [US1] `tests/services/test_timezones.py`: assert the
      effective zone defaults to the Home Assistant instance timezone;
      that a per-property override must be a valid IANA name and is
      rejected otherwise; that lookups go through
      `dt_util.async_get_time_zone` and NEVER a bare `ZoneInfo(...)`
      (a Principle VIII blocking-call violation); and that the upstream
      `property.timezone` fixed offset is never consulted.
      (FR-040, FR-074)
- [ ] T037 [P] [US1] `tests/services/test_estimator.py`: assert the
      request estimate formula from `contracts/config-entry.md` and
      that ten properties at default intervals with 500 reservations
      yields exactly **1,704** requests per day (24 property + 240
      calendar + 1,440 reservation), under SC-004's 2,000 ceiling.
      (FR-072)
- [ ] T038 [P] [US1] `tests/test_coordinator.py`: assert three distinct
      coordinator classes exist — reservations, properties, calendar —
      each keying its data by `property_id`; that reservations defaults
      to 5 minutes with a 1-minute floor and properties and calendar
      default to 60 minutes with a 15-minute floor; that the calendar
      coordinator is SEPARATE from the properties coordinator so its
      N-per-property fan-out cannot delay the single cheap properties
      call; and that one coordinator's failure does not fail the
      others. (FR-019, FR-020, FR-071)
- [ ] T039 [P] [US1] `tests/test_entity.py`: assert the FROZEN unique-ID
      format `f"{account_namespace}_{property_id}_{entity_key}"`; that
      it derives solely from account-stable and property-stable values
      and never from a name; that `suggested_object_id` is
      `f"hospitable_{slugify(property.name)}_{key}"`; and that exactly
      one device is created per selected property.
      (FR-050, FR-054, FR-055)
- [ ] T040 [P] [US1] `tests/test_init.py`: assert `async_setup_entry`
      instantiates ONLY the properties coordinator in US1 (a positive
      assertion that the reservations and calendar coordinators are
      NOT instantiated); that no Home Assistant platform is forwarded
      during US1; that `async_unload_entry` tears down every HTTP
      client, listener, and coordinator; that `async_migrate_entry`
      exists with `VERSION = 1` and `MINOR_VERSION = 1`; and that a
      setup failure never fails silently.
      (FR-041, FR-065, FR-070, FR-071)
- [ ] T041 [P] [US1] `tests/test_config_flow.py`: assert the `user` step
      validates the token with `GET /user` and stores `token`,
      `account_namespace`, and `namespace_source` in `entry.data`; the
      `properties` step lists properties by name and requires at least
      one; a second entry for the same account UUID is aborted as
      already configured while a different account is allowed; the
      `reauth_confirm` step replaces the token and ABORTS if the new
      token belongs to a different account; and the options flow
      exposes selected properties, both intervals, lookback,
      lookahead, and timezone overrides with bound validation.
      (FR-004, FR-009, FR-010, FR-011, FR-012, FR-013, FR-014,
      FR-015, FR-016)
- [ ] T042 [P] [US1] `tests/test_diagnostics.py`: assert the diagnostics
      dump is built from an ALLOWLIST, contains the entry skeleton,
      option values, coordinator health, and last-error classification,
      and contains no token, no guest name, no email, no phone, and no
      address. (FR-063)
- [ ] T043 [P] [US1] `tests/test_privacy.py`: the SC-008 audit — sweep
      diagnostics output, DEBUG-level log records, and every exception
      string for token material and personal data across a full
      simulated lifecycle. Assert `/channels` is never called.
      (FR-006, FR-062, FR-073)
- [ ] T044 [P] [US1] `tests/test_terminology.py`: assert every
      user-facing string in `strings.json` and `translations/en.json`
      uses "property" and never "listing", except where `listings` is
      the literal name of an upstream attribute. (FR-068)
- [ ] T045 [P] [US1] `tests/test_polling_only.py`: assert the package
      contains no webhook registration, no inbound HTTP view, and no
      push subscription — the integration functions entirely by
      polling and `manifest.json` declares `cloud_polling`.
      (FR-067)
- [ ] T046 [US1] Run `uv run pytest --runxfail` scoped to the node IDs
      added in T023–T045 and confirm each fails with the exception
      named in its `raises=`. Fix any test that fails for a different
      reason, then commit the red phase (tests only).

### Implementation for User Story 1 (GREEN-PHASE COMMIT)

> Each green task removes the `xfail` markers and
> `# type: ignore[...]` comments belonging to the tests it satisfies,
> in the same commit as the implementation.

- [ ] T047 [P] [US1] Implement `custom_components/hospitable/api/const.py`
      — base URL, API version, endpoint paths, timeouts, `per_page`
      ceiling of 100, batch ceiling of 50. Satisfies T023.
      (FR-001, FR-002, FR-031)
- [ ] T048 [P] [US1] Implement
      `custom_components/hospitable/api/exceptions.py`. Satisfies T024.
      (FR-035)
- [ ] T049 [P] [US1] Implement `custom_components/hospitable/api/auth.py`
      — a token-provider interface that does not preclude OAuth.
      Satisfies T025. (FR-001, FR-003, FR-005, FR-008)
- [ ] T050 [P] [US1] Implement
      `custom_components/hospitable/api/redaction.py`. Satisfies T029.
      (FR-006)
- [ ] T051 [P] [US1] Implement `custom_components/hospitable/api/retry.py`.
      Satisfies T028. (FR-036, FR-037)
- [ ] T052 [US1] Implement
      `custom_components/hospitable/api/responses.py` — envelope
      validation plus the FR-075 honored-request assertions. Satisfies
      T030. (FR-034, FR-075)
- [ ] T053 [US1] Implement `custom_components/hospitable/api/models.py`
      — property, reservation, calendar day, money, and user models;
      personal fields dropped at the boundary; NO `timezone` attribute
      on the property model. Satisfies T031.
      (FR-024, FR-039, FR-060, FR-062, FR-073)
- [ ] T054 [US1] Implement `custom_components/hospitable/api/client.py`
      — `get_async_client`-backed transport, GET-only surface,
      self-constructed pagination that never follows an upstream URL,
      and the 403 classifier defaulting to the non-scope branch.
      Satisfies T026, T027, T034.
      (FR-025, FR-026, FR-027, FR-038, FR-040)
- [ ] T055 [P] [US1] Implement
      `custom_components/hospitable/api/properties.py`. Satisfies T032.
      (FR-025, FR-075)
- [ ] T056 [P] [US1] Implement
      `custom_components/hospitable/api/reservations.py` — mandatory
      `properties[]` and date filters, 50-ID batching, the A-1
      parameter per T019's outcome, and authoritative client-side
      re-filtering. Satisfies T033.
      (FR-028, FR-029, FR-030, FR-031, FR-032)
- [ ] T057 [P] [US1] Implement
      `custom_components/hospitable/services/window.py`. Satisfies
      T035. (FR-021, FR-022)
- [ ] T058 [P] [US1] Implement
      `custom_components/hospitable/services/timezones.py` — instance
      default, validated IANA override, `dt_util.async_get_time_zone`
      only. Satisfies T036. (FR-040, FR-074)
- [ ] T059 [P] [US1] Implement
      `custom_components/hospitable/services/estimator.py`. Satisfies
      T037. (FR-072)
- [ ] T060 [US1] Implement `custom_components/hospitable/const.py` —
      domain, platforms (`SENSOR` only), interval defaults and floors,
      window defaults and bounds, option keys, `VERSION`,
      `MINOR_VERSION`. (FR-019, FR-020, FR-021, FR-070)
- [ ] T061 [US1] Implement `custom_components/hospitable/coordinator.py`
      — all three coordinator classes with independent intervals and
      isolated failure handling. Satisfies T038.
      (FR-019, FR-020, FR-071)
- [ ] T062 [US1] Implement `custom_components/hospitable/entity.py` —
      base entity, device construction, frozen unique ID,
      `suggested_object_id`, and an explicit
      `device_registry.async_get_or_create` call for each selected
      property so US1 creates devices without sensor entities.
      Satisfies T039.
      (FR-050, FR-054, FR-055)
- [ ] T063 [US1] Implement `custom_components/hospitable/config_flow.py`
      — `user`, `properties`, `reauth_confirm`, and options steps with
      bound validation. Satisfies T041.
      (FR-004, FR-007, FR-009 to FR-016)
- [ ] T064 [P] [US1] Implement
      `custom_components/hospitable/diagnostics.py` — allowlist-based.
      Satisfies T042, and contributes to T043. (FR-063)
- [ ] T065 [US1] Implement `custom_components/hospitable/__init__.py` —
      `async_setup_entry` instantiating ONLY the properties
      coordinator, `async_unload_entry` teardown,
      `async_migrate_entry`, and the options update listener
      registration. Satisfies T040.
      (FR-041, FR-065, FR-067, FR-070, FR-071)
- [ ] T066 [US1] Finalize `strings.json` and `translations/en.json`
      against the implemented flow, keeping every message actionable
      and every noun "property". Satisfies T044, T045.
      (FR-007, FR-064, FR-067, FR-068)
- [ ] T067 [US1] Sweep the diff: confirm ZERO `xfail` markers and ZERO
      `# type: ignore[import-not-found]` comments remain for
      T023–T045, then run the full suite plus
      `uv run mypy custom_components tests` and confirm both are green.
- [ ] T068 [US1] Walk the US1 rows of `quickstart.md` against a live
      Home Assistant instance and record the outcome. Confirm the exit
      criteria below.

**Exit criteria (US1)**: full CI green; one device per selected
property; the `http://` guard test passing; the scope-403 classifier
tested including the unparsable-body default; a diagnostics dump
containing no token and no personal data; the PII guard proven to fail
on a deliberately poisoned fixture; A-1 resolved (or explicitly falling
back to never sending the parameter) and the field-binding table
updated.

**Independently shippable because**: a manager can install it, paste a
token, pick properties, and get a verified connection plus devices.
Nothing later is required for that value.

**Checkpoint**: US1 complete and shippable.

---

## Phase 4: User Story 2 — Reservation status per property (P2)

**Goal**: Exactly one enum reservation sensor per property — never one
per reservation — that automations can trigger on.

**Independent Test**: With US1 installed, confirm each selected property
gains a single reservation status sensor whose state moves through
`awaiting_checkin`, `occupied`, and `checked_out` at the scheduled
times, and that a property with no reservation reads `no_reservation`
while remaining available.

### Tests for User Story 2 (RED-PHASE COMMIT) ⚠️

> Tests only, `xfail(raises=..., strict=True)`, deferred imports.

- [ ] T069 [P] [US2] `tests/services/test_status.py`: assert all six
      upstream status categories map explicitly — `request` →
      `pending_request`, `accepted` → an occupancy-derived state,
      `cancelled` → `cancelled`, `not accepted` → `not_accepted`,
      `unknown` → `unknown`, `checkpoint` → `checkpoint`. Assert
      `checkpoint` does NOT reach the unrecognized fallback. Assert an
      unrecognized status maps to `unknown` and is logged ONCE without
      raising. Assert status is read from the structured status path
      only, never a deprecated flat field.
      (FR-032, FR-043, FR-048)
- [ ] T070 [P] [US2] `tests/services/test_occupancy.py`: assert
      transitions happen at STRICT SCHEDULED TIMES in the property's
      effective IANA zone. Three boundary cases: a missing check-in
      time, a missing check-out time, and an unparsable time — each
      yields `unknown` plus a warning naming the reservation and the
      field, degraded ONLY on the two boundary dates. **Assert
      `unknown` POSITIVELY**, never merely "not occupied":
      `awaiting_checkin` satisfies the weaker assertion and IS the
      midnight-fallback bug this test exists to prevent. Assert NO
      midnight fallback exists anywhere. (FR-045, FR-047, FR-074)
- [ ] T071 [P] [US2] `tests/services/test_selection.py`: assert that
      when a property has more than one reservation in the window the
      chosen one is deterministic across repeated refreshes and across
      input ordering, and that the documented tie-break is applied.
      (FR-044)
- [ ] T072 [P] [US2] `tests/sensor/test_reservation.py`: assert exactly
      one reservation sensor per property; that its state is one of
      the nine enum options `no_reservation`, `awaiting_checkin`,
      `occupied`, `checked_out`, `pending_request`, `checkpoint`,
      `cancelled`, `not_accepted`, `unknown`; that `unavailable` is
      NEVER an enum option; and that no second dimension (such as
      availability) is folded into this single-dimensional enum.
      (FR-042, FR-043, FR-058)
- [ ] T073 [P] [US2] `tests/sensor/test_reservation_attributes.py`:
      assert the attribute contract from `contracts/entities.md` —
      guest COUNTS only (never names or contact details), scheduled
      check-in and check-out, reservation identifier, stay type, and
      the effective timezone. Assert no personal data appears in any
      attribute. (FR-046, FR-049, FR-062, FR-073)
- [ ] T074 [P] [US2] `tests/sensor/test_availability_mixin.py`: assert
      the custom availability mixin keeps the last known state and
      stays AVAILABLE after one and after two consecutive poll
      failures, becoming unavailable only on the THIRD. Home
      Assistant's stock `CoordinatorEntity.available` returns
      `last_update_success` and would go unavailable after one
      failure, so a custom mixin is required. (FR-057)
- [ ] T075 [P] [US2] `tests/sensor/test_no_reservation.py`: the SC-012
      assertion — a property with no reservation in the window reads
      `no_reservation` and its entity remains AVAILABLE. (FR-042)
- [ ] T076 [P] [US2] `tests/services/test_owner_stay.py`: assert an
      owner or maintenance stay is classified consistently with a
      guest stay for occupancy purposes and is distinguished by the
      stay-type attribute rather than by the enum state. (FR-049)
- [ ] T077 [US2] Extend `tests/test_init.py`: assert
      `async_setup_entry` now instantiates the reservations coordinator
      IN ADDITION to the properties coordinator, and still does NOT
      instantiate the calendar coordinator. (FR-071)
- [ ] T078 [US2] Run `uv run pytest --runxfail` scoped to T069–T077,
      confirm each fails for its declared reason, then commit the red
      phase.

### Implementation for User Story 2 (GREEN-PHASE COMMIT)

- [ ] T079 [P] [US2] Implement
      `custom_components/hospitable/services/status.py`. Satisfies
      T069. (FR-032, FR-043, FR-048)
- [ ] T080 [P] [US2] Implement
      `custom_components/hospitable/services/occupancy.py` — strict
      scheduled moments, `unknown` plus a warning on a missing or
      unparsable boundary time, no midnight fallback. Satisfies T070,
      T076. (FR-045, FR-047, FR-049, FR-074)
- [ ] T081 [P] [US2] Implement
      `custom_components/hospitable/services/selection.py`. Satisfies
      T071. (FR-044)
- [ ] T082 [US2] Implement
      `custom_components/hospitable/sensor/__init__.py` (platform setup
      and entity creation) and
      `custom_components/hospitable/sensor/helpers.py` (shared
      attribute and state helpers, including the single money
      minor-unit-to-float conversion point). US3, US4, and US7 require
      this module; if any ships before US2, pull this task forward into
      that phase. (FR-042, FR-060)
- [ ] T083 [US2] Implement the three-strike availability mixin in
      `custom_components/hospitable/entity.py`. Satisfies T074.
      (FR-057)
- [ ] T084 [US2] Implement
      `custom_components/hospitable/sensor/reservation.py`. Satisfies
      T072, T073, T075.
      (FR-042, FR-043, FR-046, FR-049, FR-062, FR-073)
- [ ] T085 [US2] Wire the reservations coordinator into
      `async_setup_entry` in `custom_components/hospitable/__init__.py`,
      and forward the sensor platform after
      `sensor/__init__.py` exists. Satisfies T077.
      (FR-071)
- [ ] T086 [US2] Add the reservation sensor's entity name and enum
      state translations to `strings.json` and `translations/en.json`,
      using "property" throughout. (FR-064, FR-068)
- [ ] T087 [US2] Sweep the diff for leftover `xfail` markers and
      type-ignores from T069–T077; run the full suite and mypy.
- [ ] T088 [US2] Walk the US2 rows of `quickstart.md` and record the
      outcome.

**Exit criteria (US2)**: every US2 acceptance scenario passing,
including all three occupancy boundary cases and the positive `unknown`
assertion; deterministic selection proven across repeated refreshes;
unknown statuses logged once without raising; `no_reservation` reported
while available.

**Independently shippable because**: it delivers the integration's core
value — one automatable enum sensor per property. It needs nothing from
US3 through US7.

**Checkpoint**: US1 and US2 both work independently.

---

## Phase 5: User Story 3 — Property details as entities (P3)

**Goal**: Next-arrival, next-departure, upcoming-reservation count, and
property-information sensors, plus correct handling of a property that
disappears from the account.

**Independent Test**: With US1 installed, confirm each property gains
the four detail sensors with correct timestamps in the property's
effective timezone, and that removing a property upstream marks its
entities unavailable without deleting them.

**Dependency note**: US3 depends on US1 but NOT on US2 — the
specification says so explicitly.

### Tests for User Story 3 (RED-PHASE COMMIT) ⚠️

- [ ] T089 [P] [US3] `tests/sensor/test_property_timestamps.py`: assert
      `next_arrival` and `next_departure` are timestamp sensors
      rendered in the property's effective IANA timezone, and that a
      property with no upcoming reservation reports `unknown` rather
      than a sentinel date. (FR-051)
- [ ] T090 [P] [US3] `tests/sensor/test_upcoming_count.py`: assert the
      upcoming-reservation count sensor counts only reservations in
      the configured forward window and only those in a status that
      represents a real forthcoming stay. (FR-052)
- [ ] T091 [P] [US3] `tests/sensor/test_property_info.py`: assert the
      property-information sensor exposes the attributes named in
      `contracts/entities.md` — name, capacity fields, listing
      references, and the effective timezone — and NO address, no
      coordinates, and no owner contact details. (FR-053, FR-062)
- [ ] T092 [P] [US3] `tests/sensor/test_rename_stability.py`: assert
      renaming a property upstream changes the display name but leaves
      the unique ID and therefore the entity registry entry and its
      recorded history intact. (FR-054, FR-055)
- [ ] T093 [P] [US3] `tests/sensor/test_disappeared_property.py`:
      assert that when a monitored property disappears from the
      account its entities become unavailable, its registry entries
      and history are RETAINED, and a single explanatory warning is
      logged. (FR-056)
- [ ] T094 [P] [US3] `tests/services/test_timezone_override.py`: assert
      a per-property IANA override changes rendered timestamps; that
      `effective_timezone` and `timezone_source` attributes report the
      zone in use and whether it came from the instance default or an
      override; that an invalid IANA name is rejected at the options
      step; and the **D-11 guard at the sensor layer** — no sensor
      reads any upstream `timezone` value. (FR-074)
- [ ] T095 [US3] Run `uv run pytest --runxfail` scoped to T089–T094 and
      commit the red phase.

### Implementation for User Story 3 (GREEN-PHASE COMMIT)

- [ ] T096 [US3] Implement
      `custom_components/hospitable/sensor/property.py` —
      `next_arrival`, `next_departure`, `upcoming_reservations`, and
      `property_info`. Satisfies T089, T090, T091.
      (FR-051, FR-052, FR-053)
- [ ] T097 [US3] Implement the disappeared-property path in
      `custom_components/hospitable/coordinator.py` and
      `entity.py` — unavailable, retained, warned once. Satisfies
      T093. Note this shares its mechanism with FR-018 non-destructive
      deselection, completed in US4. (FR-056)
- [ ] T098 [US3] Surface `effective_timezone` and `timezone_source` on
      the relevant entities and apply the per-property override
      throughout the sensor layer. Satisfies T092, T094.
      (FR-054, FR-055, FR-074)
- [ ] T099 [US3] Add property sensor names to `strings.json` and
      `translations/en.json`. (FR-064, FR-068)
- [ ] T100 [US3] **OQ-004 verification**: check whether reservations
      exist against listings that are not surfaced as properties. The
      detection signal is the availability sensor and the reservation
      sensor disagreeing for the same property. Record the finding in
      `spec.md` under OQ-004 and, if confirmed, document the limitation
      in the README (task T149). This is a verification and
      documentation task, not a behavior change.
- [ ] T101 [US3] Sweep the diff for leftover markers and type-ignores
      from T089–T094; run the suite and mypy.
- [ ] T102 [US3] Walk the US3 rows of `quickstart.md` and record the
      outcome.

**Exit criteria (US3)**: every US3 acceptance scenario passing; the
D-11 regression guard asserting the model has no `timezone` attribute
still green; the OQ-004 verification performed and, if confirmed,
documented.

**Independently shippable because**: dashboards and schedule-driven
automations become possible without any US2 entity.

**Checkpoint**: US1, US2, and US3 all work independently.

---

## Phase 6: User Story 4 — Cadence and window control (P4)

**Goal**: Turn fixed defaults into a supported tuning surface —
intervals, window, and property selection editable without a restart,
with a visible request estimate.

**Independent Test**: Change the reservation interval and the lookback
in the options flow and confirm the change takes effect without
restarting Home Assistant, that the displayed request estimate updates,
and that deselecting a property stops its polling without deleting its
entities.

### Tests for User Story 4 (RED-PHASE COMMIT) ⚠️

- [ ] T103 [P] [US4] `tests/test_options_reload.py`: assert the update
      listener reloads the entry so that a changed interval, window, or
      property selection takes effect with NO Home Assistant restart
      (SC-011). (FR-017)
- [ ] T104 [P] [US4] `tests/test_options_bounds.py`: assert every
      option is validated against its stated bound and that an
      out-of-range value produces a message NAMING the bound — the
      reservation interval floor of 1 minute, the property and calendar
      floor of 15 minutes, lookback 7–365, lookahead 1–730 — and never
      a bare validation code. (FR-016, FR-022, FR-064)
- [ ] T105 [P] [US4] `tests/test_options_estimate.py`: assert the
      options screen displays the estimated daily request count, that
      it is clearly LABELLED an estimate, and that it recomputes as the
      user changes intervals or selection. (FR-072)
- [ ] T106 [P] [US4] `tests/test_options_help_text.py`: assert the
      user-facing help text documents the trade-off between a shorter
      interval or a wider window and upstream request volume.
      (FR-023)
- [ ] T107 [P] [US4] `tests/test_deselection.py`: assert deselecting a
      property STOPS polling it, marks its entities unavailable, and
      RETAINS its registry entries and recorded history; and that
      reselecting it resumes polling against the SAME unique IDs so
      history is continuous in both directions. (FR-018, FR-055)
- [ ] T108 [P] [US4] `tests/test_interval_defaults.py`: assert the
      shipped defaults are 5 minutes for reservations and 60 minutes
      for properties and calendar, and that the reservation window
      defaults to 90 days back and 90 forward.
      (FR-019, FR-020, FR-021)
- [ ] T109 [US4] Run `uv run pytest --runxfail` scoped to T103–T108 and
      commit the red phase.

### Implementation for User Story 4 (GREEN-PHASE COMMIT)

- [ ] T110 [US4] Implement the options update listener and reload in
      `custom_components/hospitable/__init__.py`. Satisfies T103.
      (FR-017)
- [ ] T111 [US4] Complete the options-flow schema, bound validation
      messages, and help text in
      `custom_components/hospitable/config_flow.py`. Satisfies T104,
      T106, T108. (FR-016, FR-019 to FR-023, FR-064)
- [ ] T112 [US4] Render the `services/estimator.py` result on the
      options screen with an explicit "estimate" label. Satisfies
      T105. (FR-072)
- [ ] T113 [US4] Implement non-destructive deselection and reselection
      across `coordinator.py`, `entity.py`, and `sensor/__init__.py`,
      reusing the FR-056 mechanism. Satisfies T107. (FR-018)
- [ ] T114 [US4] Add the options-flow labels, help text, and error
      strings to `strings.json` and `translations/en.json`.
      (FR-023, FR-064, FR-068)
- [ ] T115 [US4] Sweep the diff for leftover markers and type-ignores
      from T103–T108; run the suite and mypy.
- [ ] T116 [US4] Walk the US4 rows of `quickstart.md` and record the
      outcome.

**Exit criteria (US4)**: option changes take effect with no restart;
the estimate reports 1,704 for ten properties at defaults with 500
reservations; deselection and reselection preserve identifiers and
history in both directions.

**Independently shippable because**: it converts fixed defaults into a
tuning surface that keeps the integration safe for a large portfolio.
Nothing later depends on it.

**Checkpoint**: US1–US4 all work independently.

---

## Phase 7: User Story 5 — Multiple accounts side by side (P5)

**Goal**: Evidence for SC-010's zero-collision guarantee across multiple
config entries.

**Independent Test**: Add five config entries for five different
Hospitable accounts, including two accounts owning identically named
properties, and confirm zero unique-ID collisions and full isolation.

**Honest characterization**: most of this behavior is proven BY
CONSTRUCTION in US1's namespacing, so this phase may be predominantly
tests. Test-only strengthening that asserts no new production behavior
is EXEMPT from the red-phase protocol (Principle XII, Exemptions). Any
behavior change the evidence uncovers is NOT exempt and gets its own
red phase — T122 is the template for that.

### Tests for User Story 5

- [ ] T117 [P] [US5] `tests/test_multi_entry.py`: set up FIVE config
      entries with distinct account namespaces and assert zero
      unique-ID collisions across the entity registry (SC-010).
      (FR-012, FR-055)
- [ ] T118 [P] [US5] `tests/test_multi_entry_naming.py`: assert two
      accounts owning identically named properties produce distinct
      unique IDs, distinct devices, and distinct suggested entity IDs.
      (FR-054, FR-055)
- [ ] T119 [P] [US5] `tests/test_multi_entry_isolation.py`: assert one
      entry's authentication failure, rate-limit response, or poll
      failure does not disturb another entry's coordinators or
      entities. (FR-012)
- [ ] T120 [P] [US5] `tests/test_duplicate_account.py`: assert adding a
      second entry for an account already configured is ABORTED with
      an actionable message, while a different account is accepted.
      (FR-013)
- [ ] T121 [P] [US5] `tests/test_reauth_account_match.py`: assert a
      reauth whose new token belongs to a DIFFERENT account is
      aborted rather than silently re-pointing the entry at another
      account. (FR-013, FR-014)
- [ ] T122 [US5] **Conditional red phase.** If any of T117–T121
      uncovers a genuine behavior gap rather than merely documenting
      existing behavior, convert the failing assertion into a proper
      red-phase commit — `xfail(raises=..., strict=True)`, deferred
      import, tests only — and pair it with a green-phase commit that
      fixes the behavior and removes the marker. If nothing is
      uncovered, record that explicitly in the PR body rather than
      leaving the reader to infer it.

**Exit criteria (US5)**: five entries with zero unique-ID collisions;
identically named properties across two accounts colliding nowhere; one
entry's auth failure not disturbing another.

**Independently shippable because**: it delivers the evidence for a
stated success criterion. An unevidenced guarantee is not a guarantee.

**Checkpoint**: multi-account behavior evidenced.

---

## Phase 8: User Story 6 — Token expiry and recovery (P6)

**Goal**: Failures are surfaced honestly — a credential problem prompts
reauth, a capability limit does not.

**Independent Test**: Revoke the token and confirm an actionable reauth
prompt appears within one polling interval; then trigger a scope-403
and confirm it produces neither a reauth prompt nor a repair issue.

### Tests for User Story 6 (RED-PHASE COMMIT) ⚠️

- [ ] T123 [P] [US6] `tests/test_reauth_trigger.py`: assert HTTP 401
      triggers the Home Assistant reauth flow within one polling
      interval and that the prompt names the account. (FR-014, FR-064)
- [ ] T124 [P] [US6] `tests/test_scope_403_handling.py`: assert a
      scope-403 (for example `/reservations/{id}/enrichment` returning
      `"Invalid scope(s) provided."` on a PAT) produces NO reauth and
      NO repair issue, is surfaced as a capability limitation, and is
      logged once. A scope-403 IS NOT an authentication failure.
      (FR-038, FR-065)
- [ ] T125 [P] [US6] `tests/test_non_scope_403_handling.py`: assert a
      403 that is NOT scope-related produces a repair issue explaining
      the access problem, and still no reauth. (FR-038, FR-065)
- [ ] T126 [P] [US6] `tests/test_403_unparsable_default.py`: assert a
      403 whose body is absent, empty, or non-JSON lands on the
      NON-SCOPE branch. Defaulting to the scope branch would silently
      suppress a real access problem. (FR-038)
- [ ] T127 [P] [US6] `tests/test_persistent_failure_repair.py`: assert
      a persistent non-credential failure raises a repair issue rather
      than failing silently, and that the entry does not silently
      remain in a broken state. (FR-065)
- [ ] T128 [P] [US6] `tests/test_error_message_quality.py`: audit
      EVERY user-facing string produced by the error paths and assert
      each states what failed AND what the user can do. Assert no
      user-facing message is a bare HTTP status code or an unmapped
      exception repr. (FR-064)
- [ ] T129 [P] [US6] `tests/test_setup_failure_visibility.py`: assert a
      config entry never fails silently — setup failure surfaces as
      `ConfigEntryAuthFailed`, `ConfigEntryNotReady`, or a repair
      issue as appropriate. (FR-065)
- [ ] T130 [US6] Run `uv run pytest --runxfail` scoped to T123–T129 and
      commit the red phase.

### Implementation for User Story 6 (GREEN-PHASE COMMIT)

- [ ] T131 [US6] Implement the error-to-outcome mapping from
      `contracts/errors-and-diagnostics.md` in
      `custom_components/hospitable/coordinator.py` and
      `__init__.py` — 401 to reauth, scope-403 to a logged capability
      limitation, other 403 to a repair issue, persistent failure to a
      repair issue. Satisfies T123, T124, T125, T127, T129.
      (FR-038, FR-064, FR-065)
- [ ] T132 [US6] Confirm and, if needed, harden the 403 classifier
      default in `custom_components/hospitable/api/client.py`.
      Satisfies T126. (FR-038)
- [ ] T133 [US6] Add every reauth, repair-issue, and error string to
      `strings.json` and `translations/en.json`, each naming a cause
      and an action. Satisfies T128. (FR-064, FR-068)
- [ ] T134 [US6] Sweep the diff for leftover markers and type-ignores
      from T123–T129; run the suite and mypy.
- [ ] T135 [US6] Walk the US6 rows of `quickstart.md` and record the
      outcome.

**Exit criteria (US6)**: a revoked token produces an actionable reauth
prompt within one interval; a scope-403 produces neither reauth nor a
repair issue; a 403 with an unparsable body lands on the non-scope
branch; no user-facing message is a bare status code.

**Independently shippable because**: every installation eventually hits
token expiry, and misdirecting a user toward a credential fix for a
capability limit is a user-safety defect under Principle VII.

**Checkpoint**: US1–US6 all work independently.

---

## Phase 9: User Story 7 — Availability and pricing, read-only (P7)

**Goal**: A separate per-property availability sensor fed by the
calendar coordinator, strictly read-only.

**Independent Test**: Confirm each property gains an availability
sensor reading `available` or `booked` (never the literal
`unavailable`), refreshed on the property cadence, and that a full
lifecycle issues zero non-`GET` requests.

**Design note**: availability is a SEPARATE sensor, not attributes on
the reservation sensor. FR-058 requires an availability STATE using a
term such as "booked" and forbids the literal `unavailable`, and a
state requires an entity; FR-043 separately forbids folding a second
dimension into the single-dimensional reservation enum.

### Tests for User Story 7 (RED-PHASE COMMIT) ⚠️

- [ ] T136 [P] [US7] `tests/sensor/test_availability_states.py`: assert
      one availability sensor per property whose state is `available`,
      `booked`, or `unknown`, and that the literal `unavailable` is
      NEVER used as a state value for a booked night. (FR-058)
- [ ] T137 [P] [US7] `tests/sensor/test_availability_pricing.py`:
      assert monetary values are held as INTEGER MINOR UNITS in the
      model and converted to a display value exactly ONCE, in the
      sensor layer, alongside the currency code. Assert no float
      arithmetic occurs before that point. (FR-060)
- [ ] T138 [P] [US7] `tests/api/test_calendar.py`: assert
      `GET /properties/{id}/calendar` sends `start_date` and
      `end_date` for the forward window, that `listing_id` is NEVER
      sent, and that `listing_id`/`provider` in the response are
      treated as cosmetic metadata — the response is an AGGREGATE
      across sales channels and is not scoped by them.
      (FR-058, FR-075)
- [ ] T139 [P] [US7] `tests/test_calendar_coordinator.py`: assert the
      calendar coordinator refreshes on the PROPERTY cadence (60-minute
      default, 15-minute floor) and that a failure fetching ONE
      property's calendar does not fail the others or the properties
      coordinator. (FR-061, FR-071)
- [ ] T140 [P] [US7] `tests/test_no_writes.py`: a WHOLE-LIFECYCLE
      assertion — set up, refresh every coordinator, change options,
      reload, and unload, then assert the `respx` router recorded ZERO
      requests whose method is not `GET`. Calendar data is read-only
      and no modification endpoint is reachable. (FR-059)
- [ ] T141 [US7] Extend `tests/test_init.py`: assert
      `async_setup_entry` now instantiates ALL THREE coordinators.
      (FR-071)
- [ ] T142 [US7] Run `uv run pytest --runxfail` scoped to T136–T141 and
      commit the red phase.

### Implementation for User Story 7 (GREEN-PHASE COMMIT)

- [ ] T143 [P] [US7] Implement the calendar fetch path in
      `custom_components/hospitable/api/client.py` (or a dedicated
      `api/calendar.py` if the module split reads better) with no
      `listing_id` parameter. Satisfies T138. (FR-058, FR-075)
- [ ] T144 [US7] Implement
      `custom_components/hospitable/sensor/availability.py` — enum
      state plus nightly rate attributes converted from minor units
      once. Satisfies T136, T137. (FR-058, FR-060)
- [ ] T145 [US7] Wire the calendar coordinator into
      `async_setup_entry` in `custom_components/hospitable/__init__.py`
      on the property cadence with per-property failure isolation.
      Satisfies T139, T141. (FR-061, FR-071)
- [ ] T146 [US7] Add availability sensor names and state translations
      to `strings.json` and `translations/en.json`, using "booked"
      rather than "unavailable". (FR-058, FR-064, FR-068)
- [ ] T147 [US7] Sweep the diff for leftover markers and type-ignores
      from T136–T141; run the suite and mypy.
- [ ] T148 [US7] Walk the US7 rows of `quickstart.md` and record the
      outcome.

**Exit criteria (US7)**: `booked` never rendered as `unavailable`;
per-property calendar failure isolation proven; a full lifecycle
issuing zero non-`GET` requests.

**Independently shippable because**: it is supplementary and
self-contained, and nothing else depends on it.

**Checkpoint**: all seven user stories complete.

---

## Phase 10: Polish and cross-cutting concerns

**Purpose**: Documentation, coverage, and the audits that only make
sense once every phase has landed. These tasks are largely
documentation-only or test-only and therefore Principle XII exempt;
any that turns out to require a behavior change gets its own red/green
pair.

- [ ] T149 [P] Write `README.md`: installation, the entity table
      (reservation status, next arrival, next departure, upcoming
      reservations, property info, availability), the option reference
      with defaults and floors, the request-volume trade-off, and the
      terminology rule that user-facing text says "property".
      Document the OQ-004 limitation if T100 confirmed it.
      (FR-023, FR-068)
- [ ] T150 [P] Document the request-economy design in `README.md` or a
      developer note: three coordinators, entities read shared
      coordinator data and issue no requests of their own, and the
      default daily budget of 1,704 requests for ten properties.
      (FR-071)
- [ ] T151 [P] Run `uv run interrogate --fail-under=100` over
      `custom_components/` and `tests/` and add any missing docstrings.
- [ ] T152 [P] Confirm coverage is measured over `custom_components/`
      and review the report for untested branches, adding tests for
      any material gap. Report the actual number; do not assert a
      threshold the tool did not produce.
- [ ] T153 **Marker audit**: grep the whole repository for
      `pytest.mark.xfail` and `type: ignore[import-not-found]` and
      confirm ZERO remain. Any survivor means a green phase forgot its
      cleanup, which `xfail_strict` should already have caught — if
      one is found, investigate why the gate did not fire.
- [ ] T154 **Silent-ignore audit**: re-read
      `contracts/upstream-requests.md` and confirm each of the three
      known upstream silent-ignore behaviors has a live assertion — a
      bogus `listing_id` (never sent), a bogus `include=` (never sent,
      and every sent include's key asserted present), and `http://`
      pagination URLs (never followed). (FR-075)
- [ ] T155 Walk the cross-cutting checks section of `quickstart.md` and
      record each outcome.
- [ ] T156 Run the live success-criteria validation (SC-001, SC-002,
      SC-003, SC-005, SC-006, SC-013) against a real account after CI
      is green, and record the measured values.
- [ ] T157 Re-verify `REUSE.toml` covers every path added across all
      phases with `uv run reuse lint`.
- [ ] T158 Update `spec.md`'s open-questions table with the status of
      every OQ the implementation resolved or left open, and update
      `research.md`'s assumption table with the final state of A-1
      through A-8. Say plainly which remain UNVERIFIED.

---

## Dependencies and execution order

### Phase dependencies

- **Phase 1 (Setup)**: no dependencies. Ships in the US1 PR.
- **Phase 2 (Foundational)**: depends on Phase 1. BLOCKS every user
  story. T019–T021 (live probes) additionally BLOCK the US1 green
  phase.
- **Phase 3 (US1)**: depends on Phases 1 and 2.
- **Phases 4–9 (US2–US7)**: each depends on US1, with the additional
  sensor-platform dependency noted below. They are ordered by priority,
  not by technical need, except where noted below.
- **Phase 10 (Polish)**: depends on every user story that is to ship.

### User story dependencies

- **US1 (P1)**: the foundation. Everything else needs it.
- **US2 (P2)**: needs US1. Nothing else.
- **US3 (P3)**: needs US1. It also needs the sensor platform setup and
  entity-creation module introduced at T082 (US2), or must pull T082
  forward if it ships before US2.
- **US4 (P4)**: needs US1. Reuses the FR-056 mechanism introduced in
  US3 (T097) for non-destructive deselection; if US4 ships before US3
  that mechanism must be introduced in T113 instead.
- **US5 (P5)**: needs US1. Predominantly evidence.
- **US6 (P6)**: needs US1.
- **US7 (P7)**: needs US1 and the sensor platform setup and
  entity-creation module introduced at T082 (US2), or must pull T082
  forward if it ships before US2. Nothing depends on it.
- **US3, US4, and US7 sensor caveat**: US3, US4 and US7 additionally
  require the sensor platform setup and entity-creation module
  introduced at T082 (US2). If any of them ships before US2, T082 must
  be pulled forward into that phase.

### Within each user story

- Red phase before green phase, always, as separate commits.
- Tests must report XFAIL, never FAIL. Verify with
  `uv run pytest --runxfail <node ids>` scoped to the new tests.
- Within the green phase: constants and exceptions, then models, then
  the client, then the domain services, then coordinators and
  entities, then the config flow and setup.
- Each green task removes the markers and type-ignores it makes stale,
  in its own commit.

### Parallel opportunities

- Phase 1: T003–T007 are independent files and can run together.
- Phase 2: T012, T013, T014 are three independent fixture sets.
- Phase 3 red: T023–T045 are all separate test files and can be
  written in parallel; T046 gates the commit.
- Phase 3 green: T047–T051 are independent modules; T055 and T056
  parallelize once T052–T054 exist; T057–T059 are independent of the
  `api/` package entirely.
- Phases 4–9 red: every `[P]` test file within a phase is independent.
- Once US1 has merged, US2 through US7 can be developed in parallel by
  different contributors, subject to the US3/US4 and sensor-platform
  notes above.

---

## Parallel example: User Story 1 red phase

```bash
# Independent test files — write and review together:
Task: "tests/api/test_const.py (T023)"
Task: "tests/api/test_exceptions.py (T024)"
Task: "tests/api/test_auth.py (T025)"
Task: "tests/api/test_client_403.py (T026)"
Task: "tests/api/test_pagination.py (T027)"

# Then gate the whole group before committing:
uv run pytest --runxfail tests/api/test_const.py tests/api/test_exceptions.py \
  tests/api/test_auth.py tests/api/test_client_403.py tests/api/test_pagination.py
```

---

## Implementation strategy

### MVP first

1. Phase 1 (Setup) and Phase 2 (Foundational).
2. Phase 3 (US1) red phase, then green phase.
3. **STOP and VALIDATE**: install into a clean Home Assistant, add an
   account, select properties, confirm devices and diagnostics.
4. Ship the US1 pull request.

### Incremental delivery

One pull request per user story, in priority order. Each PR contains at
least one red-phase commit and one green-phase commit, plus a separate
commit for any `tasks.md` update (Principle III). CI must be green
before the next story begins (Principle IX).

### Deliberate scope limits

The following are DEFERRED to future features and are not covered by
any task here. This is a statement of scope, not of completeness:

- Webhooks. This feature is polling-only by decision (FR-067).
- OAuth. PAT authentication only; the design must not preclude OAuth
  (FR-008) but implements none.
- Door codes and any other write operation. The calendar is read-only
  (FR-059).
- Any Home Assistant entity platform other than `sensor`.
- Any Home Assistant service registration. `services/` in this package
  is domain logic only (FR-069).

---

## Notes and known gaps

Read this section before trusting any count elsewhere in this file.

- **Phase structure diverges from `plan.md`.** `plan.md` describes
  seven phases (US1..US7) and folds scaffolding, fixtures, and the PII
  guard into US1. This file adds a Setup phase and a Foundational
  phase because the tasks template requires them and because those
  tasks are Principle XII exempt and must not be forced into a
  red/green pair. Phases 1 and 2 ship in the US1 pull request, so the
  delivery boundaries are unchanged. This is a presentation
  difference, reported rather than silently reconciled.
- **`plan.md`'s phase list omits seven requirements from its
  per-phase requirement lines**: FR-019, FR-020, FR-021, FR-062,
  FR-067, FR-068, and FR-071. All seven ARE covered in `plan.md`'s own
  requirements traceability table, and all are foundation or
  cross-cutting concerns. This file assigns each to concrete tasks;
  see the traceability table below for the authoritative per-task
  list. The omission is reported, not silently reconciled.
- **`plan.md` and `quickstart.md` disagree on three phases'
  requirement lists.** `quickstart.md` assigns FR-050 to US3 where
  `plan.md` assigns it to US1; assigns FR-015 through FR-023 to US4
  where `plan.md` assigns only FR-017, FR-018, FR-022, FR-023, and
  FR-072; and adds FR-014 to US6 where `plan.md` does not. This file
  follows `plan.md`, which is the phase-breakdown authority, while
  ensuring each disputed requirement is covered somewhere.
- **FR-033 is satisfied vacuously and that is a real tension.** FR-033
  says guest information MUST be requested as an include, but
  `include=guests` is a CONFIRMED upstream no-op and this feature
  surfaces only guest COUNTS. The resolution recorded in `plan.md` is
  that the requirement is conditional on surfacing guest data, so
  `include=guests` is NEVER SENT. T030 asserts the prohibition rather
  than the include. If a future feature surfaces guest detail, FR-033
  must be revisited.
- **Three assumptions remain UNVERIFIED at the time of writing** and
  make three tasks less concrete than the rest: A-1 (the reservation
  date-filter mode parameter, assumed `date_query=checkin`), A-2 (the
  scheduled-time field names), and A-3 (the time-string format). T019
  and T020 are live probes that resolve them; T033 and T056 are
  written to work under either outcome, with the fallback of never
  sending the A-1 parameter and relying on authoritative client-side
  filtering. Nothing in the design changes if the probes fail — only a
  constant moves.
- **T100 (OQ-004) and T156 (live success-criteria validation) cannot
  be completed without a real Hospitable account.** They are specified
  as verification obligations, not as things this task list can
  guarantee will be done.
- **This file does not claim complete coverage of every requirement's
  every nuance.** It claims that each of FR-001 through FR-075 is
  named by at least one task, which was verified mechanically by
  extracting the `FR-0NN` tokens from the task lines of this file and
  comparing that set against FR-001..FR-075. Depth of coverage is a
  judgement the reviewer should make independently.

---

## Requirement to task traceability

Generated by extracting the `FR-0NN` tokens appearing in the task lines
of this file. A requirement listed here has at least one task naming
it; it does not follow that the task fully discharges it.

| Requirement | Tasks |
| --- | --- |
| FR-001 | T023, T025, T047, T049 |
| FR-002 | T023, T047 |
| FR-003 | T025, T049 |
| FR-004 | T041, T063 |
| FR-005 | T025, T049 |
| FR-006 | T029, T043, T050 |
| FR-007 | T006, T063, T066 |
| FR-008 | T025, T049 |
| FR-009 | T041, T063 |
| FR-010 | T041, T063 |
| FR-011 | T041, T063 |
| FR-012 | T041, T063, T117, T119 |
| FR-013 | T041, T063, T120, T121 |
| FR-014 | T041, T063, T121, T123 |
| FR-015 | T041, T063 |
| FR-016 | T041, T063, T104, T111 |
| FR-017 | T103, T110 |
| FR-018 | T097, T107, T113 |
| FR-019 | T038, T060, T061, T108, T111 |
| FR-020 | T038, T060, T061, T108, T111 |
| FR-021 | T035, T057, T060, T108, T111 |
| FR-022 | T035, T057, T104, T111 |
| FR-023 | T106, T111, T114, T149 |
| FR-024 | T012, T020, T031, T053 |
| FR-025 | T012, T027, T032, T054, T055 |
| FR-026 | T012, T027, T054 |
| FR-027 | T012, T027, T034, T054 |
| FR-028 | T033, T056 |
| FR-029 | T033, T056 |
| FR-030 | T019, T033, T056 |
| FR-031 | T033, T047, T056 |
| FR-032 | T013, T056, T069, T079 |
| FR-033 | T030 |
| FR-034 | T020, T030, T052 |
| FR-035 | T014, T024, T048 |
| FR-036 | T028, T051 |
| FR-037 | T028, T051 |
| FR-038 | T014, T026, T054, T124, T125, T126, T131, T132 |
| FR-039 | T031, T053 |
| FR-040 | T034, T036, T054, T058 |
| FR-041 | T040, T065 |
| FR-042 | T072, T075, T082, T084 |
| FR-043 | T013, T069, T072, T079, T084 |
| FR-044 | T071, T081 |
| FR-045 | T070, T080 |
| FR-046 | T073, T084 |
| FR-047 | T070, T080 |
| FR-048 | T013, T069, T079 |
| FR-049 | T073, T076, T080, T084 |
| FR-050 | T039, T062 |
| FR-051 | T089, T096 |
| FR-052 | T090, T096 |
| FR-053 | T091, T096 |
| FR-054 | T039, T062, T092, T098, T118 |
| FR-055 | T039, T062, T092, T098, T107, T117, T118 |
| FR-056 | T093, T097, T113 |
| FR-057 | T074, T083 |
| FR-058 | T014, T072, T136, T138, T143, T144, T146 |
| FR-059 | T140 |
| FR-060 | T053, T082, T137, T144 |
| FR-061 | T139, T145 |
| FR-062 | T031, T043, T053, T073, T084, T091 |
| FR-063 | T042, T064 |
| FR-064 | T006, T066, T086, T099, T104, T111, T114, T123, T128, T131, T133, T146 |
| FR-065 | T040, T065, T124, T125, T127, T129, T131 |
| FR-066 | T003, T004 |
| FR-067 | T003, T045, T065, T066 |
| FR-068 | T006, T044, T066, T086, T099, T114, T133, T146, T149 |
| FR-069 | T007 |
| FR-070 | T040, T060, T065 |
| FR-071 | T038, T040, T061, T065, T077, T085, T139, T141, T145, T150 |
| FR-072 | T037, T059, T105, T112 |
| FR-073 | T031, T043, T053, T073, T084 |
| FR-074 | T036, T058, T070, T080, T094, T098 |
| FR-075 | T011, T013, T019, T027, T030, T032, T052, T055, T138, T143, T154 |
