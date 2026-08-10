<!--
SPDX-FileCopyrightText: Delimarsky, D., & Riem, M. (2026)
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: MIT
-->

<!--
  Sync Impact Report
  ==================================================
  Version change: 1.1.0 → 1.1.1
  Change type: PATCH - a factual licensing correction and wording
  refinement. No principle is added, removed, renamed, renumbered, or
  materially expanded; all twelve retain their existing scope.

  Report scope: this block describes ONLY the most recent amendment.
  It is overwritten on every amendment; the full amendment history is
  the git history of this file.

  Why this amendment exists
  -------------------------------------------------
  Version 1.1.0 still described Hospitable brand imagery as
  CC-BY-SA-4.0 material copyrighted by the repository owner. That was
  factually wrong: the images are third-party trademark assets for the
  Hospitable service, and the Hospitable name and logo are trademarks
  of Hospitable R&D BV. The project now annotates
  `custom_components/hospitable/brand/**` as
  `LicenseRef-Hospitable-Trademark` with Hospitable R&D BV as the
  copyright holder, matching the trademark notice shipped under
  `LICENSES/`.

  Modified principles (all retain their number and title):
    - IV. Licensing & Attribution Standards
      - The location-to-license enumeration now identifies Hospitable
        brand assets as `LicenseRef-Hospitable-Trademark` material used
        only for third-party service identification, not as
        CC-BY-SA-4.0 material.
      - The rationale now describes the brand imagery as third-party
        trademark material rather than share-alike material, preserving
        the same warning that downstream HACS users inherit licensing
        defects.

  Added sections: None.

  Removed sections: None.

  Renumbered principles: None.

  Template propagation status
  -------------------------------------------------
  All five files in .specify/templates/ were opened and inspected for
  this amendment. Findings, stated as checked rather than assumed:

    - .specify/templates/plan-template.md — CHECKED, no change needed.
      Its Constitution Check section delegates gates to the current
      constitution through the placeholder "[Gates determined based on
      constitution file]" and contains no hard-coded license, brand, or
      trademark enumeration.
    - .specify/templates/tasks-template.md — CHECKED, no change needed.
      Its project overlay references Principles I, IX, and XII for
      mandatory red-phase testing only. It contains no Principle IV,
      license, brand, trademark, or CC-BY-SA text.
    - .specify/templates/spec-template.md — CHECKED, no change needed.
      The template is generic feature-spec boilerplate and contains no
      license, brand, trademark, or CC-BY-SA text.
    - .specify/templates/checklist-template.md — CHECKED, no change
      needed. The checklist scaffold contains no constitution, license,
      brand, trademark, or CC-BY-SA text.
    - .specify/templates/constitution-template.md — CHECKED, no change
      needed. It is the unfilled upstream scaffold with placeholder
      principle and version fields only; it contains no project license
      enumeration or Hospitable brand guidance.

  Migration plan: No code migration is required. Existing brand files
  are already covered by the corrected `REUSE.toml` annotation and the
  new `LICENSES/LicenseRef-Hospitable-Trademark.txt` notice.
  ==================================================
-->

# Hospitable Integration Constitution

## Core Principles

### I. Code Quality & Testing Standards (NON-NEGOTIABLE)

- All source code MUST pass the configured linting and static analysis
  checks (`ruff-check`, `ruff-format`, `mypy`, `interrogate`) with zero
  errors or warnings.
- Every module, function, and class MUST include a docstring describing
  its purpose, parameters, return values, and raised exceptions.
- Type annotations MUST be present on all function signatures; `mypy`
  runs against Python 3.14 and MUST report no errors.
- `interrogate` MUST enforce 100% docstring coverage
  (`--fail-under=100`); commits that reduce coverage are PROHIBITED.
- **Code-level TDD is mandatory.** Every unit of production code MUST be
  preceded by a test that defines the desired behavior and does not yet
  pass. The Red-Green-Refactor cycle is strictly enforced:
  1. Write a test that defines the desired behavior and does not yet
     pass. Per Principle XII this MUST be expressed as
     `@pytest.mark.xfail(raises=..., reason="...", strict=True)`,
     never as a red suite.
  2. Implement the minimum code required to make the test pass.
  3. Refactor while keeping all tests green.
- Test files MUST be named `test_*.py` (enforced by the
  `name-tests-test --pytest-test-first` hook), except for `conftest.py`
  and `tests/helpers.py`.
- CI tests MUST pass before any manual or exploratory testing is
  performed. Manual testing without green CI is PROHIBITED.
- Production-code test coverage, measured over `custom_components/`
  only (see the Coverage Measurement constraint), MUST be maintained
  or increased
  with every change; coverage regressions MUST be justified and
  approved in review. Test files themselves MUST NOT be counted, since
  a red-phase test body legitimately stops executing at its deferred
  import (Principle XII).

**Rationale**: This integration surfaces live vacation-rental data —
reservations, guest identities, property calendars, and guest messaging
— inside Home Assistant, where it will drive automations that unlock
doors, arm alarms, and set thermostats around real arrivals and
departures. A defect that mis-parses a check-out date or drops a
reservation update can strand a guest outside a property or leave a
property unlocked after checkout. Rigorous, automated quality gates are
the only affordable way to keep that class of failure out of the
codebase.

### II. API Client Design

- The Hospitable API client MUST be implemented as a clean abstraction
  layer that isolates all HTTP communication from Home Assistant
  business logic. Coordinators and entity platforms MUST NOT construct
  HTTP requests directly.
- The client MUST target the Hospitable Public API v2. Because
  Hospitable carries its API version in the URL path, the targeted
  version MUST be a single documented constant and MUST NOT be
  scattered across call sites.
- The client MUST support the Personal Access Token model (sent as
  HTTP Bearer credentials) as the primary, self-serve credential
  model. It MUST NOT be designed in a way that precludes adding the
  OAuth 2.0 authorization-code flow later. Credential handling MUST
  sit behind one interface so that callers never branch on credential
  type and so that adding OAuth is an internal change to the client
  rather than a change rippling through coordinators.
- OAuth 2.0 support is DEFERRED until Hospitable Vendor access is
  actually obtained, and it MUST NOT be a precondition for any
  release. Hospitable grants OAuth only to approved Vendors, via an
  application-and-approval process with no self-serve path, so a
  self-hosted Home Assistant user cannot obtain it. Requirements in
  this constitution that describe OAuth behavior are forward-looking:
  they bind the implementation if and when OAuth is added, and they
  impose no obligation before then.
- When and if OAuth support is added, credential renewal MUST be
  handled transparently inside the client; callers MUST NOT manage
  token lifecycle. The client MUST detect expiry reactively (from
  authentication failures) as well as proactively (from expiry
  metadata returned at grant time). Published lifetimes — a 12-hour
  access token and a 90-day refresh token, with both rotating on
  refresh — are CONFIRMED-BY-SPEC from Hospitable's OpenAPI export and
  NOT confirmed by a live grant, so the client MUST treat the metadata
  on the actual response as authoritative and MUST NOT hard-code an
  assumed lifetime.
- **Vendor-gated scopes are a capability boundary, not an auth
  failure.** CONFIRMED-BY-TEST: with a valid Personal Access Token,
  `GET /v2/reservations/{uuid}` returns HTTP 200 while
  `GET /v2/reservations/{uuid}/enrichment` returns HTTP 403 with the
  reason phrase "Invalid scope(s) provided." Reservation enrichment —
  which carries the `smartlock_code` shortcode used for door codes —
  and any other endpoint requiring `enrichment:read`,
  `enrichment:write`, or another Vendor-only scope is UNREACHABLE with
  a Personal Access Token. Therefore:
  - A scope-related HTTP 403 MUST be treated as a permanent capability
    limitation, distinct from the HTTP 401 that signals an invalid or
    expired credential.
  - Such a 403 MUST NOT be retried, and MUST NOT trigger the
    reauthentication flow. Placing a valid config entry into a reauth
    loop that the user can never satisfy is a PROHIBITED failure mode.
  - Features that depend on vendor-gated scopes MUST be omitted or
    disabled rather than surfaced to the user as failing.
- The client MUST implement rate-limit awareness. Hospitable publishes
  no general numeric rate-limit ceiling, so the client MUST NOT
  hard-code quotas. It MUST treat HTTP 429 as authoritative, MUST
  honor any `Retry-After` or rate-limit headers present on the
  response, MUST NOT assume such headers are present (their existence
  is UNVERIFIED), and MUST otherwise apply exponential backoff with
  jitter. The only documented Hospitable limits are for messaging — 2
  messages per minute per reservation and 50 messages per 5 minutes —
  and those MUST be respected where the integration sends messages.
- The client MUST handle pagination for all list endpoints (Hospitable
  v2 list endpoints accept `page` and `per_page` and return items under
  a `data` key), exposing async iterators or an equivalent pattern so
  callers never page manually.
- Error handling MUST translate Hospitable API errors into well-typed
  Python exceptions carrying actionable context (HTTP status, endpoint,
  and a redacted response-body excerpt). Bare `Exception` propagation
  is PROHIBITED.
- The client MUST be independently testable without a live Hospitable
  account. All outbound HTTP MUST be exercised through `httpx` and
  mocked with `respx`; tests that require real network access are
  PROHIBITED.
- Request and response payloads MUST be validated against expected
  schemas. A malformed or unexpectedly shaped API response MUST raise
  an explicit error rather than yielding a partially populated entity.

**Rationale**: Hospitable's v2 surface spans properties, calendars,
reservations, guests, messages, and reviews — each with its own shape
and its own failure modes. Folding HTTP concerns into entity code would
make every one of those domains untestable without a live paid
Hospitable account and would let an upstream schema change break
unrelated platforms. Isolating the client also means the credential
model stays a client-internal detail: today every user authenticates
with a single-account Personal Access Token, and if a multi-account
OAuth grant ever becomes obtainable it can be added behind the same
interface without leaking into every coordinator. Recording the
vendor-scope boundary here matters just as much, because the failure it
produces looks exactly like an auth failure and is not one — a 403 on
enrichment is the API saying "this token will never be allowed to do
this," and treating it as a credential problem would push a correctly
configured user into an endless reauthentication loop.

### III. Atomic Commit Discipline (NON-NEGOTIABLE)

- Every commit MUST represent exactly one logical change (one feature,
  one fix, one refactor, or one red-phase test set).
- Each commit MUST leave the tree in a working state; broken
  intermediate states are PROHIBITED.
- Commit subjects MUST follow Conventional Commits with capitalized
  types as enforced by `.gitlint`: `Fix`, `Feat`, `Chore`, `Docs`,
  `Style`, `Refactor`, `Perf`, `Test`, `Revert`, `CI`, `Build`.
- Commit subjects MUST fit within 72 characters. `.gitlint` leaves
  `title-max-length` at its 72-character default (the
  `[title-max-length]` stanza is commented out), so 72 is both the
  project convention and the mechanically enforced limit.
- Pull request titles MUST satisfy the same convention; the
  `semantic-pull-request` workflow blocks merge otherwise.
- Commit bodies MUST be wrapped at 72 characters. This is a project
  convention that is stricter than what tooling enforces: gitlint's
  `body-max-line-length` default is 80 and `.gitlint` does not override
  it, and `.gitlint` additionally disables that check entirely for any
  body containing a URL. The 72-character wrap MUST therefore be
  applied by hand and verified in review; no hook will catch a body
  wrapped at 73 to 80 characters.
- Large features MUST be broken into multiple atomic commits. Mixing
  unrelated changes in a single commit is PROHIBITED.
- Task-tracking document updates (`tasks.md`) MUST be committed
  separately from the code they track, even though both are
  documentation-classified changes.
- Direct commits to `main` are PROHIBITED and are blocked locally by
  the `no-commit-to-branch` hook.

**Rationale**: Access-control and reservation logic is exactly the kind
of code that gets bisected under pressure — when a guest reports a door
code that did not work, the team needs to find the offending change in
minutes, not hours. Atomic commits keep `git bisect` meaningful, keep
reverts surgical, and keep review focused. Separating `tasks.md` churn
from real code prevents bookkeeping noise from obscuring the diff that
actually changed behavior.

### IV. Licensing & Attribution Standards (NON-NEGOTIABLE)

- Every file MUST be REUSE-compliant, either through inline SPDX
  copyright and license headers or through an entry in `REUSE.toml`.
- The `reuse` pre-commit hook enforces compliance; files that are
  neither headered nor covered by `REUSE.toml` MUST NOT be committed.
- This project is multi-licensed. Contributors MUST apply the correct
  license for the file's location:
  - **Apache-2.0** — the default for all project-authored code,
    documentation, configuration, `custom_components/**/*.json`,
    `specs/**`, `hacs.json`, `uv.lock`, and `.grype.yaml`.
  - **MIT** — vendored Spec Kit material under `.specify/**`,
    `.github/*/speckit.**`, and `.vscode/**`, copyright
    "Delimarsky, D., & Riem, M. (2026)". Contributors MUST NOT
    relicense these files.
  - **LicenseRef-Hospitable-Trademark** — Hospitable trademark assets
    under `custom_components/hospitable/brand/**`, used only for
    third-party service identification.
- Python files carrying inline headers MUST use:

  <!-- REUSE-IgnoreStart -->
  ```python
  # SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
  # SPDX-License-Identifier: Apache-2.0
  ```
  <!-- REUSE-IgnoreEnd -->

- Markdown, XML, and other block-comment formats MUST use the
  equivalent block-comment form.
- Adding a new top-level path MUST be accompanied by either inline
  headers on its files or a matching `REUSE.toml` annotation in the
  same commit.

**Rationale**: This repository deliberately mixes three licenses with
three different obligations, and two of them are not the project's own.
Vendored Spec Kit tooling is MIT and upstream-owned; Hospitable-facing
brand imagery is a third-party trademark asset, not project-authored
Apache-2.0 material. Getting this wrong is not a cosmetic error — it is
a licensing defect that a downstream HACS user inherits.
Machine-checked REUSE compliance is the only way to keep multiple
license and trademark regimes straight in a repository that a single
maintainer and several AI agents both touch.

### V. Pre-Commit Integrity (NON-NEGOTIABLE)

- All pre-commit hooks MUST pass locally prior to any push. Bypassing
  hooks with `--no-verify` is **PROHIBITED** under all circumstances.
- The enforced hook set, per `.pre-commit-config.yaml`, includes:
  - **File integrity** — `check-added-large-files` (1000 KB cap),
    `check-ast`, `check-builtin-literals`, `check-case-conflict`,
    `check-docstring-first`, `check-executables-have-shebangs`,
    `check-illegal-windows-names`, `check-json`, `check-toml`,
    `check-xml`, `check-yaml`, `check-merge-conflict`,
    `check-shebang-scripts-are-executable`, `check-symlinks`,
    `check-vcs-permalinks`, `debug-statements`, `destroyed-symlinks`,
    `end-of-file-fixer`, `fix-byte-order-marker`,
    `forbid-new-submodules`, `forbid-submodules`, `mixed-line-ending`,
    `requirements-txt-fixer`, and `trailing-whitespace`.
  - **Secret detection** — `detect-private-key` and
    `detect-aws-credentials`.
  - **Branch protection** — `no-commit-to-branch --branch=main`.
  - **Test naming** — `name-tests-test --pytest-test-first`.
  - **Commit message format** — `gitlint`.
  - **Python** — `ruff-check` (run with `--fix` and
    `--exit-non-zero-on-fix`), `ruff-format`, `mypy` (Python 3.14),
    and `interrogate --fail-under=100`.
  - **Markup and shell** — `markdownlint --fix`, `yamllint`,
    `actionlint`, `shellcheck`, and `bashate`.
  - **Licensing** — `reuse`.
  - **Spelling** — `codespell` (allowed words: `hass`, `checkin`,
    `astroid`).
  - **Agent output review** — the local `aislop ci` hook.
- **`mypy` and `aislop` are enforced locally only.** No workflow runs
  `pre-commit`; enforcement in CI comes from the pre-commit.ci app, and
  `.pre-commit-config.yaml` sets `ci: skip: [mypy, aislop]`. A
  contributor who skips local pre-commit will therefore NOT be caught
  by CI for a type error or an agent-output violation. This makes the
  local run of these two hooks mandatory in practice as well as in
  principle.
- Contributors MUST NOT claim enforcement from hooks that are commented
  out in `.pre-commit-config.yaml` (currently `validate-pyproject`,
  `double-quote-string-fixer`, `pretty-format-json`, `write-good`,
  `pyupgrade`, and the local `mypy-cache` and `pytest-cov` hooks). Any
  of these that becomes required MUST be enabled in configuration
  first, then reflected here by amendment.
- `markdownlint` excludes `.specify/` and `.github/`, and `bashate`
  and `shellcheck` carry exclusions for vendored Spec Kit scripts.
  Excluded paths MUST still be written to the same standard.

**Failure Recovery Protocol**:

1. Fix the issues reported by the failing hooks.
2. Stage the fixes with `git add`.
3. Attempt the commit again as if the prior attempt never happened.
4. Do NOT use `git reset` after a failed commit attempt.

**Rationale**: Pre-commit is where this project catches the failures
that matter most before they reach a user's Home Assistant instance: a
leaked Hospitable token caught by `detect-private-key`, a guest-PII
logging mistake caught in review of a clean diff, an un-headered file
caught by `reuse`. Because a single maintainer merges most changes,
these hooks are effectively the second reviewer. Bypassing them removes
the only automated check standing between a mistake and a published
HACS release. Enumerating exactly which hooks are active — and refusing
to claim the ones that are not — keeps this document honest and keeps
contributors from relying on protection that does not exist.

### VI. Agent Co-Authorship & DCO Requirements (NON-NEGOTIABLE)

- Every commit MUST carry a DCO sign-off added via `git commit -s`:

  ```text
  Signed-off-by: Andrew Grimberg <tykeal@bardicgrove.org>
  ```

- Every commit to which an AI agent materially contributed MUST include
  a `Co-authored-by` trailer naming the agent that actually did the
  work, for example:

  ```text
  Co-authored-by: Claude <claude@anthropic.com>
  Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
  ```

  The trailer MUST name the specific model or agent used, per the table
  in `AGENTS.md`. Attributing work to an agent that did not perform it
  is PROHIBITED.
- **Committer and author identity MUST remain the human contributor's
  real signing identity.** Setting `user.name`, `user.email`,
  `GIT_AUTHOR_*`, or `GIT_COMMITTER_*` to an AI persona address is
  **PROHIBITED**. Doing so detaches the commit from the human's signing
  key and breaks verified-signature and DCO validation. AI attribution
  belongs in the `Co-authored-by` trailer and nowhere else.
- Bots and agents that only *review* a change (for example an automated
  PR reviewer) MUST NOT receive a `Co-authored-by` trailer. Only agents
  that contributed content are co-authors.
- The `Co-authored-by` trailer goes in the commit message body;
  `git commit -s` appends `Signed-off-by` last. The
  `contrib-body-requires-signed-off-by` gitlint rule enforces the
  sign-off's presence.

**Rationale**: This integration is developed substantially with AI
assistance, and it handles guest personal data under an Apache-2.0
grant that depends on a valid chain of provenance. The DCO sign-off is
the human contributor's legal assertion about the code; only a human
can make it, and only the human's own signing identity can carry it.
Recording agent participation in a trailer preserves an accurate audit
trail without ever letting a machine appear to have certified origin.
Excluding reviewer-only bots keeps that trail meaningful rather than
decorative.

### VII. User Experience Consistency

- Configuration MUST use Home Assistant config flow patterns and MUST
  implement, at minimum, the user (initial setup) step, a reauth flow,
  and an options flow.
- The config flow MUST support Personal Access Token entry as the
  primary, self-serve Hospitable credential model. The config flow and
  the credential handling behind it MUST NOT be designed in a way that
  precludes adding the OAuth 2.0 authorization-code flow later. OAuth
  support is DEFERRED until Hospitable Vendor access is actually
  obtained and MUST NOT be a precondition for any release. Whichever
  credential models are supported, the distinction between them MUST
  NOT be exposed to the user as internal jargon.
- Entity naming MUST follow Home Assistant conventions, using the
  pattern `sensor.hospitable_<property>_<attribute>` and its
  per-platform equivalents. Ad hoc naming is PROHIBITED.
- Unique IDs MUST be derived from stable Hospitable identifiers so that
  renaming a property in Hospitable does not orphan entities or destroy
  recorder history.
- State attributes MUST remain backward compatible unless explicitly
  versioned with a documented migration path.
- Error messages surfaced in the config flow, repair issues, and logs
  MUST state what failed and what the user should do about it (for
  example, "the Personal Access Token was rejected; generate a new
  token in Hospitable under Apps and reauthenticate"). Raw HTTP status
  codes alone are not acceptable user-facing errors. A message MUST
  NOT direct the user to fix a credential when the underlying failure
  is a scope limitation their credential type cannot satisfy; that
  case MUST be described as an unavailable capability instead.
- Breaking changes to entity structure, service calls, or configuration
  options MUST be documented in release notes and versioned before
  release.

**Rationale**: The people configuring this integration are property
managers, not Home Assistant developers, and they will wire its
entities into automations that physically admit guests to buildings. If
an entity ID silently changes shape between releases, the automation
that issues a door code stops firing and a guest is locked out at
midnight. Stable unique IDs, stable attributes, and error messages that
name the actual remedy are therefore user-safety features, not polish.

### VIII. Performance Requirements

- All I/O MUST use Home Assistant async patterns. Blocking the Home
  Assistant event loop is PROHIBITED.
- Any unavoidable blocking call MUST be offloaded via
  `hass.async_add_executor_job(...)`.
- Polling intervals MUST be configurable, MUST ship with sensible
  defaults, and MUST enforce a minimum floor that cannot be lowered by
  configuration.
- Because Hospitable publishes no numeric rate-limit ceiling, polling
  MUST be conservative by default and MUST back off adaptively in
  response to HTTP 429 rather than assuming a fixed quota.
- API responses MUST be cached where appropriate to eliminate redundant
  calls, and the cache invalidation strategy MUST be documented.
- Coordinators MUST batch and share data across entities rather than
  letting each entity poll independently.
- Resource consumption MUST be bounded: unbounded in-memory growth of
  reservation, message, or event history is PROHIBITED, and listeners,
  tasks, and HTTP clients MUST be torn down on config entry unload.
- The integration MUST remain usable on Raspberry-Pi-class hardware
  under a realistic multi-property load.

**Rationale**: Home Assistant runs single-threaded on an event loop
that every other integration in the instance shares, and a large share
of this integration's users will run it on a small ARM board sitting in
a rental property's utility closet. A blocking HTTP call in a
reservation refresh does not merely slow this integration down — it
stalls the lock, alarm, and climate integrations alongside it. Adaptive
backoff matters for the same reason: a poll loop that trips Hospitable
rate limiting degrades every consumer on that Hospitable account, not
just Home Assistant.

### IX. Phased Development

- Development MUST proceed in defined phases, each delivering an
  independently testable increment of functionality.
- Unit-level TDD (Red-Green-Refactor) MUST NOT be deferred under any
  circumstance. Higher-level tests that span multiple stories or that
  depend on infrastructure from a later phase MAY be deferred to the
  phase in which their prerequisites exist.
- Each phase MUST end at a checkpoint where the full CI suite is green
  and the increment has been validated before the next phase starts.
- Phase boundaries, their exit criteria, and their deferred tests MUST
  be documented in the feature's `plan.md` and `tasks.md`.
- The API client layer MUST be delivered and proven before dependent
  Home Assistant platforms are built on top of it.

**Rationale**: The Hospitable surface this integration will eventually
cover — properties, calendars, reservations, guests, messages, reviews,
plus webhooks — is far too large to build in one pass, and each domain
compounds the risk of the ones below it. Proving the client layer first
means a pagination or authentication bug is found once, in isolation,
rather than rediscovered separately in six entity platforms. Explicit
checkpoints also give a solo maintainer a safe place to stop.

### X. Security & Credential Management (NON-NEGOTIABLE)

- Personal Access Tokens, OAuth client secrets, access tokens, refresh
  tokens, and any other credential MUST NEVER be committed to source
  control, embedded in tests, or written to fixture files.
- Credentials MUST be stored exclusively in Home Assistant's config
  entry storage. Writing credentials to integration-managed files,
  environment variables, or custom storage is PROHIBITED.
- When and if OAuth support is added, OAuth renewal MUST be handled
  inside the API client and MUST be invisible to callers. Hospitable's
  published lifetimes and scope names are CONFIRMED-BY-SPEC only (from
  its OpenAPI export, not from a live grant), so the implementation
  MUST NOT depend on those values as if observed; it MUST react to
  authentication failures as a first-class case and MUST honor the
  expiry metadata actually returned. Because both the access token and
  the refresh token rotate on refresh, a renewed refresh token MUST
  replace the stored one atomically and the superseded token MUST be
  discarded.
- Personal Access Tokens MUST be treated as expiring credentials that
  can also be revoked at any time from the Hospitable account.
- A reauthentication path MUST exist and MUST be triggered
  automatically whenever credentials are rejected, for every supported
  credential model. Silent, permanent failure of a config entry is
  PROHIBITED.
- Reauthentication MUST NOT be triggered by a scope-related HTTP 403.
  A credential rejection (HTTP 401) and a capability limitation (a 403
  reporting insufficient scope) are different conditions and MUST be
  distinguished before any recovery action is taken. Driving a valid
  config entry into a reauthentication loop that the user has no way
  to satisfy is a PROHIBITED failure mode.
- **Server-supplied pagination URLs MUST NOT be followed verbatim.**
  CONFIRMED-BY-TEST: Hospitable's paginator returns page links with an
  `http://` scheme, for example
  `"url": "http://public.api.hospitable.com/v2/reservations?page=2"`.
  Requesting such a link as given would silently downgrade transport
  security and expose the Bearer credential in cleartext. The client
  MUST construct page requests itself from a known-good base URL, or
  MUST force the `https` scheme on any URL it takes from a response
  body, before issuing the request.
- Credentials MUST be redacted from all logs, diagnostics downloads,
  and exception messages, including inside captured HTTP request and
  response bodies.
- Guest personal data — names, email addresses, phone numbers, and
  message content — MUST NOT be written at `debug` level or included in
  diagnostics output without redaction.
- Data sent to the Hospitable API MUST be validated before
  transmission; malformed payloads MUST be rejected locally with a
  clear error rather than forwarded upstream.

**Rationale**: A Hospitable credential is not a read-only convenience —
it reaches reservations, guest contact details, and guest messaging for
an entire property portfolio. A Personal Access Token does not reach
every endpoint (vendor-gated scopes such as enrichment refuse it), but
that limit narrows only what a token can *do*, not the breadth of
personal data it can *read*: one PAT still exposes every guest record
across every property on the account. A token leaked into a log file, a
diagnostics bundle attached to a public GitHub issue, or a committed
test fixture is a direct privacy breach for people who never agreed to
use Home Assistant at all. Guest PII deserves the same treatment for
the same reason: the guests are third parties to this software, and
they cannot consent to its logging behavior.

### XI. Webhook & Real-Time Event Handling

- Incoming webhook requests MUST be authenticated before any payload is
  parsed or acted upon. The verification mechanism in use MUST be
  documented in the implementation plan and MUST be applied
  unconditionally; processing unverified payloads is PROHIBITED.
- Webhook handling MUST be idempotent. Hospitable retries failed
  deliveries with backoff, so the same event WILL arrive more than
  once. Duplicate deliveries MUST be detected and MUST NOT produce
  duplicate state changes, duplicate notifications, or duplicate
  automation triggers.
- Out-of-order delivery MUST be tolerated. Events MUST be applied only
  when they are newer than the state already held, using an event
  timestamp or version from the payload; a stale event MUST NOT
  overwrite newer state.
- The webhook endpoint MUST acknowledge receipt quickly and MUST defer
  all substantive work to a background task. Performing API calls,
  entity updates, or any other slow work inline in the request handler
  is PROHIBITED, since it blocks the Home Assistant event loop.
- The integration MUST degrade gracefully when webhooks are
  unavailable, misconfigured, or failing: polling MUST remain a
  supported mode and MUST be sufficient on its own for correct, if less
  timely, state.
- On startup, reconnect, or any detected gap in delivery, the
  integration MUST reconcile state by backfilling from the REST API
  rather than assuming no events were missed. Silent state drift is
  PROHIBITED.
- Webhook payloads MUST be validated against expected schemas, and
  unknown event types MUST be ignored safely rather than raising.
- Guest PII from webhook payloads MUST NOT be written to debug logs.
  Log event type and identifiers, not message bodies or guest contact
  details.

**Rationale**: Hospitable emits webhooks for reservation, property,
message, and review changes, and retries failed deliveries several
times with increasing delay — which means duplicate and late deliveries
are the normal case, not an edge case. A non-idempotent handler would
re-trigger a check-in automation on a retry and re-issue a door code; a
handler that lets a stale retry overwrite fresher state would show a
cancelled reservation as active. Because a webhook can simply never
arrive — a restarted Home Assistant instance, a lapsed tunnel, a
network outage — polling reconciliation is what keeps a missed
cancellation from leaving a property configured for a guest who is not
coming.

### XII. Red-Phase Commit Protocol (NON-NEGOTIABLE)

Test-Driven Development in this project MUST be expressed in the git
history, not merely in the developer's workflow. The red phase and the
green phase are SEPARATE, individually valid commits.

**The two-commit sequence**:

1. **Red-phase commit (tests only).** The expected-failing tests that
   define the desired behavior MUST be committed first, on their own,
   with every such test marked
   `@pytest.mark.xfail(raises=..., reason="...", strict=True)`.
   Because the behavior is not yet implemented, those tests report
   XFAIL and the full suite is green. A red-phase commit MUST NOT
   contain production-code changes.
2. **Green-phase commit (implementation).** The implementation MUST
   land in a separate commit that ALSO removes the `xfail` markers, and
   the `# type: ignore[import-not-found]` comments, from the tests it
   satisfies. The suite is green again, now with those tests genuinely
   passing.

```python
# Red-phase commit: tests only, no production code.
@pytest.mark.xfail(
    raises=ImportError,
    reason="TDD red phase: T017 coordinator refresh not implemented",
    strict=True,
)
async def test_coordinator_refresh_updates_reservations() -> None:
    """The coordinator refreshes reservation state from the API."""
    # Imported inside the test body so that a missing module is an
    # expected failure rather than a collection error. The
    # `type: ignore[import-not-found]` keeps `mypy` green while the
    # module does not exist; BOTH it and the `xfail` marker MUST be
    # removed in the green-phase commit.
    from custom_components.hospitable.coordinator import (  # type: ignore[import-not-found]
        ReservationCoordinator,
    )

    assert ReservationCoordinator is not None
```

**Strictness is mandatory**:

- `strict` MUST be in effect for every `xfail` marker used for
  red-phase work, either through a global `xfail_strict = true` under
  `[tool.pytest.ini_options]` in `pyproject.toml` or explicitly on each
  marker. Non-strict `xfail` for red-phase work is PROHIBITED.
- **`strict=True` alone does NOT verify why a test failed.** When an
  `xfail` marker carries no `raises=`, pytest converts ANY exception
  raised in the setup or call phase into XFAIL; `strict` governs only
  the no-exception path. A red-phase test with a typo, a misspelled
  fixture name, or a wrong import path would therefore report XFAIL,
  pass every gate, and assert nothing — a false green. Every red-phase
  marker MUST therefore pin the expected failure type with `raises=`
  wherever that type is known, for example:

  ```python
  @pytest.mark.xfail(
      raises=ImportError,
      strict=True,
      reason="TDD red phase: T017 coordinator refresh not implemented",
  )
  ```

  A red-phase test that fails for any reason other than the missing
  behavior is a defect, not a valid red phase, and MUST be fixed before
  the red-phase commit is made.
- When `pyproject.toml` is created for this project it MUST set:

  ```toml
  [tool.pytest.ini_options]
  xfail_strict = true
  asyncio_mode = "auto"
  ```

  `asyncio_mode = "auto"` is not optional decoration: without it an
  unmarked `async def` test never runs its body. When the marker pins
  `raises=`, the test hard-fails as unsupported (pytest raises
  `Failed: async def functions are not natively supported`, which is
  not the pinned exception type); when the marker does not pin
  `raises=`, that same failure is silently converted to XFAIL and the
  red phase reports green for a test whose body never ran. Both
  outcomes are wrong, so `asyncio_mode = "auto"` is mandatory.
- The `[tool.mypy]` configuration MUST enable
  `warn_unused_ignores = true`. The deferred red-phase import carries
  `# type: ignore[import-not-found]`, which is legitimate while the
  module is missing and stale once the module exists. With this
  setting enabled, `mypy` reports
  `Unused "type: ignore" comment [unused-ignore]` on exactly the
  green-phase commit that FORGOT to remove the comment, and stays
  green on both the red-phase commit and the green-phase commit that
  removed it. This is the `xfail_strict` analogue for ignore comments:
  it makes ignore-comment removal a mechanically enforced gate rather
  than a convention, which is what this principle requires below.
  Three notes:
  - `strict = true` implicitly enables `warn_unused_ignores`, so a
    future `[tool.mypy] strict = true` SATISFIES this constraint
    rather than conflicting with it.
  - In a partially satisfied green phase, a second red-phase test that
    imports a not-yet-existing name from the now-existing module sees
    its error code shift from `import-not-found` to `attr-defined`.
    Its ignore comment MUST be RE-CODED to
    `# type: ignore[attr-defined]`, not merely retained.
  - Any narrowing of this setting MUST be expressed as a
    `[[tool.mypy.overrides]]` entry with `module = "tests.*"`. Using
    mypy's `exclude` for this purpose is PROHIBITED: `exclude` removes
    files from type checking ENTIRELY and would silently gut
    Principle I's zero-`mypy`-errors requirement across the whole test
    suite.
- Before making a red-phase commit, the author MUST run
  `--runxfail` SCOPED to the new tests, for example
  `uv run pytest --runxfail tests/path/to/new_test.py` or the specific
  node IDs. That flag disables `xfail` conversion and surfaces the
  real traceback, which is the only way to confirm that each
  red-phase test fails for the INTENDED reason rather than for an
  incidental one. The run MUST be scoped because this principle
  permits `xfail` markers to persist on `main` for the duration of a
  phase, so a bare `uv run pytest --runxfail` reports every
  pre-existing marker as a failure alongside the new ones and drowns
  the signal it is meant to produce.
- Strictness makes a test that unexpectedly passes report XPASS as a
  failure. That turns marker removal from a convention into a
  mechanically enforced gate: if the implementation commit forgets to
  drop a marker, CI fails. This project MUST NOT rely on developer
  discipline where tooling can enforce the rule.

**Marker hygiene**:

- Every test committed in a red-phase commit MUST carry an `xfail`
  marker whose `reason` names the unimplemented behavior and, where a
  spec exists, references the governing task or requirement ID. The
  example above shows the expected form: a `TDD red phase:` prefix, the
  task ID, and the behavior that does not yet exist. A bare
  `@pytest.mark.xfail` with no reason is PROHIBITED.
- The implementation commit MUST remove the `xfail` markers for the
  behavior it implements, in that same commit, together with the
  `# type: ignore[import-not-found]` comments on the imports that the
  implementation has now made resolvable. Deferring marker or ignore
  removal to a later commit is PROHIBITED. Both halves of that removal
  are tool-enforced: `xfail_strict` catches the forgotten marker as an
  XPASS failure, and `warn_unused_ignores` catches the forgotten
  ignore comment as an `unused-ignore` error.
- `xfail` MUST NOT be used to park a genuinely broken or flaky test
  indefinitely. It is a red-phase construct with a bounded lifetime:
  every `xfail` marker on `main` MUST have a corresponding open task or
  issue, and an `xfail` marker MUST NOT survive past the phase that
  implements its behavior.
- Tests that are intentionally inert MUST use `@pytest.mark.skip` with
  a documented reason. Disguising an inert test as a red-phase test is
  PROHIBITED.

**Every commit MUST leave the test suite green.** A clone of this
repository at ANY commit on `main` MUST produce a passing test run.
Commits that leave the suite red are PROHIBITED, including as
intermediate states within a pull request.

**Collection caveat**: an `xfail` marker only captures failures raised
during the setup or call phase of the test it decorates. A module-level
`import` of a not-yet-existing module breaks collection and fails the
suite before any marker can apply. Red-phase tests MUST therefore
import not-yet-existing modules inside the test function body, or
otherwise defer the import, so that the resulting `ImportError` is
recorded as an expected failure rather than a collection error.
`pytest.importorskip` MUST NOT be used for this purpose: it produces a
SKIP, which silently hides the missing behavior instead of tracking it.

Two consequences of that mechanism MUST be handled explicitly:

- **The deferred import MUST carry
  `# type: ignore[import-not-found]`.** Deferring the import defeats
  pytest collection but not `mypy`, which analyzes function bodies and
  defaults `ignore_missing_imports` to False. Without the ignore
  comment the `mypy` pre-commit hook reports
  `Cannot find implementation or library stub for module named ...`,
  and Principle I requires zero `mypy` errors while Principle V
  prohibits `--no-verify` — so the red-phase commit would be
  unmakeable. The ignore comment MUST be removed in the green-phase
  commit alongside the `xfail` marker.
- **Setup-phase failures are converted too, and `conftest.py` cannot be
  rescued at all.** Because pytest converts exceptions from the setup
  phase into XFAIL as well as those from the call phase, a fixture that
  raises during setup is silently absorbed — which is precisely why
  `raises=` is mandatory above. And a module-level import of a
  not-yet-existing module in a `conftest.py` breaks collection for that
  entire directory, where no marker can help. `conftest.py` MUST NOT
  import not-yet-existing modules at all.

**Exemptions**: this protocol governs commits that ADD or CHANGE
observable behavior. It does NOT apply to:

- Pure refactors that provably change no behavior and are already
  covered by existing passing tests.
- Documentation-only, CI-only, packaging-only, or configuration-only
  commits.
- Test-only commits that fix, clarify, or strengthen an existing test
  without asserting new production behavior.

Bug fixes are NOT exempt. A fix MUST be preceded by a red-phase commit
containing an `xfail`-marked regression test that reproduces the
defect.

**Rationale**: Every commit on `main` in this repository has to be
independently valid and clonable. This integration drives live
reservations, guest PII, and property-access workflows, so when a guest
reports a door code that did not work, `git bisect` is the first tool
reached for — and a bisect that lands on a knowingly broken tree burns
the incident window it was supposed to shorten. The same reasoning
covers CI run against an arbitrary ref and a future contributor cloning
at an arbitrary point in history. Committing the red phase separately
also makes TDD auditable: the history shows the expected-failing test
existing before the code that satisfies it, instead of an unverifiable
claim that it was written first. That audit is only trustworthy when
each red-phase marker pins its expected failure with `raises=`, since
an unpinned marker would absorb an incidental error and record a test
that never exercised the behavior it claims to define. Finally, the
protocol mechanically
reinforces Principle III — with tests and implementation forced into
separate commits, smuggling both into a single commit becomes
structurally impossible rather than merely discouraged.

## Additional Constraints

- **Language & Runtime**: Python 3.14, with full type annotation
  coverage enforced by `mypy` at `python3.14`.
- **Dependency Management**: Dependencies MUST be managed with `uv`,
  and `uv.lock` MUST be committed. Adding a dependency without updating
  the lock file in the same commit is PROHIBITED. Runtime dependencies
  MUST be kept minimal; the HTTP stack is `httpx`.
- **Test Stack**: Tests MUST use `pytest` with
  `pytest-homeassistant-custom-component` and MUST mock all Hospitable
  HTTP traffic with `respx`. `pyproject.toml` MUST set the following
  under `[tool.pytest.ini_options]`:

  ```toml
  [tool.pytest.ini_options]
  xfail_strict = true
  asyncio_mode = "auto"
  ```

  `xfail_strict` makes an unexpectedly passing red-phase test fail CI.
  `asyncio_mode = "auto"` is equally mandatory: without it an unmarked
  `async def` test never runs its body — when the marker pins
  `raises=` the test hard-fails as unsupported, and when it does not,
  that failure is silently converted to XFAIL (a false green). Both
  outcomes are wrong (Principle XII).
- **Static Analysis Settings**: `pyproject.toml` MUST set
  `warn_unused_ignores = true` under `[tool.mypy]`, or enable
  `strict = true`, which implies it. This is what mechanically forces
  the green-phase commit to remove the red-phase
  `# type: ignore[import-not-found]` comment, exactly as
  `xfail_strict` forces removal of the `xfail` marker (Principle XII).
  Narrowing this setting for tests MUST use
  `[[tool.mypy.overrides]] module = "tests.*"`; mypy's `exclude` MUST
  NOT be used, because it drops files from type checking entirely and
  would gut Principle I's zero-`mypy`-errors requirement.
- **Coverage Measurement**: Coverage MUST be measured over production
  code only:

  ```toml
  [tool.coverage.run]
  source = ["custom_components"]
  ```

  Measuring test files would make a legal red-phase commit
  mathematically impossible under any `fail_under` gate, because a
  red-phase test body legitimately aborts at its deferred import and
  leaves the remainder of the body unexecuted (Principle XII).
- **Lint Rule Compatibility**: Principle XII mandates function-body
  imports in red-phase tests. If ruff's rule selection ever includes
  `PLC0415` (`import-outside-top-level`), that rule MUST be disabled
  for `tests/**`, since it would otherwise flag every deferred import
  the red-phase protocol requires.
- **Home Assistant Compatibility**: The integration MUST follow Home
  Assistant custom component conventions, live under
  `custom_components/hospitable/`, and declare an accurate
  `manifest.json`. The minimum supported Home Assistant version MUST be
  declared and MUST NOT be raised without a release note.
- **HACS Distribution**: The repository MUST remain HACS-installable,
  with a valid `hacs.json` and brand assets under
  `custom_components/hospitable/brand/`.
- **Hospitable API Versioning**: The integration targets the Hospitable
  Public API v2, whose version is carried in the URL path. The targeted
  version MUST be documented, and any upstream breaking change MUST be
  absorbed in a dedicated migration phase rather than patched ad hoc
  across call sites.
- **Data Validation**: All data received from or sent to Hospitable
  MUST be validated against expected schemas. Silent data corruption is
  PROHIBITED.
- **License Compliance**: Every file MUST be covered by an SPDX header
  or a `REUSE.toml` entry, using the license appropriate to its path as
  defined in Principle IV.
- **Continuous Integration**: The `build-test`, `validate`, `codeql`,
  and `semantic-pull-request` workflows MUST pass on every pull
  request, as MUST the pre-commit.ci run (subject to the `mypy` and
  `aislop` skips noted in Principle V). The `openssf-scorecard`
  workflow is NOT a pull-request gate: it declares only
  `workflow_dispatch`, `branch_protection_rule`, `schedule` (weekly),
  and `push` to `main` triggers. Its score regressions MUST still be
  addressed, but they are detected after merge rather than blocking it.
  Dependency updates arrive via Dependabot and MUST clear the same
  gates as human changes.

## Development Workflow & Quality Gates

1. **Write tests** for the current phase or story, each marked
   `@pytest.mark.xfail(raises=..., reason="...", strict=True)` (TDD red
   phase).
2. **Run checks locally** — `uv run pytest tests/`,
   `uv run ruff check custom_components/ tests/`, and `uv run mypy`.
   The suite MUST be green, with the new tests reporting XFAIL.
3. **Verify the red phase is real** — run `--runxfail` scoped to the
   new tests, for example
   `uv run pytest --runxfail tests/path/to/new_test.py` (or the
   specific node IDs), and confirm from the resulting tracebacks that
   every new test fails for the INTENDED reason (the missing behavior)
   and not for a typo, a bad fixture name, or a wrong import path. The
   run MUST be scoped: Principle XII permits `xfail` markers to
   persist on `main` across a phase, so a bare
   `uv run pytest --runxfail` reports every pre-existing marker as a
   failure alongside the new ones and makes the check unusable. A test
   that fails for an incidental reason MUST be fixed before it is
   committed.
4. **Commit the tests on their own** as the red-phase commit; it MUST
   contain no production-code changes (Principle XII).
5. **Implement** the minimum code needed to pass those tests, and
   remove the `xfail` markers and the
   `# type: ignore[import-not-found]` comments the implementation
   satisfies (TDD green phase).
6. **Refactor** while keeping every test green.
7. **Re-run the same local checks.** The suite MUST be green, with the
   previously marked tests now passing outright.
8. **Stage and commit the implementation atomically**, with SPDX
   coverage, the `Co-authored-by` trailer when an agent contributed,
   and `-s` for DCO sign-off. The same trailer and sign-off
   requirements apply to the red-phase commit.
9. **Pre-commit hooks run automatically on BOTH commits** — the
   red-phase commit and the implementation commit alike. Fix any
   failures, re-stage, and commit again. Do NOT `git reset`. Do NOT use
   `--no-verify`. Note that `mypy` runs on the red-phase commit too,
   which is why the deferred import must carry its ignore comment
   (Principle XII).
10. **Open a pull request** with a Conventional Commit-formatted title;
    `semantic-pull-request` enforces this.
11. **CI MUST be green.** No manual or exploratory testing against a
    live Home Assistant instance is permitted until it is.
12. **Review MUST verify** constitutional compliance, atomic commit
    structure, red/green commit separation, licensing coverage,
    credential and PII hygiene, and agent co-authorship where
    applicable. Non-compliance blocks merge.
13. **Manual validation** may proceed only after all automated gates
    pass.

## Governance

- This constitution supersedes all other development practices. Where
  it conflicts with any other document, including `AGENTS.md`, this
  document prevails.
- Amendments MUST be documented with a version bump, an explicit
  rationale, and a migration plan when existing code is affected.
- Version increments follow semantic versioning:
  - **MAJOR**: Backward-incompatible principle removals or
    redefinitions.
  - **MINOR**: New principles, new sections, or materially expanded
    guidance.
  - **PATCH**: Clarifications, wording changes, and other non-semantic
    refinements.
- All pull requests and code reviews MUST verify compliance with these
  principles. Non-compliance MUST block merge.
- The Sync Impact Report comment at the top of this file records ONLY
  the most recent amendment; each `/speckit.constitution` run overwrites
  it. The authoritative, complete amendment history is the git history
  of this file, which Principle III keeps atomic and bisectable.
- All `.specify/templates/*.md` files MUST be reviewed for consistency
  whenever this constitution is amended, and any drift MUST be
  corrected — in the same change where doing so preserves commit
  atomicity, otherwise under a follow-up TODO recorded in the Sync
  Impact Report. Because `.specify/**` is MIT-licensed, upstream-owned
  Spec Kit material (Principle IV), any such correction is a local
  project overlay that a Spec Kit upgrade WILL overwrite and that MUST
  therefore be re-applied after every upstream Spec Kit upgrade.
- Claims about tooling in this document MUST match the repository's
  actual configuration. When `.pre-commit-config.yaml`, `.gitlint`,
  `REUSE.toml`, or the CI workflows change in a way that alters an
  enforced gate, this constitution MUST be amended to match.
- Use `AGENTS.md` for day-to-day runtime development guidance that
  supplements, but never overrides, this constitution.

**Version**: 1.1.1 | **Ratified**: 2026-08-06 | **Last Amended**: 2026-08-10
