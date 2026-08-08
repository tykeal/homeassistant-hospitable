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
assumes the reservation date-filter mode parameter's name and value.
Issue the same reservation query twice against a live account, once
with a deliberately bogus mode value, and compare result sets.
Identical results prove the parameter is silently ignored, which moves
it to NEVER SENT in the
[upstream-requests](./contracts/upstream-requests.md) register and
makes the client's local window filter authoritative. Differing results
confirm it is honored and pin the value in `api/const.py`. Record the
outcome in `research.md`. The same session pins every UNVERIFIED row of
the [field binding table](./data-model.md#field-binding-table).

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
| Per-property IANA override set | Arrival and departure timestamps use the override; `timezone_source` reports `override` |
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

## Cross-cutting checks

Run at the end of every phase.

| Check | Requirement |
| --- | --- |
| No `unavailable` string in any enum option list | FR-047, FR-058 |
| No non-`GET` request in any test recording | FR-059 |
| No request to a body-supplied URL | FR-026 |
| No `include=guests`, no `status[]`, no calendar `listing_id` | Honored-Request Verification register |
| No bare `zoneinfo.ZoneInfo(...)` construction | Principle VIII, SC-013 |
| No `property.timezone` read anywhere | FR-074 |
| Diagnostics and DEBUG logs contain no fixture personal data and no token | FR-062, FR-073, SC-008 |
| `interrogate --fail-under=100` clean | Principle I |
| Coverage over `custom_components/` maintained or increased | Principle I |
| Every `xfail` marker on `main` has an open task | Principle XII |

## Optional live validation

Only after CI is green, and only with a token from an account the
validator owns.

| Step | Notes |
| --- | --- |
| Complete setup end to end | SC-001 targets under three minutes |
| Change a reservation upstream | SC-002 targets reflection within one interval |
| Time a full refresh with ten properties | SC-003 targets under thirty seconds |
| Leave it running | SC-005 targets thirty days without intervention |
| Rename a property upstream | SC-006 requires 100% identifier and history preservation |

**Never commit a live response**, even redacted. Fixtures mirror
observed shapes with invented values, and a redaction slip in a fixture
is permanent in git history.
