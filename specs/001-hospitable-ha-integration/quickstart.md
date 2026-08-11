<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Quickstart: Validating the Hospitable Integration

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

This is a validation and run guide. It states how to prove each phase
works, not how to build it. Implementation belongs in `tasks.md` and
the implementation phase.

## Prerequisites

This guide applies from **US1 onward**. None of it is runnable at the
point the plan is merged: at that moment the repository holds
specification documents only, with no Python source, no
`pyproject.toml` and no `uv.lock`. US1 creates the project scaffolding
described here; every row below is a prerequisite for running the
checks, not a claim about the current tree.

| Requirement | Notes |
| --- | --- |
| Python 3.14 | Constitution, Additional Constraints |
| `uv` | The only supported dependency manager; `uv.lock` is committed from US1 onward |
| A checkout with pre-commit installed | `uv run pre-commit install` |
| Nothing else | **No live Hospitable account is needed or permitted for the test suite.** Every outbound HTTP call is mocked with `respx` (Principle II) |

Manual validation against a live account is permitted only after CI is
green (Principle I, workflow step 11). Live-account validation is
optional throughout; every automated check below runs offline.

## Setup

```bash
uv sync
uv run pre-commit install
```

## The standing check loop

Run these after every change. All three must be clean before a commit.

```bash
uv run pytest tests/
uv run ruff check custom_components/ tests/
uv run mypy
```

Expected: suite green, with any current red-phase tests reporting
XFAIL rather than FAIL.

## Verifying a red phase is real

Principle XII requires this **before** every red-phase commit. It is
the only way to confirm a new test fails for the intended reason rather
than a typo, a bad fixture name, or a wrong import path.

```bash
uv run pytest --runxfail tests/api/test_client.py::test_never_follows_link_urls
```

**The run must be scoped to the new tests.** `xfail` markers are
permitted to persist on `main` for the duration of a phase, so a bare
`uv run pytest --runxfail` reports every pre-existing marker as a
failure and drowns the signal.

Read the resulting traceback and confirm the failure is the missing
behavior. A red-phase test that fails for an incidental reason is a
defect and must be fixed before it is committed.

## Verifying the green phase removed its markers

The green-phase commit must remove the `xfail` markers and the
`# type: ignore[import-not-found]` comments for the behavior it
implements, in that same commit. Both halves are tool-enforced:

```bash
uv run pytest tests/   # xfail_strict turns a forgotten marker into an XPASS failure
uv run mypy            # warn_unused_ignores reports a forgotten ignore comment
```

A forgotten marker fails as XPASS. A forgotten ignore comment fails as
`Unused "type: ignore" comment [unused-ignore]`. Neither depends on
anyone remembering.

Where a second red-phase test imports a not-yet-existing *name* from a
now-existing module, its ignore comment must be **re-coded** from
`import-not-found` to `attr-defined`, not merely retained.

## Verifying the PII guard

The fixture guard is itself tested, because a guard nobody has watched
fail is a guard nobody knows works.

```bash
uv run pre-commit run check-fixture-pii --all-files
```

Expected: pass over the committed fixture set.

Then prove it fires. Add a fixture containing a non-example-domain
email address, stage it, and confirm the hook fails naming the file,
the line, and the rule. Discard the poisoned fixture afterwards. The
suite also carries an automated equivalent, so this manual step is a
confidence check rather than the primary evidence.

**Do not bypass the hook.** `--no-verify` is prohibited under all
circumstances (Principle V).

## Per-phase validation

Each phase is one pull request. A phase is done when its scenarios pass
**and** the full CI suite is green (Principle IX).

### US1 — Connect an account and pick properties

Requirements: FR-001 to FR-016, FR-024 to FR-041, FR-050, FR-055,
FR-063, FR-066, FR-069, FR-070, FR-073 to FR-075.

| Scenario | Expected |
| --- | --- |
| Valid token submitted | Advances to property selection |
| Rejected token submitted | Error naming both causes — invalid or expired token, or a plan without Public API access — and where to generate a replacement; form stays editable |
| Two of five properties selected | Exactly two devices created; only those two polled |
| No property selected | Flow refuses to finish, explains at least one is required |
| Account with no properties | Reports none found; no empty selector |
| Same account added twice | Aborts as already configured |
| Fixture serves `http://` pagination links | The client never requests them; the poisoned route raises if touched |
| Fixture omits the `listings` include | Warning logged once; `listings_available` is `False`; refresh still succeeds |
| Fixture returns 403 with a scope reason | No retry, no reauth, no repair issue |
| Fixture returns 403 without a scope reason | Repair issue raised; still no reauth |
| Fixture returns 401 | Reauth raised |
| Diagnostics downloaded | No token, no personal data, response skeletons present |
| Entry unloaded | Every coordinator, task, listener, and HTTP client torn down |

**Live probe task, required before the US1 green phase.** Assumption
A-1 in [research.md](./research.md#a-1-reservation-date-filter-mode-parameter)
is resolved: `date_query=checkin` is sent explicitly on every
reservation query, even though it currently matches the platform
default. The same session pins any remaining UNVERIFIED rows of the
[field binding table](./data-model.md#field-binding-table).

### US2 — Reservation status per property

Requirements: FR-042 to FR-049, FR-057.

| Scenario | Expected |
| --- | --- |
| Accepted reservation, arrival in the future | `awaiting_checkin`, with the FR-046 attributes populated |
| Accepted, check-in time passed, check-out not reached | `occupied` |
| No reservation in the window | `no_reservation`, and the entity is **available** |
| Reservation cancelled upstream | State reflects it within one polling interval |
| Several reservations in the window | One selected per FR-044; the rest in `upcoming_reservations` |
| Unrecognized status value | `unknown`, logged once per distinct value, no raise |
| Owner stay | `stay_type` reports an owner stay; the state follows the same rules as a guest stay |
| Arrives today, check-in time later today | `awaiting_checkin`, **never** `occupied` |
| Departs today, check-out time earlier today | `checked_out`, **never** `occupied` |
| Arrival or departure date with an unparsable scheduled time | `unknown`, warning naming the reservation and the field, **never** `occupied`, **never** a midnight substitute |
| Same reservation three days into the stay, unparsable time | `occupied` — the degradation is scoped to the two boundary dates |
| Two equally ranked reservations | Selection is deterministic by ascending reservation identifier across repeated refreshes |
| Two consecutive failed polls | Entity available, last known values retained |
| Three consecutive failed polls | Entity unavailable |

The midnight-substitution scenario is a **negative** assertion. Test
that the state is `unknown`, not merely that it is "not occupied" —
`awaiting_checkin` would also satisfy the weaker assertion while being
exactly the midnight-fallback bug FR-045 prohibits.

### US3 — Property details

Requirements: FR-050 to FR-056, FR-074.

| Scenario | Expected |
| --- | --- |
| Property with future reservations | `next_arrival` and `next_departure` report the correct moments |
| Property with no future reservations | Both report no value, not a stale one |
| Property renamed upstream | Display name updates; entity identifiers and history preserved |
| Property with several channel listings | All represented with channel and channel identifier |
| Property deleted or unshared upstream | Entities unavailable with a reason; registry entries retained |
| Per-property IANA override set | Day-boundary presentation uses the override; `timezone_source` reports `override` |
| No override set | The Home Assistant instance timezone is used; `timezone_source` reports `instance` |
| Fixture property carries `timezone: "-0700"` | That value influences nothing; the model has no such attribute |
| Invalid IANA override submitted | Rejected with a message naming the expected form |

The `-0700` scenario is a regression guard for
[research.md D-11](./research.md#d-11). Assert on the attribute's
absence, not just on behavior, so reintroducing the field fails
immediately.

**OQ-004 verification task.** Confirm whether reservations on unlisted
or unpublished channel listings are absent from `/reservations`. If
confirmed, document it in the user-facing README. The detection signal
is a disagreement between the availability sensor, which reads the
aggregate calendar covering every channel, and the reservation status
sensor.

### US4 — Polling cadence and window

Requirements: FR-015 to FR-023, FR-072.

| Scenario | Expected |
| --- | --- |
| Options screen opened | Both intervals, both window bounds, the property selection, and the timezone overrides are editable and show current values |
| Interval below its floor submitted | Rejected with a message naming the minimum |
| Window bound out of range submitted | Rejected with a message naming the bound |
| Lookback widened | Next poll retrieves the additional history, with no restart |
| Any option changed | Takes effect on the next poll, with no restart |
| Properties changed | New ones gain devices and entities; deselected ones stop polling and go unavailable; **every** property's identifiers and history are preserved |
| Any value edited | The request-per-day estimate updates and is labelled an estimate |
| Estimate at defaults, ten properties, 500 reservations | Reports 1,704, under the SC-004 ceiling of 2,000 |

The deselection scenario is non-destructive in both directions.
Reselecting a property must restore its original entity identifiers and
its recorder history.

Known limitations:

- The request-per-day estimate recomputes on the next server render of
  the options form, not live as a field changes. Home Assistant config
  forms re-render server-side, so "updates as any value is edited"
  means "updates on the next render" — the only behaviour the platform
  supports.
- A new timezone override cannot be set for a property in the same
  submission that first selects it: the override field is only rendered
  for already-selected properties. Select the property and save, then
  reopen the options to set its override. Previously-saved overrides
  for deselected properties are retained across saves.

### US5 — Multiple accounts

Requirements: FR-012, FR-013, FR-055.

| Scenario | Expected |
| --- | --- |
| Two entries, two accounts | Both operate independently; every entity is uniquely addressable |
| Same account added twice | Refused, explaining it is already configured |
| One entry's token rejected | Only that entry enters reauthentication; the other keeps polling |
| Five entries configured | Zero unique-ID collisions (SC-010) |
| Two accounts, identically named properties | No collision; identity derives from the namespace and property identifier, never a name |
| Reauth token belongs to a different account | Aborted, not silently accepted |

Much of US5 is proven by construction in US1's namespacing. This phase
delivers the multi-entry **evidence**, plus any fix the evidence
forces. Test-only strengthening of an existing test is exempt from the
red-phase protocol; any behavior change it uncovers is not.

### US6 — Token expiry and recovery

Requirements: FR-014, FR-038, FR-064, FR-065.

| Scenario | Expected |
| --- | --- |
| Token revoked, next poll returns 401 | Reauth prompt naming the token as the cause and where to replace it |
| Replacement token supplied | Polling resumes; prompt clears; entities and history retained |
| Scope-related 403 | Capability reported as unavailable; **no** reauth and **no** repair issue |
| Non-scope 403 | Repair issue; still no reauth |
| 403 body absent or unparsable | Classified as non-scope; repair issue; no reauth |
| Persistent non-credential failure | Repair issue |
| Every user-facing message | States what failed and what to do; no bare status codes |

The unparsable-body scenario is the one that catches a permissive
classifier. It must land on the non-scope branch.

Verified (US6 suite, all green):

- Token revoked, next poll returns 401 — `test_reauth_trigger.py`
  drives a real coordinator refresh returning 401 and asserts a reauth
  flow is in progress whose form prompt names the account.
- Replacement token supplied — `test_config_flow.py`
  (`test_reauth_replaces_token_for_same_account_only`) confirms the
  token is replaced and the account namespace is retained.
- Scope-related 403 — `test_scope_403_handling.py` asserts no reauth,
  no repair issue, a single capability log, and `last_update_success`
  stays true.
- Non-scope 403 — `test_non_scope_403_handling.py` asserts one repair
  issue and no reauth.
- 403 body absent or unparsable — `test_403_unparsable_default.py`
  guards the `classify_403` fail-safe default and the client error path.
- Persistent non-credential failure — `test_persistent_failure_repair.py`
  escalates three consecutive 5xx polls to one repair issue.
- Every user-facing message — `test_error_message_quality.py` audits
  every config/options error, abort, and repair-issue string for a
  cause and an action, rejecting bare status codes and exception reprs.
- Setup never fails silently — `test_setup_failure_visibility.py`
  asserts a setup 401 does not load the entry and a setup 5xx yields
  SETUP_RETRY.

### US7 — Availability and pricing, read-only

Requirements: FR-058 to FR-061.

| Scenario | Expected |
| --- | --- |
| Open night today | `available`, carrying the nightly rate and currency |
| Booked today through any channel | `booked` — **never** the string `unavailable` |
| Rate returned as integer minor units | Converted exactly once, in the sensor; the model never carries a float |
| Forward window | Available as attributes |
| Calendar refresh cadence | Property cadence, not reservation cadence |
| One property's calendar fetch fails | Only that property's availability sensor degrades; the others refresh normally |
| Full lifecycle: setup, refresh, options change, unload | **Zero** non-`GET` requests issued |

The zero-writes assertion is the FR-059 proof. It is a whole-lifecycle
assertion over the `respx` router rather than a review promise, because
FR-059 is absolute.

Outcome (implemented and verified in `feat/us7-availability`):

- Open night today → `available`, carrying `nightly_rate` and
  `currency` attributes. Verified by an end-to-end state-machine test.
- Booked today → `booked`, and the entity is simultaneously asserted to
  not be in Home Assistant's `unavailable` state, so a sold night is
  never conflated with a broken integration.
- Integer minor units → the model field is an `int` and the sensor is
  the single conversion point via `minor_units_to_float`; a `6001`
  minor-unit value renders exactly, guarding against early float
  arithmetic.
- Property cadence (60-minute default, 15-minute floor) confirmed.
- One property's 500 leaves the survivors' data present and correct and
  the properties coordinator's `last_update_success` and
  `consecutive_failures` untouched. The failing property retains its
  last-good calendar through two strikes and its availability sensor
  degrades to `unavailable` on the third consecutive per-property
  failure (D-15, FR-057), recovering when a fetch next succeeds.
- Full lifecycle (setup, refresh every coordinator, options change,
  reload, unload) records only `GET` requests.

Known limitations:

- Today the live API only reports `AVAILABLE`/`RESERVED`, so an
  unavailable night that is a host block rather than a guest booking
  maps to the honest `unknown` state, not `booked`. That defensive
  branch is proven with a synthetic fixture carrying an unrecognised
  reason; it exists to be correct if the vocabulary widens, not because
  the value appears in production data today.
- The nightly rate reflects the aggregate calendar across every sales
  channel. The response `listing_id` and `provider` are cosmetic and are
  never surfaced as a scope, so the rate must not be read as
  channel-specific.

## Cross-cutting checks

Run at the end of every phase.

| Check | Requirement | Phase 10 outcome |
| --- | --- | --- |
| No `unavailable` string in any enum option list | FR-047, FR-058 | PASS. Grep over `custom_components/hospitable/sensor` found no enum option list containing `unavailable`. |
| No non-`GET` request in any test recording | FR-059 | PASS. `tests/test_no_writes.py::test_full_lifecycle_issues_only_get_requests` records setup, refresh, reload, and unload, then asserts every captured method is `GET`. |
| No request to a body-supplied URL | FR-026 | PASS. `tests/api/test_pagination.py::test_pagination_constructs_https_pages` poisons the `http://` body link and asserts constructed HTTPS page requests. |
| No `include=guests`, no `status[]`, no calendar `listing_id` | Honored-Request Verification register | PASS. `tests/api/test_reservations.py` asserts reservation queries omit `include=guests`, `status[]`, `date_type`, and `filter_date_type`; `tests/api/test_calendar.py` asserts calendar queries omit `listing_id`. |
| No bare `zoneinfo.ZoneInfo(...)` construction | Principle VIII, SC-013 | PASS. Grep over `custom_components/hospitable` and `tests` found no `ZoneInfo(` construction. |
| No `property.timezone` read anywhere | FR-074 | PASS. Grep over `custom_components/hospitable` and `tests` found no `property.timezone` read. |
| Diagnostics and DEBUG logs contain no fixture personal data and no token | FR-062, FR-073, SC-008 | PASS. `tests/test_diagnostics.py::test_diagnostics_redacts_tokens_and_personal_data`, `tests/test_privacy.py::test_privacy_audit_helpers`, and `tests/test_check_fixture_pii.py` passed. |
| `interrogate --fail-under=100` clean | Principle I | PASS. `uv run interrogate --fail-under=100 custom_components/ tests/ --quiet` exited 0. |
| Coverage over `custom_components/` maintained or increased | Principle I | PASS. `uv run pytest --cov=custom_components --cov-report=term-missing tests/` passed 164 tests and reported 95% total coverage. |
| Every `xfail` marker on `main` has an open task | Principle XII | MIXED. Executable code and tests have zero `pytest.mark.xfail` or `type: ignore[import-not-found]` matches. A whole-repository grep still finds those literal strings in governance/specification prose, including `.specify/memory/constitution.md`, which Phase 10 must not edit; `xfail_strict` does not apply to Markdown prose. |

## Live validation

Run on 2026-08-11T17:32Z by the project manager against a live account
with 13 properties for the window 2026-05-13 through 2026-11-09. No
live response body is committed here.

Property inventory returned 13 properties with `meta.total` 13. An
earlier probe that saw 10 properties did not paginate past the default
page size; the integration client paginates via `meta.last_page`, so
that probe was not evidence of a code defect.

| Criterion | Final live result |
| --- | --- |
| SC-001 setup under three minutes | **NOT MEASURED.** This requires a human walking the config flow UI. |
| SC-002 change reflected within one polling interval for 95% of observations | **PARTIALLY SUPPORTED.** Feasibility was measured only: a reservation poll took 0.77 s against the five-minute default interval. The 95%-of-observations claim was not measured because no live reservation was mutated and observed over time. |
| SC-003 full refresh under 30 seconds | **PASS.** Sequential wall-clock total was 15.23 s: properties 0.56 s; the first reservations page 0.77 s with response metadata reporting 208 total reservations and `last_page` 3; and 13 calendar requests 13.89 s returning 2,353 day-records, all 13 succeeding. This is an upper bound because the probe was sequential while the integration fetches calendars concurrently. |
| SC-005 30 consecutive days unattended | **NOT MEASURED.** This requires 30 days of elapsed runtime. |
| SC-006 rename preserves identifiers and history | **PASS by construction, supported by live data.** Property `id` is a 36-character opaque string. The live account had 13 distinct ids and 13 distinct names, and `id` is independent of `name`. Entity unique ids and device identifiers derive from the account namespace plus property id, never from the display name, through `build_unique_id` and `build_device_identifier` in `custom_components/hospitable/entity.py`; `tests/sensor/test_rename_stability.py::test_rename_preserves_identifiers` covers the rename path. |
| SC-013 no operation blocks the event loop over 100 ms | **PASS by source audit, not profiling.** Static scanning of `custom_components/hospitable/` found no blocking I/O: no `open(`, no `time.sleep`, no `subprocess`, no synchronous `requests`, and no bare `zoneinfo.ZoneInfo(...)` construction. All upstream I/O goes through the async `httpx` client. True event-loop profiling on Raspberry-Pi-class hardware was not performed. |

Incidental A-7 recheck: the `GET /properties` response carried
`x-hospitable-trace` but no `X-RateLimit-*` and no `Retry-After`,
consistent with the existing A-7 finding.

**Never commit a live response**, even redacted. Fixtures mirror
observed shapes with invented values, and a redaction slip in a fixture
is permanent in git history.

## Red-phase machinery verification

Run these commands before relying on red-phase commits:

```shell
uv run pytest tests/test_red_phase_contract.py::test_xfail_strict_unexpected_pass
uv run pytest tests/test_red_phase_contract.py::test_asyncio_auto_executes_async_tests
uv run mypy tests/typecheck_unused_ignore_sample.py
```

The first command must fail because `xfail_strict = true` turns an
unexpected pass into a failure. The second proves async tests execute
under `asyncio_mode = "auto"`. The third must report an unused ignore
when the temporary sample contains a stale `# type: ignore`.
