<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Implementation Plan: Hospitable Home Assistant Integration

**Branch**: `001-hospitable-ha-integration` | **Date**: 2026-08-08 |
**Spec**: [spec.md](./spec.md)

**Input**: Feature specification from
`/specs/001-hospitable-ha-integration/spec.md`

## Summary

Deliver the first Home Assistant custom integration for Hospitable: a
read-only, polling-only, Personal Access Token integration that exposes
one device and six sensor entities per selected property, across seven
independently shippable phases.

The technical approach is shaped by three forces:

1. **The upstream API silently ignores inputs.** Three independent
   silent-ignore behaviors are CONFIRMED — a bogus calendar
   `listing_id`, an invalid `include=` name, and pagination URLs
   returned with an `http://` scheme. The client therefore treats HTTP
   200 as insufficient proof that a request was honored, and every
   optional input carries either a post-condition assertion or a
   documented prohibition. This is a first-class design concern, not a
   note.
2. **Personal data is everywhere and is not this software's to leak.**
   Guests, account holders, co-hosts, and channel logins all appear in
   payloads. The design drops personal fields at the model boundary
   rather than redacting them at the sink, and diagnostics use an
   allowlist because FR-073 explicitly binds endpoints added by later
   specifications.
3. **Occupancy has to be derived, and derived exactly.** Hospitable
   publishes no checked-in status. Occupancy comes from scheduled
   moments in a real IANA timezone, and a missing scheduled time is a
   data error that produces `unknown`, never a midnight fallback.

Three coordinators run on two user-facing intervals. Reservations
refresh on their own interval; properties and the calendar share the
second interval but are separate coordinators so that the calendar's
per-property fan-out cannot degrade the cheap single-request property
refresh.

## Technical Context

Everything in this section describes the **target state established by
US1 and maintained thereafter**, not the current tree. At the time this
plan is written the repository contains specification documents only —
no Python source, no `pyproject.toml`, no `uv.lock`. Each item below is
an implementation target that the phases in
[Phase breakdown](#phase-breakdown) are responsible for
reaching.

**Language/Version**: Python 3.14, fully type annotated, `mypy` at
`python3.14` with zero errors.

**Primary Dependencies**: `httpx` — and nothing else at runtime. The
pragmatic dependency policy was applied and its honest outcome is zero
additional helpers; see [research.md D-03](./research.md#d-03) for the
retry and serialization libraries considered and why each was rejected.
`zoneinfo` is standard library.

**Storage**: Home Assistant config entry storage only. The Personal
Access Token lives there and nowhere else (FR-003). No
integration-managed file, environment variable, or custom store.

**Testing**: `pytest` with `pytest-homeassistant-custom-component`, all
outbound HTTP mocked with `respx`. `xfail_strict = true`,
`asyncio_mode = "auto"`. No test requires a live Hospitable account.

**Target Platform**: Home Assistant 2026.8.0 and later, installed
through HACS, running on hardware down to Raspberry-Pi class.

**Project Type**: Home Assistant custom integration (single Python
package under `custom_components/hospitable/`).

**Performance Goals**: A full refresh for ten properties under thirty
seconds (SC-003). Fewer than 2,000 upstream requests per day at
defaults with ten properties and 500 reservations in the window
(SC-004); the design's arithmetic lands at 1,704. No operation blocks
the event loop for more than 100 ms (SC-013).

**Constraints**: Read-only — no write request of any kind, and calendar
writes are prohibited absolutely (FR-059). Polling only; no webhook
dependency (FR-067). Sensor platform only (FR-054). No Home Assistant
services registered (FR-069). Reservation interval floor one minute,
property interval floor fifteen minutes, neither lowerable by
configuration.

**Scale/Scope**: Tens of properties per config entry, several config
entries per Home Assistant instance. 75 functional requirements, 7 user
stories delivered as 7 pull requests, roughly 30 production modules.

**Unknowns**: No `NEEDS CLARIFICATION` markers remain. Eight
assumptions rest on UNVERIFIED upstream behavior; each is isolated,
tiered, and given a concrete fallback in
[research.md](./research.md#assumptions-on-unverified-upstream-behavior).
None is treated as CONFIRMED anywhere in the design.

## Constitution Check

*GATE: evaluated before Phase 0 and re-evaluated after Phase 1 design.
Both evaluations reached the same result.*

**Result: PASS, with two items recorded in Complexity Tracking and
three deviations from planning instructions recorded separately below.
No constitutional principle is violated or waived.**

| Principle | Status | How this design satisfies it |
| --- | --- | --- |
| I. Code Quality & Testing | PASS | `ruff-check`, `ruff-format`, `mypy`, `interrogate --fail-under=100` all clean. Every module, function, and class carries a docstring. Unit-level TDD is deferred nowhere; every phase opens with a red-phase commit. Coverage measured over `custom_components/` only |
| II. API Client Design | PASS | All HTTP isolated in `api/`; coordinators and entities construct no requests. API version is one constant in `api/const.py`. PAT sits behind a single credential interface so adding OAuth is an internal change (FR-008). A vendor-gated 403 is a capability boundary, never an auth failure. No quota hard-coded, no rate-limit header assumed. Pagination exposed as an async generator. Typed exceptions carry status, endpoint, and a redacted excerpt. All HTTP mocked with `respx`; no test needs a live account. Malformed shapes raise |
| III. Atomic Commits | PASS | One logical change per commit; every commit leaves the tree working. Conventional Commits with capitalized types, subjects within 50 characters, bodies wrapped at 72 by hand. `tasks.md` updates committed separately from the code they track. No direct commits to `main` |
| IV. Licensing | PASS | Python files carry inline SPDX headers. `tests/fixtures/**` is JSON and cannot, so a `REUSE.toml` annotation lands in the same commit that creates the path. `custom_components/hospitable/brand/**` is CC-BY-SA-4.0; `custom_components/**/*.json` and `hacs.json` are already annotated |
| V. Pre-Commit Integrity | PASS | No `--no-verify`, ever. A new local hook, `check-fixture-pii`, joins the enforced set. On failure: fix, `git add`, commit again — never `git reset`. `mypy` and `aislop` are local-only, so the local run is mandatory in practice as well as principle |
| VI. Agent Co-Authorship & DCO | PASS | Every commit uses `git commit -s` and carries `Co-authored-by: Copilot`. Author and committer remain the human contributor's signing identity; no `user.name` or `user.email` is set at any scope |
| VII. User Experience Consistency | PASS | The config flow implements the user step, a reauth flow, and an options flow — the stated minimum — from the first shippable release. PAT is offered without exposing credential-model jargon, and the design does not preclude OAuth. Entity IDs follow `sensor.hospitable_<property>_<attribute>`. Unique IDs derive only from immutable identifiers. Attribute contracts are documented and frozen. Error messages name the remedy, and a scope limitation is never described as a credential problem |
| VIII. Performance | PASS | All I/O async on `httpx`; no blocking call. Timezone lookups go through `dt_util.async_get_time_zone`, never a bare `ZoneInfo(...)`. Intervals configurable with unlowerable floors. Conservative defaults with 429 backoff and no assumed quota. Coordinators batch and share; entities never poll. Reservation retention bounded by the window. Every client, listener, and task torn down on unload |
| IX. Phased Development | PASS | Seven phases, one per user story, each independently testable and shippable. Unit-level TDD deferred nowhere. Each phase ends at a green-CI checkpoint. Phase boundaries and exit criteria are documented below and carry into `tasks.md`. The API client layer is delivered and proven in US1 before any dependent platform is built |
| X. Security & Credentials | PASS | No credential in source, tests, or fixtures — enforced by `detect-private-key` plus the new PII guard. Token in config entry storage only. Reauth on 401; **never** on a scope-403, with the classifier defaulting to the non-scope branch. Pagination URLs never followed verbatim, with a `respx` test that raises if they ever are. Credentials and personal data redacted from logs, diagnostics, and exception text — and mostly never read at all |
| XI. Webhooks & Real-Time Events | NOT APPLICABLE | This feature is polling-only (FR-067) and webhooks are explicitly out of scope with their own future specification. No webhook endpoint, handler, or signature verification is introduced, so no obligation under this principle is engaged. This is inapplicability, not a waiver — the principle binds fully whenever webhooks are added |
| XII. Red-Phase Commit Protocol | PASS | Every phase is a red-phase commit followed by a green-phase commit. Every marker is `@pytest.mark.xfail(raises=..., strict=True, reason="TDD red phase: ...")`. `xfail_strict` and `warn_unused_ignores` are set in `pyproject.toml` from the commit that creates it. Imports deferred into test bodies with `# type: ignore[import-not-found]`, re-coded to `attr-defined` where the module exists but the name does not. `conftest.py` imports no not-yet-existing module. `--runxfail` scoped to new tests before every red-phase commit. Every commit leaves the suite green |

**Additional Constraints check**: Python 3.14; `uv` with a committed
`uv.lock`; `pytest` plus `pytest-homeassistant-custom-component` plus
`respx`; `xfail_strict` and `asyncio_mode` set; `warn_unused_ignores`
set, narrowed for tests only via `[[tool.mypy.overrides]]` and never
via `exclude`; coverage sourced from `custom_components`; `PLC0415`
disabled for `tests/**` if ruff's selection ever includes it; the
integration under `custom_components/hospitable/` with an accurate
`manifest.json` declaring 2026.8.0; HACS-installable with `hacs.json`
and brand assets; the API version documented as one constant; all data
validated; REUSE-compliant; the pull-request gates green.

## Decision deviations

Recorded plainly rather than absorbed, because a plan that quietly
reinterprets its instructions is worse than one that argues with them.

### Deviation 1: the calendar surface

**Instruction**: "calendar data appears as attributes on the existing
per-property sensor. No new platform."

**What this plan does**: honors "no new platform" exactly — no Home
Assistant `calendar` entity, sensor platform only. It does **not** put
availability on an existing sensor's attributes. It creates one
additional sensor entity, `availability`, per property.

**Why**: FR-058 requires an availability *state* and prohibits the
string `unavailable` for a booked night on the grounds that Home
Assistant reserves that value. That reasoning is only meaningful about
an entity state; an attribute has no interaction with Home Assistant's
reserved value, so the prohibition would be vacuous under an
attribute-only design. US7 acceptance scenarios 1 and 2 both describe
"the availability sensor" reporting a value. Folding it into the
reservation status sensor's state is independently prohibited by
FR-043, which declares that enum single-dimensional. The specification
is the authoritative input, so it governs.

**Cost of being wrong**: one extra entity per property. Reversible
without a unique-ID migration, since removing one entity key does not
disturb the others.

### Deviation 2: which coordinators US1 wires into setup

**Instruction**: "US1's PR carries the foundation — the api client, the
coordinators, and the config flow."

**What this plan does**: US1's diff contains all three coordinator
classes, fully implemented and unit-tested against synthetic fixtures.
Only the properties coordinator is instantiated and refreshed by
`async_setup_entry` in US1. The reservations coordinator is wired in
US2 and the calendar coordinator in US7, alongside the entities that
consume them.

**Why**: US1 creates no entity that reads reservation or calendar data.
Wiring both into setup would ship a release spending roughly 1,700
upstream requests per day to display nothing, contradicting US1's own
"independently shippable" standard and FR-071's economy requirement.
Principle IX's demand that "the API client layer MUST be delivered and
proven before dependent Home Assistant platforms are built" is
satisfied by the classes existing and being proven under test, which is
exactly what US1 delivers.

**This is a scoping reading, not a reversal.** Both coordinators land
in the US1 diff.

### Deviation 3: the Hostaway `services/` precedent

The briefing states that the sibling Hostaway integration's `services/`
package is domain logic rather than Home Assistant service
registration. **It is not.** Hostaway's `services/__init__.py` defines
`async_setup_services` and registers nine Home Assistant services.

This changes nothing about this integration: FR-069 defines `services/`
for *this* project as domain logic and states explicitly that it is not
HA service registration, and this feature registers no Home Assistant
service. The correction is recorded so the reference implementation is
not mis-cited later as precedent for the opposite.

### A spec-internal tension: FR-033 and `include=guests`

Not a deviation from an instruction, but worth surfacing. FR-033 says
the integration "MUST request guest information as an include on the
reservation query". The specification's own confirmed expansion table
lists `guests` under "tested no-ops or invalid names" for
`/reservations`.

Both are satisfied because FR-033 is conditional on guest data being
surfaced, and this feature surfaces none — FR-046 lists guest *counts*,
never identities. The include is therefore not sent, and the
prohibition is recorded in the Honored-Request Verification register
so a future contributor does not send `include=guests` on the strength
of FR-033's first clause and receive a silent no-op. See
[research.md D-06](./research.md#d-06).

## Project Structure

### Documentation (this feature)

```text
specs/001-hospitable-ha-integration/
├── spec.md                          # Input (merged, authoritative)
├── plan.md                          # This file
├── research.md                      # Phase 0: decisions and assumptions
├── data-model.md                    # Phase 1: models, entities, entry
├── quickstart.md                    # Phase 1: validation guide
├── contracts/                       # Phase 1: interface contracts
│   ├── upstream-requests.md
│   ├── entities.md
│   ├── config-entry.md
│   └── errors-and-diagnostics.md
├── checklists/
│   └── requirements.md              # Existing
└── tasks.md                         # Phase 2 (NOT created by this command)
```

### Source Code (repository root)

```text
custom_components/hospitable/
├── __init__.py                # setup, unload, async_migrate_entry
├── const.py                   # DOMAIN, defaults, floors, option keys
├── config_flow.py             # user, properties, reauth_confirm, options
├── coordinator.py             # the three DataUpdateCoordinator subclasses
├── entity.py                  # base entity, device info, availability mixin
├── diagnostics.py             # allowlist-based diagnostics (FR-063)
├── manifest.json
├── strings.json
├── translations/
│   └── en.json
├── brand/                     # CC-BY-SA-4.0
├── api/                       # all HTTP lives here; nothing else builds requests
│   ├── __init__.py            # public re-exports
│   ├── const.py               # base URL, API version, page and batch ceilings
│   ├── exceptions.py          # the typed hierarchy
│   ├── auth.py                # credential interface; PAT today, OAuth-addable
│   ├── redaction.py           # denylist plus value sweep
│   ├── retry.py               # bounded jittered backoff, Retry-After aware
│   ├── responses.py           # envelope parsing and post-condition asserts
│   ├── models.py              # frozen dataclasses with from_api()
│   ├── client.py              # httpx transport, pagination, retry, errors
│   ├── properties.py          # /properties and /properties/{id}/calendar
│   └── reservations.py        # /reservations batching and merging
├── services/                  # DOMAIN LOGIC (FR-069) — not HA service calls
│   ├── __init__.py
│   ├── status.py              # upstream category to state enum (FR-043, FR-048)
│   ├── occupancy.py           # scheduled-moment derivation (FR-045)
│   ├── selection.py           # most-relevant reservation (FR-044)
│   ├── window.py              # lookback and lookahead computation (FR-021)
│   ├── timezones.py           # effective IANA zone resolution (FR-074)
│   └── estimator.py           # requests-per-day estimate (FR-072)
└── sensor/
    ├── __init__.py            # platform setup, entity construction
    ├── helpers.py             # attribute builders shared across sensors
    ├── reservation.py         # reservation_status
    ├── property.py            # next_arrival, next_departure, count, info
    └── availability.py        # availability (US7)

tests/
├── conftest.py                # imports NO not-yet-existing module
├── helpers.py
├── fixtures/                  # synthetic JSON; guarded by check-fixture-pii
├── api/
├── services/
├── sensor/
├── test_config_flow.py
├── test_coordinator.py
├── test_diagnostics.py
├── test_init.py
└── test_privacy.py            # the SC-008 leak audit

scripts/
└── check_fixture_pii.py       # the local pre-commit guard

pyproject.toml
uv.lock
hacs.json
```

**Structure Decision**: A single Home Assistant custom integration
package. The `api` / `services` / `sensor` split is not a preference —
FR-069 makes it a binding constraint from the first commit, because
later specifications will add domains that assume it, and because the
`services` name collides with a reserved Home Assistant term and needs
defining once, centrally. `services/` here holds reservation selection,
occupancy derivation, status mapping, window computation, timezone
resolution, and the request estimator. This feature registers **no**
Home Assistant service.

The layout mirrors the sibling Hostaway integration where the idioms
fit and diverges where the platform genuinely differs; the divergences
are tabulated in
[research.md](./research.md#divergences-from-the-hostaway-reference-implementation).

## Coordinators

Three subclasses, two user-facing intervals.

| Coordinator | Data type | Interval | Default | Floor | Cost per refresh |
| --- | --- | --- | --- | --- | --- |
| `HospitableReservationsCoordinator` | `dict[str, tuple[HospitableReservation, ...]]` | reservation | 5 min | 1 min | `ceil(P/50)` x `ceil(R/100)` |
| `HospitablePropertiesCoordinator` | `dict[str, HospitableProperty]` | property | 60 min | 15 min | 1 |
| `HospitableCalendarCoordinator` | `dict[str, PropertyCalendar]` | property | 60 min | 15 min | `P` |

`P` is selected properties, `R` reservations in the window. All three
key on `property_id`.

**Why the calendar is not folded into the properties coordinator.** The
properties fetch is one cheap call that every device and every property
sensor depends on. The calendar fetch is `P` separate calls and is the
only refresh whose cost scales with the selection. Combining them puts
the cheap, reliable refresh behind an expensive fan-out, so one slow or
failing property would delay or fail everything. They share the user's
single "property polling interval" because FR-020 defines exactly one
such knob; two coordinators on one interval is an internal isolation
decision, not a second user-facing control.

### Failure isolation

| Coordinator | Partial failure | Total failure |
| --- | --- | --- |
| Properties | Not possible; single request | `UpdateFailed`; counter increments |
| Reservations | A failed batch fails the refresh — merging a partial batch set produces the partially populated view FR-034 prohibits | `UpdateFailed` |
| Calendar | Per-property. Failed properties keep their last-good day map; only their `availability` sensors degrade | `UpdateFailed` only when **every** property failed |

**FR-057 needs a custom availability policy.** Home Assistant's stock
`CoordinatorEntity.available` returns `last_update_success`, which goes
unavailable after a *single* failed poll. FR-057 requires three
consecutive failures. A shared mixin therefore tracks a
consecutive-failure counter reset on any success, and entity
availability becomes `data is present and consecutive_failures < 3`.
Relying on the stock behavior would violate FR-057 quietly, since
nothing about it looks wrong at a glance.

Auth failures translate to `ConfigEntryAuthFailed`, which raises reauth
for that entry only (US5 acceptance scenario 3). A scope-403 never
does.

## Data model and entity design

Full detail in [data-model.md](./data-model.md) and
[contracts/entities.md](./contracts/entities.md). The load-bearing
points:

**Six sensors and one device per selected property.** Never an entity
per reservation — FR-042 requires it and the Out of Scope section
rejects the alternative as a design, not merely defers it.

| Entity key | Kind | Phase |
| --- | --- | --- |
| `reservation_status` | Enum | US2 |
| `next_arrival` | Timestamp | US3 |
| `next_departure` | Timestamp | US3 |
| `upcoming_reservations` | Numeric | US3 |
| `property_info` | Diagnostic | US3 |
| `availability` | Enum | US7 |

**The reservation status enum is single-dimensional** (FR-043):
`no_reservation`, `awaiting_checkin`, `occupied`, `checked_out`,
`pending_request`, `checkpoint`, `cancelled`, `not_accepted`,
`unknown`. Stay type is an attribute, never a state, because an owner
stay can independently be in any of those conditions (FR-049).

**Occupancy is derived from scheduled moments, never calendar days.**
The check-in and check-out moments come from the reservation's
`check_in` and `check_out` datetimes when they are usable, falling back
to the property's configured `checkin` and `checkout` strings only if
needed. All comparisons happen in the property's effective IANA zone.
**A missing or uninterpretable time is a data error**: on the affected
boundary date the sensor reports `unknown` and logs a warning naming
the reservation and the field. No midnight substitution exists
anywhere in the code, and the test for it asserts `unknown`
specifically, because "not occupied" would also be
satisfied by `awaiting_checkin` — which is exactly the midnight bug.

**Calendar data becomes the `availability` sensor**, with rate,
currency, and a short forward window as attributes. `booked` is used
for an unavailable night; `unavailable` is never an option, because
Home Assistant owns that value.

**Money is integer minor units** in every model, converted to a display
value exactly once in the sensor layer. No model carries a float
(FR-060).

## Config flow, options flow, and versioning

Full detail in
[contracts/config-entry.md](./contracts/config-entry.md).

**Config flow**: `user` (token, with FR-007 plan and token-generation
help text, validated by `GET /user`) then `properties` (multi-select by
name, at least one required, with a distinct abort when the account has
none). `reauth_confirm` accepts a replacement token and verifies it
belongs to the *same* account — accepting a different account's token
would leave the frozen namespace pointing at the wrong account and
orphan every entity, the exact outcome FR-055 exists to prevent.

**Options flow** exposes both intervals, both window bounds, the
property selection, and per-property IANA overrides, all bound-checked
with messages naming the permitted bound (FR-016). It displays a live
requests-per-day estimate, labelled as an estimate (FR-072), and the
FR-023 warnings that widening the window costs requests and narrowing
the lookback can hide in-progress long stays. Changes reload the entry
through an update listener, so they take effect with no restart
(FR-017, SC-011).

**Deselection is non-destructive** and shares a code path with upstream
disappearance: polling stops, entities go unavailable with a reason,
registry entries are retained, and reselection restores identifiers and
recorder history (FR-018, FR-056).

**Versioning**: `VERSION = 1`, `MINOR_VERSION = 1`, with
`async_migrate_entry` implemented in the first release even though it
has nothing to migrate. It refuses downgrades, is the single documented
place a future migration is added, and carries the frozen unique-ID
contract in its docstring. Adding it retroactively is the failure mode
that orphans entities, because by then version-less entries already
exist in the wild (FR-070).

`entry.data` carries only immutable identity — token, account
namespace, namespace source. Everything user-changeable is in
`entry.options`, so an options change never needs a data migration and
a reauth touches exactly one key.

**OAuth is not precluded** (FR-008). Credential handling sits behind
one interface in `api/auth.py`; callers never branch on credential
type. Adding the authorization-code flow later is an internal change
plus one config flow step.

## Auth, errors, retry, and the scope-403 rule

Full detail in
[contracts/errors-and-diagnostics.md](./contracts/errors-and-diagnostics.md).

A typed hierarchy under one base, every instance carrying status,
endpoint, and a redacted excerpt (FR-035): `HospitableAuthError`,
`HospitableScopeError`, `HospitableForbiddenError`,
`HospitableNotFoundError`, `HospitableRateLimitError`,
`HospitableConnectionError`, `HospitableResponseError`, and
`HospitableIncludeMissingError`.

**The 403 branch is the most consequential decision in the error
handling.** A 403 is classified as a scope failure only when the parsed
body's reason phrase contains the case-insensitive substring `scope`.
Everything else — including an absent, empty, or unparsable body —
falls to `HospitableForbiddenError`.

| Property | Choice | Why |
| --- | --- | --- |
| Default branch | Non-scope | `HospitableScopeError` suppresses retry, reauth, and repair. Defaulting to it would swallow a genuine authorization problem |
| Matching | Substring, not the literal `"Invalid scope(s) provided."` | One observed string from one endpoint; an upstream wording change would reroute every scope failure into the reauth loop Principle X names PROHIBITED |
| Reauth | Neither 403 branch, ever | FR-038, Principle II, Principle X |
| Repair issue | Non-scope only | FR-065 carves out the scope case; a repair issue for something the user cannot fix trains users to ignore repair issues |

**Retry**: transport errors, 429, and 5xx retry with jittered
exponential backoff, honoring `Retry-After` when present in either its
delta-seconds or HTTP-date form. 401, 403, 404, and shape violations
never retry. Attempts are bounded; on exhaustion the last typed
exception is raised with its context intact (FR-037). No quota is
hard-coded and no rate-limit header is assumed to exist — their
existence is UNVERIFIED, and designing a token bucket against them is
the easy mistake here (FR-036, OQ-005).

The calendar fan-out is bounded by a semaphore. That is a self-imposed
civility limit chosen because nothing upstream is calibratable, and it
is described as such rather than presented as compliance with a
published limit.

## Redaction and diagnostics

Two mechanisms, deliberately different.

**Logs and exception text** use a key-token denylist followed by a
regex value sweep for bearer tokens, email addresses, and
telephone-shaped strings, then truncation and control-character
sanitization. A denylist is right here because log call sites are many
and over-redacting a debug line costs nothing.

**Diagnostics use an allowlist**, and this is the more important half.
FR-073 binds personal data "whether the endpoint is already known to
carry personal data **or is added in a later specification**". A
denylist structurally cannot satisfy that clause — a future endpoint
returning an undenied field would be emitted in full. An allowlist
fails closed, and reports how many keys it dropped so the omission is
visible.

The diagnostics payload carries entry version, options without the
token, per-coordinator health, record counts, and a **structural
skeleton** of the last response per endpoint: key names paired with the
Python type of their values, never the values. That answers the
question almost every support request reduces to — what shape did the
API actually return — while being structurally incapable of carrying a
name, an address, a coordinate, or a token.

**Most personal fields are never read at all.** Guest identities,
account billing fields, `platform_email`, `platform_name`,
`platform_user_id`, `platform_picture`, `co_hosts`, street, postcode,
and coordinates have no model field. `/channels` is not called, because
nothing needs it and its `login` field can be a clear-text email.
Dropping at the boundary is strictly safer than redacting at the sink,
because a value never parsed cannot be forgotten at a new call site.

SC-008 therefore becomes mechanically testable rather than
aspirational: a diagnostics dump and a DEBUG log capture, both built
from the synthetic fixtures, must contain none of those fixtures'
personal-data values and none of the synthetic token.

## Honored-Request Verification

**HTTP 200 is not proof that a request was honored.** This API has
three independent, separately discovered silent-ignore behaviors, so
treating them as three isolated bugs would leave the fourth
undiscovered. Every optional input the client can send therefore
carries either a post-condition assertion or a documented prohibition.
[contracts/upstream-requests.md](./contracts/upstream-requests.md)
holds the register normatively; a contributor adding a query parameter
must add a row, and the row forces the question "how would I know if
this were ignored?".

**The `include=` pattern (FR-075)**: `responses.assert_include()`
checks that every item in the response carries the expected expansion
key, raising `HospitableIncludeMissingError` otherwise. Two includes
are sent, both CONFIRMED valid:

| Include | Assertion | Fallback when it fires |
| --- | --- | --- |
| `include=listings` on `/properties` | `listings` present on every item | Log once at WARNING; set `listings_available = False`; the refresh continues. The gap is visible as an entity attribute, so an empty listing set is never ambiguous |
| `include=properties` on `/reservations` | `properties` present on every item | Log once at WARNING; fall back to the properties coordinator's cached data. The refresh does not fail |

Both fallbacks are "handle their absence explicitly" as FR-075
requires, as distinct from silent degradation.

**On `include=properties`**, two rationales of different strength, both
recorded. The stated one — that it collapses an N+1 property lookup —
is weaker than it appears, because the properties coordinator already
holds every selected property, so no N+1 remains at the transport
layer. The load-bearing one is decoupling: reservations refresh every
five minutes against properties every sixty, so the include carries
fresh property context on every reservation poll and keeps the
reservation sensor rendering when the properties refresh is failing. It
costs zero extra requests. The design does not claim the first as its
justification.

**Never sent**: `include=guests` (CONFIRMED no-op; FR-033 is
conditional and its condition is unmet here), any other include value,
`status[]` (honored, but OQ-003 forbids depending on server-side
status filtering for correctness, and cancelled reservations are needed
for FR-044 ordering and the `cancelled` state), and the calendar
`listing_id` (CONFIRMED silently discarded).

## Pagination

The client constructs every page URL from the compiled-in base URL and
a locally incremented `page` integer. It never reads `links`,
`meta.path`, or any other URL-valued response field, because those come
back with an `http://` scheme and following them would downgrade a
user's transport security and expose the bearer credential in cleartext
(FR-026, Principle X).

| Guard | Effect |
| --- | --- |
| `per_page` clamped to 100 | FR-025 |
| Termination from `meta.last_page` | FR-025 |
| `meta.current_page` asserted equal to the page requested | FR-034; a mismatch raises |
| Absolute page ceiling | A malformed envelope cannot produce an infinite loop (FR-039) |

**The prohibition is mechanically enforced.** The `respx` suite
registers a route for `http://public.api.hospitable.com/...` whose side
effect raises. Any change that starts following body links fails that
test immediately, instead of silently downgrading transport security
for every user. This turns FR-026 from a convention into a gate.

OQ-006 leaves the permanence of the upstream defect unknown. The
mitigation is correct either way, so no re-evaluation is scheduled.

## Test strategy

### Configuration, set once in US1

```toml
[tool.pytest.ini_options]
xfail_strict = true
asyncio_mode = "auto"

[tool.mypy]
python_version = "3.14"
warn_unused_ignores = true

[tool.coverage.run]
source = ["custom_components"]
```

`asyncio_mode = "auto"` is not decoration. Without it an unmarked
`async def` test never runs its body: with `raises=` pinned the test
hard-fails as unsupported, and without `raises=` that failure is
silently converted to XFAIL and the red phase reports green for a test
that never ran. Both outcomes are wrong.

`warn_unused_ignores = true` is what mechanically forces the
green-phase commit to remove its `# type: ignore[import-not-found]`
comment, exactly as `xfail_strict` forces marker removal. Any narrowing
for tests goes in `[[tool.mypy.overrides]] module = "tests.*"`; mypy's
`exclude` must never be used, because it drops files from type checking
entirely and would gut Principle I across the whole suite.

Coverage is sourced from `custom_components` only. Measuring test files
would make a legal red-phase commit mathematically impossible under any
`fail_under` gate, because a red-phase body legitimately aborts at its
deferred import.

### The red-phase protocol, applied per phase

Every phase runs the same sequence.

1. **Write the phase's tests**, each marked
   `@pytest.mark.xfail(raises=..., strict=True, reason=...)`, where the
   reason takes the form `TDD red phase: <task id> <behavior>`.
   Imports of not-yet-existing modules go **inside the test body**,
   carrying `# type: ignore[import-not-found]`. A module-level import
   would break collection before any marker could apply.
2. **Verify the red phase is real**:
   `uv run pytest --runxfail <the new node ids>`. Scoped, always —
   markers are permitted to persist on `main` across a phase, so a bare
   `--runxfail` run reports every pre-existing marker as a failure and
   destroys the signal. Read each traceback and confirm the failure is
   the missing behavior, not a typo or a bad fixture name.
3. **Commit the tests alone** (red-phase commit). No production code.
   `mypy` runs on this commit too, which is why the ignore comment has
   to be present.
4. **Implement the minimum**, and in the *same* commit remove the
   `xfail` markers and the ignore comments that implementation
   satisfies. Where a still-red test now imports a missing *name* from
   an existing module, re-code its ignore to `attr-defined` rather than
   retaining `import-not-found`.
5. **Re-run the loop.** Previously marked tests now pass outright.

**`raises=` is mandatory on every marker.** `strict=True` alone governs
only the no-exception path; without `raises=`, pytest converts *any*
exception in setup or call into XFAIL, so a typo or a misspelled
fixture would pass every gate while asserting nothing.

**`conftest.py` may not import a not-yet-existing module at all** — a
module-level import there breaks collection for the whole directory,
where no marker can help. Fixtures needing integration objects are
therefore *factory* fixtures: they return a callable that performs the
import inside its own body. Plain data fixtures return dicts loaded
from `tests/fixtures/`.

Every commit leaves the suite green. A clone at any commit on `main`
produces a passing run.

### Synthetic fixtures

Shapes are copied from live observation; **every value is invented**.
No live response is ever committed, even redacted, because a redaction
slip in a fixture is permanent in git history.

Shapes preserved: key names, nesting, types, nullability, integer
minor-unit money, the Laravel paginator envelope, `http://` pagination
links, `meta: null` on `/channels`, and the object-valued (not
list-valued) calendar `data`.

| Fixture | Purpose |
| --- | --- |
| `properties_page1.json` | Baseline, including `timezone: "-0700"` so the D-11 guard has something to ignore |
| `properties_include_listings.json` | FR-053 listing attributes |
| `properties_paginated_p1.json`, `_p2.json` | Two pages carrying `http://` links and `meta.path` — the FR-026 guard |
| `reservations_page1.json` | All six status categories, including `request` and `unknown`, which the live census never observed (A-6) |
| `reservations_include_properties.json` | The honored include |
| `reservations_include_missing.json` | HTTP 200 with the `properties` key absent — the FR-075 assertion path |
| `reservations_boundary_times.json` | Arrival today with a later check-in, departure today with an earlier check-out, and an unparsable time |
| `calendar_property.json` | Object-valued `data`, `days` array, integer minor-unit price |
| `user.json` | UUID plus PII-shaped-but-synthetic fields, for the leak audit |
| `error_401.json`, `error_403_scope.json`, `error_403_other.json`, `error_403_unparsable.txt`, `error_429.json` | The error taxonomy, including the classifier's default branch |

Fixtures live in `tests/fixtures/`, **not** `tests/resources/`. The
repository's `.pre-commit-config.yaml` carries a top-level `exclude`
covering `^tests/resources`, which would exempt fixtures from every
hook — including `check-json`, and including the PII guard itself. A
guard that a blanket exclude can switch off is not a guard.

`tests/fixtures/**` is a new top-level path holding JSON, which cannot
carry an inline SPDX header, so a `REUSE.toml` annotation lands in the
**same commit** that creates the path (Principle IV).

### The PII pre-commit guard

A local hook, `check-fixture-pii`, implemented as
`scripts/check_fixture_pii.py` and added to `.pre-commit-config.yaml`
in US1. It runs over staged JSON under `tests/fixtures/`.

| Rule | Fails on |
| --- | --- |
| Email | Any address whose domain is not `example.com`, `example.org`, `example.net`, or `.invalid` |
| Owner identity | The literals `tykeal` or `bardicgrove`, case-insensitive, anywhere |
| Credential shape | Bearer-token-shaped strings outside the documented synthetic constant |
| Coordinates | Latitude or longitude outside the reserved synthetic box |
| Address | Postcodes and street strings outside the synthetic allowlist |
| Location | A JSON fixture added anywhere other than `tests/fixtures/` |

It reports file, line, and the rule name — and deliberately **does not
echo the matched value**, because CI logs are retained and echoing the
finding would relocate the leak rather than prevent it.

The hook is itself tested: a unit test feeds it a poisoned fixture and
asserts a non-zero exit, then feeds it the real fixture set and asserts
zero. A guard nobody has watched fail is a guard nobody knows works.

### Test layers

| Layer | Covers |
| --- | --- |
| `tests/api/` | Transport, retry, pagination, the error classifier, redaction, model construction, every post-condition assertion |
| `tests/services/` | Status mapping, occupancy derivation, reservation selection, window computation, timezone resolution, the request estimator — all pure functions, no Home Assistant needed |
| `tests/sensor/` | State and attribute production per entity |
| `test_config_flow.py` | Every step, every error, every abort |
| `test_coordinator.py` | Interval wiring, failure isolation, the three-strike availability counter |
| `test_init.py` | Setup, unload, teardown completeness, migration |
| `test_diagnostics.py` | Allowlist behavior and the skeleton renderer |
| `test_privacy.py` | The SC-008 audit across diagnostics, DEBUG logs, and exception text |

## Phase breakdown

One pull request per user story, in priority order. Each is
independently shippable, and each ends at a green-CI checkpoint before
the next begins (Principle IX). Every phase is at minimum a red-phase
commit plus a green-phase commit (Principle XII), with `tasks.md`
updates committed separately (Principle III).

### Phase US1 (P1) — Connect an account and pick properties

**Delivers**: repository scaffolding (`pyproject.toml`, `uv.lock`,
`manifest.json` declaring 2026.8.0, `hacs.json`, brand assets,
`strings.json`, `translations/en.json`); the complete `api/` package;
`services/window.py`, `timezones.py`, `estimator.py`; all three
coordinator classes with the properties coordinator wired into setup;
`entity.py`; `config_flow.py` with the user, properties,
`reauth_confirm`, and options steps; `__init__.py` with setup, unload,
and `async_migrate_entry`; `diagnostics.py`; the synthetic fixtures;
the PII guard.

**Requirements**: FR-001 to FR-016, FR-024 to FR-041, FR-050, FR-055,
FR-063, FR-066, FR-069, FR-070, FR-073, FR-074, FR-075.

**Why independently shippable**: a manager can install it, paste a
token, pick properties, and get a verified connection plus one Home
Assistant device per selected property — which US1 itself names as
standalone value. Diagnostics work. Reauth works. Options are editable.

**Why it is larger than the rest**: Principle VII requires the config
flow to implement the user step, a reauth flow, and an options flow "at
minimum", so a compliant shippable increment cannot omit any of them.
Principle IX requires the API client layer to be delivered and proven
before dependent platforms. Both push the foundation into the first PR.
Recorded in Complexity Tracking.

**Exit criteria**: full CI green; a device per selected property; the
`http://` guard test passing; the scope-403 classifier tested including
the unparsable-body default; a diagnostics dump containing no token
and no personal data; the PII guard proven to fail on a poisoned
fixture. The A-1 date-filter probe and the field-binding table are
resolved before the green phase.

### Phase US2 (P2) — Reservation status per property

**Delivers**: the reservations coordinator wired into setup;
`services/status.py`, `occupancy.py`, `selection.py`;
`sensor/__init__.py`, `sensor/helpers.py`, `sensor/reservation.py`; the
three-strike availability mixin.

**Requirements**: FR-042 to FR-049, FR-057.

**Why independently shippable**: this is the integration's core value —
one enum sensor per property that automations can trigger on. It builds
on US1 and needs nothing from US3 through US7.

**Exit criteria**: every US2 acceptance scenario passing, including all
three occupancy boundary cases and the negative midnight assertion;
deterministic selection proven across repeated refreshes; unknown
statuses logged once without raising.

### Phase US3 (P3) — Property details as entities

**Delivers**: `sensor/property.py` — `next_arrival`, `next_departure`,
`upcoming_reservations`, `property_info`; FR-056 disappeared-property
handling; per-property timezone overrides applied to timestamps and
surfaced through `effective_timezone` and `timezone_source`.

**Requirements**: FR-051 to FR-056, and the FR-074 user-facing
completion.

**Why independently shippable**: dashboards and schedule-driven
automations become possible. It depends on US1 and on the sensor
platform setup and entity-creation module introduced at T082 (US2). If
US3 ships before US2, T082 must be pulled forward into US3.

**Exit criteria**: every US3 acceptance scenario passing; the D-11
regression guard asserting the model has no `timezone` attribute; the
OQ-004 verification performed and, if confirmed, documented.

### Phase US4 (P4) — Cadence and window control

**Delivers**: the update listener that reloads on option change without
a restart; the FR-072 request estimate on the options screen; the
FR-023 help text; non-destructive deselection; bound-naming validation
messages.

**Requirements**: FR-017, FR-018, FR-022, FR-023, FR-072.

**Why independently shippable**: it converts fixed defaults into a
supported tuning surface, which is what keeps the integration safe for
a large portfolio. It also touches `sensor/__init__.py`, so it requires
the sensor platform setup and entity-creation module introduced at T082
(US2), or must pull T082 forward if it ships before US2. Nothing later
depends on it.

**Exit criteria**: option changes take effect with no restart; the
estimate reports 1,704 for ten properties at defaults with 500
reservations; deselection and reselection preserve identifiers and
history in both directions.

### Phase US5 (P5) — Multiple accounts side by side

**Delivers**: multi-entry integration tests; the reauth account-match
check; any fix the evidence forces.

**Requirements**: FR-012, FR-013, and FR-055 verification.

**Why independently shippable**: it delivers the *evidence* for
SC-010's zero-collision guarantee. Much of the behavior is proven by
construction in US1's namespacing, which is the honest
characterization — this phase may be predominantly tests. Test-only
strengthening of an existing test is exempt from the red-phase protocol
(Principle XII, Exemptions); any behavior change the evidence uncovers
is not exempt and gets its own red phase.

**Exit criteria**: five entries with zero unique-ID collisions;
identically named properties across two accounts colliding nowhere; one
entry's auth failure not disturbing another.

### Phase US6 (P6) — Token expiry and recovery

**Delivers**: repair issues for persistent non-credential failures;
scope-403 surfaced as a capability limitation with no repair issue and
no reauth; an audit of every user-facing string against FR-064.

**Requirements**: the FR-038 user-facing completion, FR-064, FR-065.

**Why independently shippable**: every installation eventually hits
token expiry, and Principle VII treats a message that misdirects a user
toward a credential fix for a capability limit as a user-safety defect.

**Exit criteria**: a revoked token produces an actionable reauth prompt
within one interval; a scope-403 produces neither reauth nor a repair
issue; a 403 with an unparsable body lands on the non-scope branch; no
user-facing message is a bare status code.

### Phase US7 (P7) — Availability and pricing, read-only

**Delivers**: the calendar coordinator wired into setup;
`sensor/availability.py`; minor-unit conversion; the whole-lifecycle
zero-writes assertion.

**Requirements**: FR-058 to FR-061.

**Why independently shippable**: supplementary but self-contained, and
last because nothing else depends on it. It requires the sensor
platform setup and entity-creation module introduced at T082 (US2), or
must pull T082 forward if it ships before US2.

**Exit criteria**: `booked` never rendered as `unavailable`;
per-property calendar failure isolation proven; a full lifecycle
issuing zero non-`GET` requests.

## Requirements traceability

Every functional requirement maps to a design element. Where a
requirement is satisfied by *absence* — a field never read, an endpoint
never called — that is stated, because "not implemented" and
"deliberately not reachable" are different things.

| Requirements | Where satisfied |
| --- | --- |
| FR-001, FR-002 | `api/const.py` single base-URL and version constant; the permitted-request list in `contracts/upstream-requests.md` |
| FR-003, FR-006 | Token in `entry.data` only; `api/redaction.py`; `test_privacy.py` |
| FR-004 | `GET /user` validation in the `user` config flow step |
| FR-005 | Reauth on 401; no expiry assumption hard-coded |
| FR-007 | `strings.json` help text on the token step |
| FR-008 | Single credential interface in `api/auth.py`; no OAuth credential accepted |
| FR-009, FR-010, FR-011 | `config_flow.py` steps `user` and `properties` |
| FR-012, FR-013 | One entry per account; `entry.unique_id` is the account UUID |
| FR-014 | `reauth_confirm` with the account-match check |
| FR-015, FR-016 | Options flow schema and bound validation |
| FR-017 | Update listener reload (US4) |
| FR-018 | Non-destructive deselection, shared with FR-056 |
| FR-019, FR-020 | `const.py` defaults and floors; coordinator interval wiring |
| FR-021, FR-022, FR-023 | `services/window.py`; options bounds; help text |
| FR-024 | Direct `snake_case` field access; no translation layer written |
| FR-025, FR-026 | `api/client.py` self-constructed pagination; the `http://` raising route |
| FR-027 | `httpx` defaults; no verification-disabling option exists |
| FR-028, FR-029, FR-030, FR-031 | `api/reservations.py` batching, mandatory filters, the A-1 mode parameter |
| FR-032 | The structured status path only; deprecated flat fields never read |
| FR-033 | Satisfied vacuously — no guest data surfaced, `include=guests` CONFIRMED a no-op, prohibition recorded |
| FR-034, FR-075 | `api/responses.py` shape and post-condition assertions |
| FR-035 | The exception base carrying status, endpoint, redacted excerpt |
| FR-036, FR-037 | `api/retry.py` |
| FR-038 | The 403 classifier; `HospitableScopeError` |
| FR-039 | Window-scoped retention; local re-filter; bounded log-once cache |
| FR-040 | Async throughout; `dt_util.async_get_time_zone` for zone lookups |
| FR-041 | `async_unload_entry` teardown |
| FR-042 to FR-049 | `services/status.py`, `occupancy.py`, `selection.py`; `sensor/reservation.py` |
| FR-050 | `entity.py` device construction |
| FR-051, FR-052, FR-053 | `sensor/property.py` |
| FR-054 | The `suggested_object_id` pattern |
| FR-055 | Frozen unique-ID format; namespace written once into `entry.data` |
| FR-056, FR-057 | The availability mixin and the disappeared-property path |
| FR-058 to FR-061 | `sensor/availability.py`; `MoneyAmount`; the calendar coordinator on the property cadence |
| FR-059 | Satisfied by absence — no write method exists on the client; whole-lifecycle zero-writes assertion |
| FR-062, FR-073 | Personal fields dropped at the model boundary; denylist for logs; allowlist for diagnostics; `/channels` never called |
| FR-063 | `diagnostics.py` |
| FR-064, FR-065 | The error-to-outcome mapping; repair issues; the scope-403 carve-out |
| FR-066 | `manifest.json` and `hacs.json` |
| FR-067 | Polling only; no webhook code exists |
| FR-068 | "property" throughout; "listing" only in the `listings` attribute |
| FR-069 | The `api` / `services` / `sensor` split; no HA service registered |
| FR-070 | `VERSION`, `MINOR_VERSION`, `async_migrate_entry` |
| FR-071 | Three coordinators; entities read shared data and issue no requests |
| FR-072 | `services/estimator.py` |
| FR-074 | `services/timezones.py`; the upstream `timezone` never read |

| Success criteria | How it is evaluated |
| --- | --- |
| SC-001, SC-002, SC-003, SC-005, SC-006 | Live validation, after CI is green (`quickstart.md`) |
| SC-004 | Arithmetic in `contracts/upstream-requests.md`: 1,704 against a 2,000 ceiling; asserted by the estimator test |
| SC-007 | The 429 backoff test |
| SC-008 | `test_privacy.py` across diagnostics, DEBUG logs, and exception text |
| SC-009 | Reauth tests (US6) |
| SC-010 | Multi-entry tests (US5) |
| SC-011 | Update listener tests (US4) |
| SC-012 | The `no_reservation` availability assertion (US2) |
| SC-013 | No blocking call; `dt_util.async_get_time_zone`; verified in live validation |

## Open questions carried into implementation

| Question | Status | Effect on design |
| --- | --- | --- |
| OQ-001 | UNVERIFIED | None. This feature writes nothing |
| OQ-002 | RESOLVED | The upstream `timezone` is never read (D-11) |
| OQ-003 | RESOLVED | `status[]` works but is not used; correctness stays client-side |
| OQ-004 | LIKELY | A documentation obligation (A-8). The detection signal is the availability and reservation sensors disagreeing |
| OQ-005 | UNVERIFIED | No quota hard-coded, no header assumed (A-7) |
| OQ-006 | CONFIRMED, permanence unknown | The mitigation is correct either way; no re-evaluation scheduled |
| OQ-007 | UNVERIFIED | Reactive handling only; no proactive expiry warning |
| OQ-008 | RESOLVED | Occupancy derived; no checked-in status assumed |
| OQ-009 | RESOLVED | The account UUID is the namespace; entry-ID fallback retained |
| OQ-010 | RESOLVED | Aggregate calendar; `listing_id` never sent |
| OQ-011 | UNVERIFIED | `/channels` is never called (A-5) |
| OQ-012 | UNVERIFIED | `ical_imports` discarded at the model boundary (A-5) |
| OQ-013 | UNVERIFIED | `request` and `unknown` fully mapped and fixture-exercised (A-6) |

A-1, A-2, and A-3 are resolved by the 2026-08-09 live probes.
`date_query=checkin` is sent explicitly, even though it matches the
current platform default, and `check_in`/`check_out` are the confirmed
scheduled-time fields.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --- | --- | --- |
| US1's pull request is substantially larger than US2 through US7 | Principle VII requires the config flow to implement the user step, reauth, and options "at minimum", so a compliant shippable increment cannot omit any of them. Principle IX requires the API client layer to be delivered and proven before dependent platforms. Both force the foundation into the first PR | Splitting US1 into a client-only PR and a config-flow PR was rejected: a client-only PR ships nothing a user can install or observe, so it is not an independently shippable increment under Principle IX, and it would leave `main` at a commit with production code no entry point reaches. The size is mitigated by many atomic commits within the PR (Principle III), not by deferring the requirement |
| US5's pull request may be predominantly tests | Multi-account correctness is proven by construction in US1's namespacing, so the phase's genuine deliverable is evidence for SC-010 rather than new behavior | Merging US5 into US1 was rejected because it would enlarge the already-largest PR and bury five-account collision evidence inside a foundation review. Dropping the phase was rejected because SC-010 is a stated success criterion and an unevidenced guarantee is not a guarantee. Principle XII's exemption for test-only strengthening applies, and any behavior change the evidence uncovers gets its own red phase |

**No constitutional principle is violated or waived by this plan.**
Both rows above are complexity to be tracked, not gates being bypassed.
The three decision deviations recorded earlier are departures from
planning instructions in favor of the specification and of observed
fact, not from the constitution.
