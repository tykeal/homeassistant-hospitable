<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Phase 0 Research: Hospitable Home Assistant Integration

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Date**: 2026-08-08

## Purpose

This document records the decisions taken before design, the reasoning
behind each, and the alternatives that were rejected. It also isolates
every assumption this design rests on that the specification does not
mark CONFIRMED, so that no unverified upstream behavior is silently
promoted to fact.

The specification's four-tier evidence legend (CONFIRMED, DOCUMENTED,
LIKELY, UNVERIFIED) is used verbatim here. Nothing in this document
upgrades a tier.

## Decision index

| ID | Decision | Governing requirements |
| --- | --- | --- |
| D-01 | Three coordinators, two intervals | FR-019, FR-020, FR-061, FR-071 |
| D-02 | Calendar surfaced as a sensor entity, not a platform | FR-054, FR-058 |
| D-03 | Zero new runtime dependencies beyond `httpx` | FR-034, FR-075 |
| D-04 | Hand-written frozen dataclass models | FR-024, FR-034 |
| D-05 | Honored-Request Verification as a client rule | FR-026, FR-075 |
| D-06 | `include=properties` on reservations; no `include=guests` | FR-033, FR-075 |
| D-07 | Self-constructed pagination, links never followed | FR-025, FR-026 |
| D-08 | Error taxonomy with a distinct scope-403 branch | FR-035, FR-038, FR-065 |
| D-09 | Hand-rolled retry with jittered backoff | FR-036, FR-037 |
| D-10 | Allowlist diagnostics, denylist logging | FR-062, FR-063, FR-073 |
| D-11 | Upstream `timezone` field never parsed into a model | FR-045, FR-074 |
| D-12 | Config entry version 1.1 with a migration path from day one | FR-070 |
| D-13 | Fixtures under `tests/fixtures/`, guarded by a local hook | Constitution X |
| D-14 | One PR per user story; US1 carries the foundation | Constitution IX |
| D-15 | Failure isolation policy differs per coordinator | FR-057, SC-005 |

## D-01: Three coordinators sharing two intervals

**Decision**: Three `DataUpdateCoordinator` subclasses.

| Coordinator | Interval option | Default | Floor | Upstream cost per refresh |
| --- | --- | --- | --- | --- |
| `HospitableReservationsCoordinator` | reservation interval | 5 min | 1 min | `ceil(P/50)` batches x `ceil(R/100)` pages |
| `HospitablePropertiesCoordinator` | property interval | 60 min | 15 min | 1 request (paginated only above 100 properties) |
| `HospitableCalendarCoordinator` | property interval | 60 min | 15 min | `P` requests, one per selected property |

`P` is the number of selected properties and `R` the number of
reservations inside the configured window.

**Rationale**: The properties fetch is a single cheap call. The
calendar fetch is `P` separate calls, one per selected property, and it
is the only refresh in the integration whose cost scales linearly with
the property selection. Folding the two into one coordinator would put
a cheap, reliable, single-request refresh behind an expensive fan-out,
so one slow or failing property would delay or fail the property
refresh that every device and every property sensor depends on.
Splitting them means a calendar fan-out that partially fails degrades
only the availability sensors of the affected properties.

Both still run on the same user-facing interval, because the user has
one mental model — "property data" — and FR-020 defines exactly one
property polling interval. Two coordinators sharing one configured
interval is an internal isolation decision, not a second user-facing
knob.

**Alternatives considered**:

- *Two coordinators (reservations; properties + calendar)*: rejected
  for the failure-coupling reason above.
- *Four coordinators (splitting reservation batches)*: rejected.
  Reservation batches must be merged into one consistent result set per
  FR-031, so they cannot fail independently without producing a
  partially populated view, which FR-034 prohibits.
- *One coordinator*: rejected. It would refresh property records every
  five minutes for no benefit, and it makes the SC-004 request budget
  unachievable.

## D-02: Calendar data is a sensor entity, not a platform

**Decision**: Availability is exposed as one additional sensor entity
per property, `sensor.hospitable_<property>_availability`, with the
nightly rate, currency, and the short forward window carried as its
attributes. No Home Assistant `calendar` platform entity is created.

**This deviates from a literal reading of a planning instruction.** The
instruction was that "calendar data appears as attributes on the
existing per-property sensor; no new platform". The "no new platform"
half is honored exactly. The "attributes on an existing sensor" half
is not, because FR-058 and US7 acceptance scenarios 1 and 2 require an
availability *state*:

> The availability state MUST use a term such as "booked" for an
> unavailable night and MUST NOT use the word "unavailable", which Home
> Assistant reserves to mean that the entity's data cannot currently be
> reached.

That sentence is only meaningful about an entity state. An attribute
has no interaction with Home Assistant's `unavailable` reserved value,
so the prohibition would be vacuous under an attribute-only design.
Folding availability into the reservation status sensor's state is also
prohibited independently by FR-043, which declares that enum
single-dimensional and restricted to reservation status and occupancy.

The specification is the authoritative input, so it wins. This is
recorded rather than absorbed, and is repeated in
[plan.md](./plan.md#decision-deviations).

**Alternatives considered**:

- *Attributes on the reservation status sensor*: rejected. Violates the
  FR-058 state requirement and mixes two independent data sources onto
  one entity, so a calendar fetch failure would have to degrade the
  reservation sensor.
- *Home Assistant `calendar` platform entity*: rejected. Explicitly out
  of scope and prohibited by FR-054.

## D-03: Zero new runtime dependencies

**Decision**: `manifest.json` declares exactly one requirement,
`httpx`. No retry library, no serialization library, no timezone
library.

The dependency policy given for this plan is pragmatic: a small,
well-maintained helper is permitted where it earns its weight. That
policy was applied, and its honest outcome here is that nothing earns
its weight. This is a finding, not a refusal to consider dependencies.

**Retry and backoff** (`tenacity`, `backoff`, `stamina`): rejected.
The requirement is narrow and specific — honor `Retry-After` when
present, never assume rate-limit headers exist, apply jittered
exponential backoff otherwise, bound the attempt count. Expressing that
through a generic retry decorator requires custom predicate, wait, and
stop callables that together are larger than the roughly fifty lines of
direct code they would replace, and the decorator hides the one
behavior most likely to regress: which HTTP status codes are retried
at all. The sibling Hostaway integration reaches the same conclusion in
a 46-line `api/retry.py`.

**Serialization** (`pydantic`, `mashumaro`, `attrs`, `cattrs`):
rejected, and rejected for a reason specific to this API. FR-034 and
FR-075 both require the integration to *assert* on response structure —
that expected keys are present, that an `include=` expansion actually
took effect, that a page response is the page that was requested. A
generic deserializer's entire value proposition is tolerating and
smoothing over structural variation, which is precisely the behavior
that would let a silently ignored `include=` pass unnoticed. Adopting
one would make the integration's central defensive rule harder to
enforce, not easier. Home Assistant core also does not ship `pydantic`,
so it would be a genuine new install for every user.

**Timezones**: `zoneinfo` is in the standard library on Python 3.14 and
Home Assistant already depends on `tzdata`. No dependency is needed.
See D-11 for the event-loop consequence.

**Alternatives considered**: adding `tenacity` only, on the grounds
that it is ubiquitous. Rejected because ubiquity is not weight-earning;
the constitution's Additional Constraints require runtime dependencies
to be kept minimal and name `httpx` as the HTTP stack.

## D-04: Hand-written frozen dataclass models

**Decision**: `api/models.py` defines `@dataclass(frozen=True)` models
with explicit `from_api()` classmethods that validate required keys and
raise `HospitableResponseError` on a shape violation.

**Rationale**: Follows from D-03. Immutability keeps coordinator data
safe to share across entities, which FR-071 requires. Explicit
`from_api()` methods are the natural home for the FR-034 shape
assertions. Because Hospitable is `snake_case` throughout (FR-024,
CONFIRMED), field names map directly and no translation layer is
written — a difference from the Hostaway reference implementation,
which needs camelCase-to-snake_case mapping in every `from_api_response`
and is therefore materially more verbose than this integration will be.

**Alternatives considered**: `TypedDict` over raw payload dicts.
Rejected because a `TypedDict` is erased at runtime and asserts
nothing, so every FR-034 check would still have to be written by hand
with none of the immutability benefit.

## D-05: Honored-Request Verification

**Decision**: A named, first-class client rule. **HTTP 200 is not proof
that a request was honored.** Every optional request parameter the
client sends must be paired with a post-condition assertion on the
response, or must be documented as deliberately never sent.

This is elevated above a note because this API has four independent,
separately discovered silent-ignore behaviors — the fourth, `/channels`
ignoring `per_page`, was found exactly as this rule predicted a further
one would be. Treating any of them as an isolated bug to work around
would leave the next one undiscovered.

**The register of optional inputs**, which
[contracts/upstream-requests.md](./contracts/upstream-requests.md)
carries normatively:

| Input | Upstream behavior | Client rule |
| --- | --- | --- |
| `include=listings` on `/properties` | CONFIRMED valid | Assert `listings` key present on every item |
| `include=properties` on `/reservations` | CONFIRMED valid | Assert `properties` key present on every item |
| `include=guests` on `/reservations` | CONFIRMED no-op | NEVER SENT (D-06) |
| `listing_id` on the calendar route | CONFIRMED silently discarded | NEVER SENT |
| `links[].url`, `meta.path` | CONFIRMED insecure `http://` | NEVER FOLLOWED (D-07) |
| `page`, `per_page` | CONFIRMED honored | Assert `meta.current_page` equals the page requested |
| `properties[]` on `/reservations` | CONFIRMED required | Assert every returned reservation's property is in the requested set |
| `status[]` on `/reservations` | CONFIRMED honored (OQ-003) | NEVER SENT; correctness stays client-side |
| `per_page` on `/channels` | CONFIRMED-BY-TEST silently ignored (OQ-011) | NEVER SENT; endpoint is uncalled and unpaginated |
| `date_query=checkin` | CONFIRMED-BY-TEST honored parameter and value | SEND; explicit even though it matches the current platform default |

**Rationale**: The rule converts an open-ended hazard into a finite,
reviewable checklist. A future contributor adding a query parameter
must add a row, and the row forces the question "how would I know if
this were ignored?".

**Alternatives considered**: asserting on a checksum or `ETag` of the
response. Rejected; no such mechanism is documented or observed.

## D-06: Include usage, and the FR-033 guest include

**Decision**: Send `include=properties` on `/reservations` and
`include=listings` on `/properties`. Send no other include. In
particular, **do not send `include=guests`**.

**On `include=guests` and FR-033.** FR-033 says the integration "MUST
request guest information as an include on the reservation query **when
guest data is surfaced**". Two facts settle this:

1. This feature surfaces no guest identity. FR-046 lists guest *counts*
   broken down by adults, children, infants, and pets. It lists no
   guest name, email, or phone. The FR-033 precondition is therefore
   not met.
2. The specification's own confirmed expansion table lists `guests` in
   the "tested no-ops or invalid names" column for `/reservations`.
   Sending it would produce an HTTP 200 with no added keys, which under
   D-05 the client must treat as an unhonored request.

So FR-033 is satisfied vacuously in this feature, and the design
records the constraint for the future specification that does surface
guest data: it will have to establish the real expansion name first,
because `guests` is confirmed not to be it. This reading is surfaced
explicitly because a careless implementation would send `include=guests`
on the strength of FR-033's first clause alone and get a silent no-op.

**On `include=properties`.** Two honest rationales, of differing
strength:

- *Stated rationale (weaker than it first appears)*: it collapses an
  N+1 property lookup. This is true in the abstract, but this design
  already holds every selected property in the properties coordinator,
  so there is no N+1 left to collapse at the transport layer.
- *Actual load-bearing rationale*: it decouples the reservation
  coordinator from the properties coordinator. Reservations refresh
  every five minutes; properties every sixty. With the include, each
  reservation refresh carries its own property context, so the
  reservation status sensor renders correctly for a property created or
  renamed inside the last hour, and continues to render if the
  properties refresh is failing. It costs zero additional requests.

Both are recorded. The design does not claim the first as its
justification.

**Fallback if the assertion fires**: log once at WARNING naming the
endpoint and the missing key, then fall back to the properties
coordinator's cached data for property context. The reservation refresh
does not fail. This is "handle their absence explicitly" per FR-075,
as distinct from silent degradation.

## D-07: Pagination is constructed, never followed

**Decision**: `HospitableClient._paginate()` is an async generator that
constructs every page URL itself from the compiled-in base URL, the
endpoint path, and a `page` integer it increments locally. The client
never reads `links`, `meta.path`, `meta.next_page_url`, or any other
URL-valued response field.

Guards:

- `per_page` is clamped to 100 (FR-025).
- Termination is driven by `meta.last_page` and `meta.current_page`.
- An absolute page ceiling bounds the loop even if `meta` is absent or
  inconsistent, so a malformed envelope cannot produce an infinite
  request loop.
- `meta.current_page` is asserted equal to the page requested. A
  mismatch raises `HospitableResponseError`.

**Testable enforcement**: the `respx` suite registers a route for
`http://public.api.hospitable.com/...` whose side effect is to raise.
Any client change that starts following links verbatim fails that test
immediately rather than silently downgrading a user's transport
security.

**Rationale**: FR-026 and Principle X both require this. The permanence
of the upstream defect is unknown (OQ-006), and the mitigation is
correct whether or not it is ever fixed, so no future re-evaluation is
scheduled.

## D-08: Error taxonomy

**Decision**: A single base exception with a shallow, purpose-built
hierarchy. Every instance carries the HTTP status, the endpoint path,
and a redacted body excerpt (FR-035).

```text
HospitableError
├── HospitableAuthError            401
├── HospitableScopeError           403 with a scope-related reason
├── HospitableForbiddenError       403 without a scope-related reason
├── HospitableNotFoundError        404
├── HospitableRateLimitError       429, carries retry_after
├── HospitableConnectionError      transport failure, 5xx
└── HospitableResponseError        shape or envelope violation
    └── HospitableIncludeMissingError   D-05 post-condition failure
```

**The 403 split is the critical branch** and the one most likely to be
implemented wrongly. Classification rule:

1. Parse the response body as JSON. If `reason_phrase` (or, failing
   that, `message` or `error`) contains the case-insensitive substring
   `scope`, raise `HospitableScopeError`.
2. Otherwise — including when the body is absent, empty, or
   unparsable — raise `HospitableForbiddenError`.

The default is deliberately the *non*-scope branch, because
`HospitableScopeError` suppresses both retry and reauthentication, and
misclassifying a genuine authorization problem as a capability limit
would hide it. `HospitableForbiddenError` raises a repair issue under
FR-065.

Neither 403 branch ever produces reauthentication. Only
`HospitableAuthError` does. This is mandated three times over: FR-038,
Principle II, and Principle X.

**Alternatives considered**: matching the exact literal
`"Invalid scope(s) provided."`. Rejected as too brittle — it is one
observed string from one endpoint, and a wording change upstream would
silently reroute every scope failure into a reauthentication loop,
which Principle X names a PROHIBITED failure mode.

## D-09: Retry and backoff

**Decision**: A bounded retry loop in `api/retry.py`, applied inside
the client's request method.

| Condition | Retried | Delay |
| --- | --- | --- |
| Transport error (`httpx.TransportError`) | Yes | Jittered exponential |
| HTTP 429 | Yes | `Retry-After` if present, else jittered exponential |
| HTTP 5xx | Yes | Jittered exponential |
| HTTP 401, 403, 404 | No | — |
| Shape violation | No | — |

Backoff is `base * 2**attempt`, multiplied by a uniform jitter factor
in `[0.75, 1.25]`, floored at 0.1 s and capped at `MAX_BACKOFF`.
`MAX_BACKOFF = 300` seconds, chosen to satisfy SC-007's five-minute
resumption bound even when the computed delay includes maximum jitter.
Attempts are bounded; on exhaustion the last typed exception is raised
with its context intact (FR-037).

No quota is hard-coded and no rate-limit header is assumed to exist
(FR-036, OQ-005). `Retry-After` is honored *if present* in both its
delta-seconds and HTTP-date forms; absence is the expected case.

Politeness for the calendar fan-out is a concurrency limit, not a rate
limit: an `asyncio.Semaphore` bounds simultaneous calendar requests.
This is a self-imposed civility bound chosen because nothing upstream
is known to calibrate against, and it is stated as such rather than
presented as compliance with a published limit.

## D-10: Redaction and diagnostics

**Decision**: Two different mechanisms for two different problems.

**Logs and exception text use a denylist plus a value sweep.** A
key-token denylist catches `token`, `authorization`, `secret`,
`password`, `email`, `login`, `phone`, `picture`, `co_host`, `vat`,
`tax`, and `platform_name`. A regex sweep then runs over the resulting
text for bearer tokens, email addresses, and telephone-shaped strings,
as defence in depth against a key name nobody anticipated. Output is
truncated to a bounded excerpt length.

A denylist is used here because log call sites are many and the cost of
over-redacting a debug line is low.

**Diagnostics use an allowlist.** This is the more important half, and
it is chosen for a specific reason. FR-073 requires that personal data
be treated as sensitive by default "whether the endpoint is already
known to carry personal data **or is added in a later specification**".
A denylist cannot satisfy that clause: a future endpoint returning a
field nobody has denied would be emitted in full. An allowlist fails
closed — an unrecognized field is omitted, and the omission is visible
because the diagnostics output records how many keys it dropped.

Concretely, the diagnostics payload contains the config entry version
and options with the token absent, the namespace source, per-coordinator
health (last success flag, consecutive failure count, last exception
*type* and status code but not its message), entity and record counts,
and a *structural skeleton* of the most recent response per endpoint:
key names paired with the Python type of their values, never the values
themselves. That is close to maximally useful for triage and
structurally incapable of leaking a name, an address, or a token.

FR-062 and SC-008 are then verifiable rather than aspirational: the
test suite asserts that a diagnostics dump built from the synthetic
fixtures contains none of the fixtures' personal-data values, and that
a log capture at DEBUG across a full refresh contains none of them
either.

## D-11: The upstream timezone field is never parsed

**Decision**: `HospitableProperty` has no `timezone` attribute. The
`timezone` key from `/properties` is not read into any model, is not
stored in the config entry, and is not emitted in diagnostics.

**Rationale**: OQ-002 established (CONFIRMED, live) that the field is a
fixed UTC offset such as `-0700`, which is DST-blind and may vary with
the season. FR-074 prohibits its use as default, fallback, or persisted
value. The strongest available enforcement of a "never use this"
requirement is to make the value structurally unreachable from the
code that could misuse it, so it is dropped at the model boundary.

A unit test asserts the attribute does not exist, so a future
contributor who adds it back is stopped by CI rather than by review
attention.

**Event-loop consequence**: constructing a `zoneinfo.ZoneInfo` reads
the filesystem and therefore blocks. Timezone resolution uses Home
Assistant's `homeassistant.util.dt.async_get_time_zone`, which is
cached and executor-backed. A bare `ZoneInfo(...)` call anywhere in the
integration is a Principle VIII violation and SC-013 risk.

**Alternatives considered**: deriving an IANA zone from
`address.coordinates`. Explicitly out of scope, and it would require a
bundled shapefile dependency that D-03 would reject.

## D-12: Config entry versioning

**Decision**: `VERSION = 1`, `MINOR_VERSION = 1`, with
`async_migrate_entry` implemented in the first release even though it
has nothing to migrate yet.

`async_migrate_entry` in version 1.1 does three things: it refuses to
downgrade (an entry whose `version` exceeds the running `VERSION`
returns `False` rather than being mangled), it is the single documented
place a future migration is added, and it carries the frozen unique-ID
contract in its docstring.

**Rationale**: FR-070 requires the migration path to exist. Adding it
retroactively is the failure mode that orphans entities, because by
then there are already entries in the wild written by a release that
never declared a version. FR-055 additionally freezes the unique-ID
format, so the migration function is where that promise has to be kept.

`entry.data` holds only immutable identity: the token, the account
namespace, and which source that namespace came from. Everything a user
can change lives in `entry.options`, so an options change never
requires a data migration.

## D-13: Test fixtures and the PII guard

**Decision**: Synthetic fixtures live in `tests/fixtures/`, and a local
pre-commit hook, `check-fixture-pii`, fails the commit when one matches
a known-PII pattern.

**Path choice is load-bearing.** The repository's
`.pre-commit-config.yaml` carries a top-level `exclude` covering
`^tests/resources`. Placing fixtures there would exempt them from every
hook — including `check-json`, and including the PII guard itself. A
guard that a blanket exclude can switch off is not a guard. Fixtures
therefore go in `tests/fixtures/`, which no exclude covers.

`tests/fixtures/**` is a new top-level path containing JSON, which
cannot carry an inline SPDX header, so a `REUSE.toml` annotation must
land in the same commit that introduces the path (Principle IV).

**Guard rules**, all applied to staged JSON under `tests/fixtures/`:

| Rule | Fails on |
| --- | --- |
| Email | Any RFC-ish address whose domain is not `example.com`, `example.org`, `example.net`, or `.invalid` |
| Owner identity | The literals `tykeal` or `bardicgrove` anywhere, case-insensitive |
| Credential shape | Bearer-token-shaped strings outside the documented synthetic token constant |
| Coordinates | Latitude or longitude outside the reserved synthetic box |
| Address | Postcodes and street strings outside the synthetic allowlist |
| Location | A JSON fixture added anywhere other than `tests/fixtures/` |

The hook reports file, line, and the name of the rule that fired. It
deliberately does **not** echo the matched value, because CI logs are
retained and echoing the finding would relocate the leak rather than
prevent it.

**Fixture content policy**: shapes are copied from live observation —
key names, nesting, types, nullability, the integer-minor-unit money
representation, the Laravel paginator envelope, the `http://`
pagination links, `meta: null` on `/channels`. Every value is invented.
No live response is ever committed, even redacted, because a redaction
mistake in a fixture is permanent in git history.

## D-14: Phase structure

**Decision**: One pull request per user story, US1 through US7, in
priority order. US1 carries the foundation.

**Reading of "US1 carries the coordinators"**: US1's PR *contains* all
three coordinator classes, fully implemented and unit-tested against
the synthetic fixtures, which is what Principle IX means by proving the
API client layer before dependent platforms are built. Only the
properties coordinator is *instantiated and refreshed* by
`async_setup_entry` in US1, because US1 creates no entity that consumes
reservation or calendar data. Wiring the other two into setup at that
point would ship a release that spends roughly 1,700 upstream requests
a day to display nothing, which contradicts US1's own
"independently shippable" standard and FR-071's economy requirement.

This is a scoping reading, not a reversal. Both coordinators land in
the US1 diff, under test.

**Constitution VII floor**: it requires the config flow to implement
the user step, a reauth flow, and an options flow "at minimum". A
shippable US1 therefore cannot omit reauth or options. US1 delivers the
minimum compliant version of each; US4 and US6 deepen them rather than
introduce them. The plan states per-PR scope so this does not read as
scope creep.

## D-15: Failure isolation policy

**Decision**: The three coordinators fail differently, on purpose.

| Coordinator | Partial failure | Total failure |
| --- | --- | --- |
| Properties | Not possible; one request | `UpdateFailed`; failure counter increments |
| Reservations | A failed batch fails the refresh — merging a partial batch set would produce the partially populated view FR-034 prohibits | `UpdateFailed` |
| Calendar | Per-property. Failed properties keep their last-good day map; their availability sensors alone degrade | `UpdateFailed` only when every property failed |

**FR-057 requires a custom availability policy.** Home Assistant's
`CoordinatorEntity.available` returns `last_update_success`, which
makes an entity unavailable after a *single* failed poll. FR-057
requires three consecutive failures. A shared mixin therefore tracks a
consecutive-failure counter, reset on any success, and entity
availability is `data is present and consecutive_failures < 3`. Using
the stock behavior would violate FR-057 quietly, since nothing about it
looks wrong at a glance.

## Assumptions and resolved upstream behavior

Each row states the assumption or resolved behavior, why it is needed,
and any concrete fallback if a live probe disproves it. Resolved rows
carry their evidence tier directly.

### A-1: Reservation date-filter mode parameter

**Tier**: RESOLVED, CONFIRMED-BY-TEST. **Governs**: FR-029, FR-030.

FR-030 requires the date-filter mode to be sent explicitly when the
platform exposes such a parameter. A live probe on 2026-08-09 confirmed
`date_query` exists, is honored, and validates its value set. In a
narrow window, baseline and `date_query=checkin` were byte-identical
(`total=37`, hash `71b51035652a`), while `date_query=checkout`
returned a different set (`total=35`, hash `e900025af453`). A bogus
value returned HTTP 400 with "The date reference must be either
'checkin' or 'checkout'." The complete value set is therefore exactly
`checkin` or `checkout`; the platform default is currently `checkin`.
The fallback branch in FR-030 is documented but not taken.

**Why it matters**: the ninety-day lookback default exists specifically
because filtering is by check-in date (FR-022, and the Edge Cases
discussion of long stays). If the real filter mode were, say, overlap
based, the lookback rationale changes.

**Decision**: send `date_query=checkin` on every reservation query,
even though it matches the current platform default, so a future
platform default change cannot silently alter window semantics. The
client-side window filter remains authoritative.

### A-2: Scheduled time field names on a reservation

**Tier**: CONFIRMED-BY-TEST. **Governs**: FR-045, FR-046.

The live reservation-field probe on 2026-08-09 confirmed the scheduled
check-in and check-out fields are top-level `check_in` and `check_out`.
They were present on 25 of 25 sampled reservations. No candidate-field
list is needed.

### A-3: Format of property `checkin` and `checkout` strings

**Tier**: CONFIRMED-BY-TEST. **Governs**: FR-053, FR-074.

The live property-field probe on 2026-08-09 confirmed `checkin` and
`checkout` are bare `HH:MM` wall-clock policy strings. They are not
instants: they contain no date, seconds, UTC offset, or timezone, and
they must not be parsed into datetimes or used for arithmetic. Across
13 sampled properties both fields were present, non-null, and matched
the `99:99` mask.

The integration carries these values as strings for property attributes
and degrades malformed values to `None`. It must not combine them with
`property.timezone`, because that upstream field is a fixed UTC offset
(`-0700` in fixtures), not an IANA timezone, and is DST-blind.

The reservation scheduled-time probe separately confirmed reservation
`check_in` and `check_out` are top-level ISO 8601 datetimes with UTC
offsets. Those reservation fields remain governed by A-2 and FR-045.

### A-4: Reservation window filter fidelity

**Tier**: UNVERIFIED (mechanism), CONFIRMED (observation).

FR-029 records that a dateless reservation query returned no results
and that the mechanism is unestablished. The design always sends
explicit bounds, which FR-029 states is the correct mitigation under
every candidate explanation, so no behavior depends on resolving it.

The client additionally re-filters the merged result set against the
configured window locally before handing it to the coordinator, so a
server-side filter that is looser than requested cannot inflate memory
beyond the FR-039 bound.

### A-5: Channels pagination and iCal imports

**Tier**: OQ-011 RESOLVED (CONFIRMED-BY-TEST); OQ-012 unresolvable from
the available account. **Governs**: OQ-011, OQ-012.

Neither affects this feature. `/channels` is not called by this
integration at all — it is account-level, it carries a clear-text email
in `login`, and nothing in FR-001 through FR-075 needs it, so the
lowest-risk handling of the endpoint is not to call it. A live test
resolved OQ-011: `/channels` returned `meta: null` and `links: null`,
and a `per_page=1` request returned the identical seven rows, so the
endpoint is unpaginated and silently ignores `per_page` — the fourth
silent-ignore behavior in the D-05 register. `ical_imports` arrives as
a side effect of `include=listings` and is discarded at the model
boundary, which is why its population state is irrelevant here; OQ-012
could not be resolved because no iCal imports are configured on the
available account, and confirming a populated array would require an
account that uses them.

This is recorded so that a later specification does not mistake the
absence of handling for an oversight.

### A-6: Unobserved reservation status categories

**Tier**: CONFIRMED-BY-TEST (resolved). **Governs**: FR-043, OQ-013.

Resolved by a live census of every `reservation_status.current` and
every `history` entry across 652 reservations. The `current` value is an
object `{category, sub_category}`; the census of history entries was:

| category | sub_category | count |
| --- | --- | --- |
| accepted | null | 541 |
| cancelled | null | 162 |
| not accepted | expired | 47 |
| request | request to book | 39 |
| not accepted | declined | 11 |
| checkpoint | voided | 8 |
| checkpoint | checkpoint | 7 |
| request | pending verification | 3 |
| request | request for payment | 2 |
| request | awaiting approval | 2 |

Findings:

- `request` **never** appears as a *current* category but occurs 46
  times in `history`. It remains fully mapped and is exercised by a
  synthetic fixture.
- `unknown` was **never** observed anywhere, as either a category or a
  sub_category. The `unknown` fallback in `StatusMapper` nonetheless
  **remains correct defensive behaviour** for an unrecognised future
  value and MUST NOT be removed: FR-048 requires mapping an unknown
  category to `unknown`, logging once, and never raising.

**Fallback**: none needed for the observed categories. The genuinely
risky path remains a category *outside* the documented six, which FR-048
covers: map to `unknown`, log once per distinct value, never raise.

### A-6a: Flat status disagrees with the structured path

**Tier**: CONFIRMED-BY-TEST. **Governs**: FR-032, FR-048.

A census of the deprecated flat `.status` string against
`reservation_status.current` over 652 reservations:

| flat `.status` | nested `category` | nested `sub_category` | count |
| --- | --- | --- | --- |
| accepted | accepted | null | 504 |
| cancelled | cancelled | null | 118 |
| denied | not accepted | declined | 11 |
| cancelled | not accepted | expired | 10 |
| checkpoint voided | checkpoint | voided | 8 |
| checkpoint | checkpoint | checkpoint | 1 |

The two sources **disagree in three of the six observed combinations**.
Ten reservations report flat `cancelled` while the structured path says
`not accepted` / `expired`, so a reader trusting the flat field would
mislabel an expired stay as cancelled. This is hard evidence for FR-032
and FR-048: status MUST be read from the structured path and never from
the flat field, which is retained only as raw/deprecated evidence.

### A-7: Rate-limit headers

**Tier**: CONFIRMED-BY-TEST for the success case; the 429 case remains
UNVERIFIED. **Governs**: FR-036, OQ-005.

The client reads `Retry-After` and any `X-RateLimit-*` headers *if
present* and ignores their absence, which a live probe confirms is the
actual behavior on success. The full response headers on a `200` from
`GET /properties` were `date`, `content-type`, `cache-control`,
`x-hospitable-trace`, `access-control-allow-origin`,
`access-control-expose-headers`, and `strict-transport-security` —
there was **no `X-RateLimit-*` header and no `Retry-After`**. The
design's tolerance of their absence is therefore confirmed rather than
assumed, and the opposite mistake — designing a token-bucket against
headers that may not exist — is confirmed as one correctly avoided. No
code path requires these headers and no quota is hard-coded. What
remains genuinely unknown is whether a rate-limited `429` response
carries `Retry-After`; no `429` has been observed and one will not be
deliberately triggered, so the defensive `Retry-After` parsing in
`custom_components/hospitable/api/retry.py` stays and remains correct.

### A-8: Reservations on unlisted listings

**Tier**: UNANSWERABLE BY API DESIGN (OQ-004). **Governs**: OQ-004.

The original third-party report claimed these are absent from the
reservations endpoint. Live probing established (CONFIRMED-BY-TEST)
that the question cannot be decided through the public API at all:
`GET /reservations` without `properties[]` returns HTTP 400 with
`"The properties field is required."`, `GET /listings` and
`GET /properties/{id}/listings` both return 404, all 13 account
properties report `listed: true`, and all 56 listings are surfaced via
`GET /properties?include=listings`. Reservations therefore cannot be
enumerated for a listing that is not already known, and no endpoint
enumerates listings independently. The behavior is structurally
undecidable, not merely untested.

**Handling**: this remains a documentation obligation, not a code one,
and that conclusion is now firmly established rather than provisional.
The user-facing README (task T149) must state the limitation. Notably,
the availability sensor from US7 reads the *aggregate* property
calendar, which CONFIRMED includes bookings from every sales channel —
so if such reservations exist, the availability sensor and the
reservation sensor will disagree for such a property, and that
disagreement is the only observable detection signal.

## Deferred scope: webhooks and OAuth

This section preserves future-scope research that does not bind the
current PAT-only, polling-only feature. Principle XI remains not
applicable to this feature, as recorded in [plan.md](./plan.md),
because this integration registers no webhook endpoint and performs no
OAuth flow in spec 001.

### F-1: Webhook signature mechanism

**Tier**: UNVERIFIED. **Governs**: future webhook specifications only.

Best available information, all from secondary sources rather than an
observed delivery, suggests Hospitable signs webhook deliveries with a
`Signature` header whose value is an HMAC-SHA256 hex digest over the
raw request body. The same secondary sources report dashboard-only
webhook registration, no webhook registration API, delivery source IPs
in `38.80.170.0/24`, and five failed-delivery retries at 1 second,
5 seconds, 10 seconds, 1 hour, and 6 hours.

**Handling**: do not implement signature verification against the
unverified header name alone. A future webhook specification must
confirm the mechanism against a real delivery or authenticated
developer-portal material before relying on any header name, digest
format, retry schedule, or source-address range.

### F-2: OAuth token lifetimes, endpoints, and scopes

**Tier**: CONFIRMED-BY-SPEC. **Governs**: future OAuth
specifications only.

Hospitable's own Stoplight OpenAPI export documents the OAuth details
below. No live OAuth grant was performed, because obtaining one
requires Vendor approval that this project does not hold; these facts
therefore must not be promoted to CONFIRMED-BY-TEST.

- Access token lifetime: 12 hours (`expires_in: 43200`).
- Refresh token lifetime: 90 days.
- Both access and refresh tokens rotate on refresh. A future OAuth
  implementation must replace the stored refresh token atomically and
  discard the superseded token.
- Observed scopes: `listing:read`, `property:read`, `financials:read`,
  `message:read`, `message:write`, `transaction:read`,
  `enrichment:read`, and `enrichment:write`.
- Token endpoint: `POST https://auth.hospitable.com/oauth/token`.
- The token endpoint takes a JSON body, not a form-encoded body. A
  form-encoded request may look natural from OAuth habit but is wrong
  for this API.
- Authorize endpoint: `https://auth.hospitable.com/oauth/authorize`.
- Scopes are configured in the Partner Portal and are not passed in the
  authorize URL.
- There is no client-credentials grant. `authorization_code` is the
  only documented grant type.

**Handling**: spec 001 remains PAT-only. The credential interface keeps
OAuth addable, but no current code may depend on Vendor-only access or
OAuth scopes.

### F-3: General and messaging rate limits

**Tier**: RESOLVED as unpublished, with `X-RateLimit-*` headers
UNVERIFIED. **Governs**: FR-036, OQ-005, and future messaging
specifications.

Hospitable publishes no general numeric rate-limit ceiling. The only
documented numeric limits found are for messaging: 2 messages per
minute per reservation and 50 messages per 5 minutes. The existence of
`X-RateLimit-*` response headers remains UNVERIFIED; it rests on
SDK-author prose rather than documentation or an observed response.

**Handling**: the current polling client must continue to avoid any
hard-coded general quota and must not assume `X-RateLimit-*` headers
are present. Future messaging specifications must respect the two
published messaging limits wherever the integration sends messages.

## Sizing check against SC-004

SC-004 bounds the integration at fewer than 2,000 upstream requests per
day for ten selected properties at default settings with no more than
500 reservations in the window. The design's arithmetic:

| Component | Per day |
| --- | --- |
| Property polls: `1440 / 60` x 1 page | 24 |
| Calendar polls: `1440 / 60` x 10 properties | 240 |
| Reservation polls: `1440 / 5` x `ceil(10/50)` batches x `ceil(500/100)` pages | 1,440 |
| **Total** | **1,704** |

1,704 < 2,000, so SC-004 holds at the stated bound with roughly 15%
headroom. The dominant term is the reservation page count, which is why
FR-023's warning about widening the window is a real operational
warning and not boilerplate, and why FR-072 requires the options screen
to show the estimate.

Two levers exist if a user's configuration exceeds the budget, and
neither is used by default: raising the reservation interval, and
adding a `status[]` filter to exclude cancelled reservations
server-side. The second is available (OQ-003 CONFIRMED the filter
works) but is deliberately not adopted, because OQ-003 also records
that correctness must not depend on server-side status filtering, and
because cancelled reservations are needed for the FR-044 selection
ordering and FR-043's `cancelled` state.

## Divergences from the Hostaway reference implementation

The Hostaway integration is the structural model. Where this design
departs, the reason is a genuine platform difference rather than
preference.

| Area | Hostaway | Hospitable | Why |
| --- | --- | --- | --- |
| Coordinators | Two | Three | Calendar fan-out cost isolation (D-01) |
| Field naming | camelCase to snake_case mapping in every model | None | Hospitable is `snake_case` throughout (FR-024, CONFIRMED) |
| Auth | OAuth2 client-credentials with a token manager and refresh lock | Static PAT, no refresh, no lock | PAT does not expire within a session; OAuth is out of scope but the credential interface keeps it addable (FR-008) |
| Pagination | Cursor (`afterId`) and offset | Laravel page/`per_page` envelope | Different upstream paginator |
| `services/` package | Home Assistant service registration | Domain logic only | FR-069 defines the name explicitly for this project. **This contradicts the briefing's claim that Hostaway's `services/` is domain logic; it is in fact HA service registration.** FR-069 governs regardless, and this integration registers no HA services. |
| `diagnostics.py` | Absent | Required | FR-063 |
| Response envelope | `{status, result}` | Laravel `{data, links, meta}` | Different upstream shape |
| Entry migration | No `async_migrate_entry` | Required from day one | FR-070 |
| Insecure pagination links | Not applicable | Explicit prohibition and a test guard | CONFIRMED upstream defect (FR-026) |

The idioms adopted unchanged are: an `api` / `services` / `sensor`
package split, a thin exception hierarchy with a single base, private
helper functions in a dedicated `redaction` module, frozen dataclass
models with `from_api` constructors, `SensorEntityDescription`
subclasses carrying a `value_fn`, `suggested_object_id` used to satisfy
the entity-ID naming convention, and `respx` for all outbound HTTP in
tests.
