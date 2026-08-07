<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Feature Specification: Hospitable Home Assistant Integration

**Feature Branch**: `001-hospitable-ha-integration`

**Created**: 2026-08-06

**Status**: Draft

**Input**: User description: "Home Assistant integration for the
Hospitable property management platform"

## Overview

Hospitable is a vacation-rental property management platform. Property
managers use it to consolidate bookings that arrive from Airbnb,
Vrbo/HomeAway, Booking.com, and direct channels into a single view of
their portfolio.

This feature delivers the first Home Assistant custom integration for
Hospitable. No such integration exists today. Its purpose is to make a
manager's live reservation and property state available inside Home
Assistant so that automations can react to real arrivals, departures,
cancellations, and occupancy without anyone re-keying data by hand.

This specification covers the read-only, polling-based foundation of
that integration, authenticated with a Hospitable Personal Access
Token. Later specifications will build on it.

### Evidence confidence legend

This specification distinguishes what is known about the Hospitable
Public API from what is merely reported. Every claim about upstream
behavior carries one of these markers, and requirements that rest on
unverified behavior say so explicitly rather than asserting it.

| Marker | Meaning |
| --- | --- |
| **CONFIRMED** | Verified empirically against a live Hospitable account, or read directly from Hospitable's own OpenAPI export. |
| **DOCUMENTED** | Stated in Hospitable's own user-facing documentation or account interface, but not verified empirically. This tier is not equivalent to CONFIRMED: one claim from this source — that a Personal Access Token reaches every Public API endpoint by default — has already been disproved by live test. |
| **LIKELY** | Reported by an independent third party who claims live verification, but not reproduced by this project. |
| **UNVERIFIED** | Single-source, undocumented, or inferred. Must not be relied upon without a test. |

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect an account and pick properties (Priority: P1)

As a property manager, I want to add the Hospitable integration
through the Home Assistant user interface by pasting my Personal
Access Token, and then pick which of my properties Home Assistant
should watch, so that I only bring in the properties I actually
automate.

**Why this priority**: Nothing else in the integration can exist
without an authenticated connection and a chosen property set. Every
other story reads data that this story makes reachable. It is also the
smallest slice that delivers standalone value: a manager who completes
only this story has a verified, stored connection and a device in Home
Assistant for each property they care about.

**Independent Test**: Add the integration from the Home Assistant
integrations page, paste a token, confirm the property list is
populated from the live account, select a subset, and confirm one
device appears per selected property and none for unselected ones.

**Acceptance Scenarios**:

1. **Given** a valid Personal Access Token from a Hospitable account
   on a paid plan, **When** the manager pastes it into the setup form,
   **Then** the integration verifies it against Hospitable and
   advances to the property selection step.
2. **Given** a token that Hospitable rejects, **When** the manager
   submits the form, **Then** an error explains that the token was
   rejected and tells the manager to generate a new one under Apps →
   API access, and the form remains editable for a retry.
3. **Given** a token that Hospitable rejects, **When** the manager
   submits the form, **Then** the failure message names both possible
   causes — an invalid or expired token, and an account whose plan has
   no Public API access — rather than showing a bare HTTP status code.
4. **Given** the property list step is shown, **When** the manager
   selects two of five properties and finishes, **Then** exactly two
   property devices are created and only those two properties are
   polled.
5. **Given** the manager selects no properties, **When** they try to
   finish, **Then** the flow refuses to complete and explains that at
   least one property is required.
6. **Given** the account has no properties at all, **When** the
   property step loads, **Then** the flow reports that no properties
   were found instead of presenting an empty selector.

---

### User Story 2 - Monitor reservation status for each property (Priority: P2)

As a property manager, I want a single sensor per property that tells
me what is happening with that property's booking right now, so that I
can trigger automations on arrival, departure, and cancellation
without wiring up one entity per booking.

**Why this priority**: This is the core value of the integration and
the reason a manager installs it. It is deliberately modeled as one
sensor per property rather than one entity per reservation, so the
entity set stays stable and bounded as bookings come and go.

**Independent Test**: With the integration configured, confirm each
selected property has a reservation status sensor whose state matches
the property's real booking situation in Hospitable, and whose
attributes describe the relevant reservation and the bookings that
follow it.

**Acceptance Scenarios**:

1. **Given** a property with an accepted reservation whose arrival
   date is in the future, **When** the integration polls, **Then** the
   property's reservation status sensor reports that it is awaiting
   check-in and its attributes carry the arrival date, departure date,
   nights, guest counts, booking channel, and channel confirmation
   code.
2. **Given** a property whose accepted reservation has arrived and
   whose scheduled check-in time has passed, but which has not yet
   reached its scheduled check-out, **When** the integration polls,
   **Then** the sensor reports the property as occupied.
3. **Given** a property with no reservation anywhere in the configured
   window, **When** the integration polls, **Then** the sensor reports
   that there is no reservation, rather than becoming unavailable or
   blank.
4. **Given** a reservation is cancelled in Hospitable, **When** the
   next poll runs, **Then** the sensor state changes to reflect the
   cancellation within one polling interval.
5. **Given** a property has several reservations in the window,
   **When** the integration polls, **Then** the sensor reflects the
   single most operationally relevant reservation and lists the
   remainder in an upcoming-reservations attribute.
6. **Given** Hospitable returns a reservation status value the
   integration does not recognise, **When** the sensor updates,
   **Then** it reports an unknown state, logs the unrecognised value
   once, and does not raise.
7. **Given** a stay marked as an owner stay rather than a guest stay,
   **When** the sensor updates, **Then** the stay-type attribute
   reports an owner stay, while the sensor state continues to reflect
   that reservation's status and occupancy on exactly the same terms
   as a guest booking.
8. **Given** a property whose accepted reservation arrives today with
   a scheduled check-in time later in the day, **When** the
   integration polls before that time, **Then** the sensor reports
   that it is awaiting check-in and MUST NOT report the property as
   occupied.
9. **Given** a property whose accepted reservation departs today with
   a scheduled check-out time earlier in the day, **When** the
   integration polls after that time, **Then** the sensor reports the
   property as checked out and MUST NOT report it as occupied.
10. **Given** a reservation on its arrival or departure date that
    carries no usable scheduled check-in or check-out time, **When**
    the integration polls, **Then** the sensor reports an unknown
    state, logs a warning naming the reservation and the missing
    field, and MUST NOT report the property as occupied and MUST NOT
    substitute a midnight or any other default time.

---

### User Story 3 - See property details as entities (Priority: P3)

As a property manager, I want each property's own information and its
near-term booking summary exposed as entities, so that I can build
dashboards that show my portfolio at a glance and write automations
that depend on check-in and check-out timing.

**Why this priority**: Property context turns a bare status value into
something a dashboard can present and an automation can schedule
against. It depends on User Story 1 but not on User Story 2, and it
delivers value on its own.

**Independent Test**: Confirm that each selected property exposes
next-arrival and next-departure timestamps, an upcoming reservation
count, and a property information entity carrying the property's
address, configured check-in and check-out times, capacity, and its
channel listings.

**Acceptance Scenarios**:

1. **Given** a property with future reservations, **When** the
   integration polls, **Then** next-arrival and next-departure
   entities report the correct upcoming dates and times.
2. **Given** a property with no future reservations, **When** the
   integration polls, **Then** the next-arrival and next-departure
   entities report no value rather than a stale one.
3. **Given** a property is renamed in Hospitable, **When** the next
   poll runs, **Then** the display name updates while the entity
   identifiers and their recorded history are preserved.
4. **Given** a property has more than one channel listing, **When**
   the property information entity updates, **Then** all listings are
   represented with their channel and channel identifier.
5. **Given** a monitored property is deleted or unshared in
   Hospitable, **When** the next poll runs, **Then** its entities
   become unavailable with an explanatory reason and are not silently
   removed.

---

### User Story 4 - Tune polling cadence and window (Priority: P4)

As a property manager, I want to control how often Home Assistant
polls Hospitable and how far back and forward it looks for
reservations, so that I can trade freshness against request volume to
suit my portfolio.

**Why this priority**: Hospitable publishes no general rate limit, so
there is no derivable "correct" cadence. Shipping conservative
defaults with a supported way to change them is what keeps the
integration safe for a large portfolio and still useful for a manager
who wants deeper history.

**Independent Test**: Change each option from the integration's
options screen and confirm the new cadence and window take effect
without restarting Home Assistant, and that out-of-range values are
rejected with a clear message.

**Acceptance Scenarios**:

1. **Given** the integration is configured with default options,
   **When** the manager opens the options screen, **Then** the
   reservation polling interval, the property polling interval, the
   lookback window, and the lookahead window are all editable and show
   their current values.
2. **Given** the manager sets a polling interval below the enforced
   floor, **When** they submit, **Then** the change is rejected with a
   message naming the minimum allowed value.
3. **Given** the manager widens the lookback window, **When** they
   submit, **Then** the next poll retrieves the additional historical
   reservations without a Home Assistant restart.
4. **Given** the manager changes the selected properties from the
   options screen, **When** they submit, **Then** newly selected
   properties gain devices and entities, deselected properties stop
   being polled and their entities become unavailable, and the entity
   identifiers and recorded history of every property — selected,
   still-selected, or deselected — are preserved.

---

### User Story 5 - Run several Hospitable accounts side by side (Priority: P5)

As a manager who administers more than one Hospitable account, I want
to add each account to Home Assistant separately, so that all of my
portfolios appear in one place without their entities colliding.

**Why this priority**: Multi-account support constrains how entity
identity is derived, so it must be specified from the outset even
though only some users need it. Retrofitting it later would break
existing entity identifiers.

**Independent Test**: Add two config entries with tokens from two
different Hospitable accounts and confirm both sets of properties
appear with distinct, non-colliding entities and independent polling.

**Acceptance Scenarios**:

1. **Given** one Hospitable account is already configured, **When**
   the manager adds a second account with a different token, **Then**
   both entries operate independently and every entity remains
   uniquely addressable.
2. **Given** one Hospitable account is already configured, **When**
   the manager tries to add the same account a second time, **Then**
   the flow refuses and explains that the account is already
   configured.
3. **Given** two configured accounts, **When** one account's token is
   rejected, **Then** only that account's entry enters
   reauthentication and the other continues polling normally.

---

### User Story 6 - Recover when the token expires or is revoked (Priority: P6)

As a property manager, I want Home Assistant to tell me plainly when
my Hospitable token has stopped working and let me supply a new one,
so that my automations do not fail silently a year after I set them
up.

**Why this priority**: Hospitable Personal Access Tokens expire after
one year and can be revoked at any time, so every installation will
eventually hit this. Silent, permanent failure of a config entry is
prohibited.

**Independent Test**: Revoke or replace the token in Hospitable,
confirm Home Assistant raises a reauthentication prompt with an
actionable message, supply a new token, and confirm polling resumes
with all entity history intact.

**Acceptance Scenarios**:

1. **Given** a configured integration whose token has been revoked,
   **When** the next poll is rejected as unauthenticated, **Then**
   Home Assistant surfaces a reauthentication prompt naming the token
   as the cause and describing where to generate a replacement.
2. **Given** a reauthentication prompt is open, **When** the manager
   supplies a valid replacement token, **Then** polling resumes, the
   prompt clears, and the existing entities and their history are
   retained.
3. **Given** a request fails because the account lacks the permission
   scope for an endpoint rather than because the token is invalid,
   **When** the failure is handled, **Then** the integration reports a
   capability limitation and does **not** trigger reauthentication.

---

### User Story 7 - View availability and pricing read-only (Priority: P7)

As a property manager, I want to see each property's near-term
availability and nightly rate in Home Assistant, so that I can put my
open nights on a dashboard.

**Why this priority**: This is genuinely useful but strictly
supplementary, and it is the story most likely to be deferred to a
later phase. It is listed last because none of the earlier stories
depend on it. Writes to the Hospitable calendar are explicitly
excluded from this specification even though a Personal Access Token
is permitted to make them.

**Independent Test**: Confirm each selected property exposes today's
availability and rate, with a short forward window available as
attributes, and confirm that no code path in the integration is
capable of modifying the Hospitable calendar.

**Acceptance Scenarios**:

1. **Given** a property with an open night today, **When** the
   integration polls, **Then** the property's availability sensor
   reports the night as available and carries the nightly rate and
   currency.
2. **Given** a property that is booked today, **When** the integration
   polls, **Then** the availability sensor reports the night as
   booked. It MUST NOT use the word "unavailable" for this, because
   Home Assistant reserves that entity state to mean that the
   integration cannot currently reach the data.
3. **Given** any configuration or service invocation, **When** the
   integration runs, **Then** it never issues a calendar update
   request to Hospitable.

---

### Edge Cases

- **A reservation is in progress but checked in before the lookback
  window opens.** Hospitable filters reservations by check-in date by
  default, so a long stay that began before the window starts would
  otherwise vanish mid-stay and the property would report vacant while
  occupied. The default lookback of ninety days is chosen to cover the
  28-to-90-night long-term stays that are routine in this market.
- **A property has no reservations at all in the window.** The status
  sensor reports no reservation; it does not become unavailable.
- **Hospitable returns paging links using an insecure scheme.**
  Verified live: `meta.links[].url` values come back with an `http://`
  scheme. Following them verbatim would downgrade the connection. The
  integration constructs its own page requests instead.
- **A reservation request is issued without a property filter.**
  Hospitable requires the property filter; a request without it is
  invalid and must never be constructed.
- **A reservation request is issued without dates.** Verified live: a
  reservation query issued without start and end dates returned no
  results. The cause is not established — it could be a narrow default
  window, a default that excludes past reservations, or an interaction
  with the required property filter. The integration always sends an
  explicit window, which is the correct mitigation under any of those
  explanations. (CONFIRMED observation; mechanism UNVERIFIED)
- **The account has many properties.** The property filter is repeated
  once per property in the query string, so a large selection could
  produce an impractically long request. No upstream limit on request
  length or filter count is published, so the integration batches
  defensively at a fixed ceiling rather than against a known bound.
  (UNVERIFIED — no published limit)
- **Hospitable returns HTTP 429.** No general rate limit is published,
  so the integration cannot preempt one. It treats 429 as
  authoritative and backs off.
- **Hospitable returns a scope error.** Verified live: an endpoint
  outside a Personal Access Token's reach returns HTTP 403 with a
  scope-related reason. This is a permanent capability limitation, not
  a bad token, and must not be retried or escalated to
  reauthentication.
- **Hospitable returns a reservation status the integration has never
  seen.** The sensor degrades to an unknown state and logs once.
- **A poll fails transiently.** Entities retain their last known
  values rather than flapping to unavailable on a single failure.
- **A property is removed from Hospitable while still selected, or is
  deselected by the manager.** In both cases its entities become
  unavailable with an explanatory reason and its registry entries are
  retained, so nothing is destroyed and reselection restores history.
- **A reservation is on its arrival or departure date but carries no
  usable scheduled check-in or check-out time.** Occupancy cannot be
  determined, so the sensor reports unknown and logs the defect. No
  midnight or other default time is substituted.
- **Home Assistant restarts mid-window.** State is rebuilt entirely
  from the next poll; no local state is assumed to have survived.
- **Two accounts contain properties with the same name.** Entity
  identity derives from an account namespace and property identifiers,
  not names, so no collision occurs.
- **A reservation belongs to an unlisted or unpublished channel
  listing.** Such reservations are reported to be absent from the
  reservations endpoint entirely. See Open Questions.

## Requirements *(mandatory)*

### Functional Requirements

#### Authentication and credentials

- **FR-001**: The integration MUST authenticate to the Hospitable
  Public API v2 at `https://public.api.hospitable.com/v2` using a
  Personal Access Token presented as an HTTP bearer credential.
  (CONFIRMED)
- **FR-002**: The integration MUST target Public API v2 exclusively.
  It MUST NOT issue requests to Hospitable's internal web-application
  endpoints, to the Hospitable MCP server, or to any other Hospitable
  surface.
- **FR-003**: The integration MUST store the Personal Access Token
  exclusively in Home Assistant's config entry storage. Writing it to
  files, environment variables, or any integration-managed store is
  prohibited.
- **FR-004**: The integration MUST verify the supplied token during
  setup by performing a read request, and MUST NOT create a config
  entry for a token the platform rejects.
- **FR-005**: The integration MUST treat the Personal Access Token as
  an expiring credential that can also be revoked at any time.
  Hospitable Personal Access Tokens expire one year after issue.
  (DOCUMENTED)
- **FR-006**: The integration MUST redact the token from all logs,
  diagnostics output, and exception messages, including from any
  captured request or response body.
- **FR-007**: The integration MUST explain, at the point of token
  entry, that Public API access requires a paid Hospitable plan, that
  the Essentials plan is excluded, and where in the Hospitable account
  a token is generated. (DOCUMENTED)
- **FR-008**: The integration MUST NOT request, accept, or store OAuth
  client credentials in this feature. Personal Access Token entry is
  the only credential model offered. The config flow and the
  credential handling behind it MUST NOT be designed in a way that
  precludes adding the OAuth 2.0 authorization-code flow later.

#### Configuration and options

- **FR-009**: The integration MUST provide a Home Assistant config
  flow with a token entry step followed by a property selection step.
- **FR-010**: The property selection step MUST list the properties
  retrieved live from the authenticated account, presented by their
  human-readable property names.
- **FR-011**: The config flow MUST require at least one property to be
  selected before it can complete, and MUST report clearly when the
  account contains no properties.
- **FR-012**: The integration MUST support multiple concurrent config
  entries, one per Hospitable account.
- **FR-013**: The integration MUST prevent the same Hospitable account
  from being configured twice, identifying the account by a stable
  account identifier obtained from the platform rather than by the
  token value. The platform exposes such an identifier to a Personal
  Access Token as a UUID returned by the user endpoint; FR-055
  retains the fallback that applies if it is ever unavailable.
  (CONFIRMED — see OQ-009)
- **FR-014**: The integration MUST provide a reauthentication flow
  that accepts a replacement token in place of a rejected one and
  preserves all existing entities, entity identifiers, and recorded
  history.
- **FR-015**: The integration MUST provide an options flow exposing,
  at minimum: the reservation polling interval, the property polling
  interval, the reservation lookback window in days, the reservation
  lookahead window in days, and the set of selected properties.
- **FR-016**: The options flow MUST validate every value against a
  documented minimum and maximum, and MUST reject an out-of-range
  value with a message naming the permitted bound.
- **FR-017**: Option changes MUST take effect without a Home Assistant
  restart.
- **FR-018**: Deselecting a property MUST stop polling it and MUST
  mark its entities unavailable with an explanatory reason. Entity
  registry entries MUST be retained, so that reselecting the property
  restores its entity identifiers and recorded history. Deselection is
  therefore non-destructive and matches FR-056's handling of a
  property that disappears upstream.

#### Polling cadence and reservation window

- **FR-019**: The reservation polling interval MUST default to five
  minutes and MUST enforce a floor of one minute that configuration
  cannot lower.
- **FR-020**: The property polling interval MUST default to sixty
  minutes and MUST enforce a floor of fifteen minutes. Property
  records change rarely, so a slower cadence costs nothing.
- **FR-021**: The reservation window MUST default to ninety days
  backward and ninety days forward from the current date, and both
  bounds MUST be configurable.
- **FR-022**: The reservation lookback MUST be configurable from seven
  to three hundred and sixty-five days, and the lookahead from one to
  seven hundred and thirty days. The lookback floor is seven days
  rather than zero because a zero lookback would drop every
  in-progress stay and report occupied properties as vacant.
- **FR-023**: The integration MUST document, in user-facing help text,
  both that widening the window increases the number of upstream
  requests per poll, and that narrowing the lookback can hide
  in-progress long stays and cause an occupied property to report as
  having no reservation.

The defaults above are chosen defensively rather than derived, and it
is worth being explicit about how little can be derived. Hospitable
publishes no general rate limit, so there is no upstream ceiling to
calibrate against. The only sizing observation this project actually
holds is that a single query against one reference account, spanning
2025-01-01 to 2026-12-31 across all of that account's properties,
returned six hundred and eighteen reservations. (CONFIRMED
observation) That account's property count is not known, and the
distribution of those reservations across the window is not known, so
no per-property or per-day booking density can honestly be derived
from it. Any such figure would be invented.

What the specification can control is the shape of its own request
pattern. At the defaults, an account with ten selected properties
issues twenty-four property-list requests per day and two hundred and
forty per-property calendar requests per day — two hundred and
sixty-four requests of fixed overhead — plus two hundred and
eighty-eight reservation polls per day, each costing one request per
hundred reservations in the window. SC-004 bounds the total against a
stated reservation count rather than against an invented density, so
that it can actually be evaluated.

The ninety-day lookback is deliberately long. Hospitable filters
reservations by check-in date by default, so the lookback must exceed
the longest stay the integration expects to see, or an in-progress
stay silently disappears and its property reports as vacant while
occupied. Long-term stays of twenty-eight to ninety nights are routine
in this market, so a shorter lookback — the thirty days an earlier
draft of this specification used — would have produced exactly that
false negative on the integration's primary sensor.

#### API client behavior

- **FR-024**: The integration MUST consume Hospitable field names as
  returned. Hospitable uses `snake_case` throughout, so no field-name
  translation layer is required or permitted. (CONFIRMED)
- **FR-025**: The integration MUST page through every list endpoint
  using the platform's page and page-size parameters, MUST NOT request
  a page size above one hundred, and MUST use the response metadata to
  determine when paging is complete. (CONFIRMED)
- **FR-026**: The integration MUST construct every page request itself
  over HTTPS. It MUST NOT follow the pagination link values returned
  in the response body verbatim, because those values are returned
  with an insecure `http://` scheme and following them would downgrade
  the connection. (CONFIRMED by live observation)
- **FR-027**: Every request the integration issues MUST use HTTPS with
  certificate verification enabled. No configuration option may
  disable either.
- **FR-028**: The integration MUST include an explicit property filter
  on every reservation query, because the reservations endpoint
  requires it. (CONFIRMED)
- **FR-029**: The integration MUST send an explicit start date and end
  date on every reservation query, derived from the configured window.
  Verified live: a reservation query issued without start and end
  dates returned no results. The underlying cause is not established.
  (CONFIRMED observation; mechanism UNVERIFIED)
- **FR-030**: The integration MUST send the reservation date-filter
  mode explicitly rather than relying on the platform default.
- **FR-031**: The integration MUST send no more than fifty property
  identifiers in a single reservation query, splitting a larger
  selection across multiple batched requests and merging them into a
  single consistent result set. No upstream limit on request length or
  filter count is published; fifty is a defensive implementation
  ceiling, not a value derived from any known bound. (UNVERIFIED — no
  published limit)
- **FR-032**: The integration MUST read reservation status from the
  current-status field of the platform's structured reservation status
  object. It MUST NOT read the platform's deprecated flat status or
  status-history fields. (CONFIRMED)
- **FR-033**: The integration MUST request guest information as an
  include on the reservation query when guest data is surfaced,
  because Hospitable exposes no standalone guest resource, and MUST
  behave correctly when that data is absent. (CONFIRMED)
- **FR-034**: The integration MUST validate the shape of every
  response against the structure it expects, and MUST raise an
  explicit error rather than producing a partially populated entity
  when a response does not match.
- **FR-035**: The integration MUST translate platform errors into
  typed errors carrying the HTTP status, the endpoint, and a redacted
  excerpt of the response body.
- **FR-036**: The integration MUST treat HTTP 429 as authoritative,
  MUST honor any retry-delay or rate-limit headers present on the
  response, and MUST otherwise apply exponential backoff with jitter.
  Hospitable publishes no general numeric rate limit, so the
  integration MUST NOT hard-code a quota, and MUST NOT assume that
  rate-limit headers are present. (Header behavior: UNVERIFIED)
- **FR-037**: The integration MUST bound its retry attempts and MUST
  surface a clear, actionable error once they are exhausted rather
  than retrying indefinitely.
- **FR-038**: The integration MUST distinguish an HTTP 403 caused by
  insufficient token scope from an HTTP 401 caused by an invalid or
  expired token. A scope failure MUST be reported as a permanent
  capability limitation, MUST NOT be retried, and MUST NOT trigger
  reauthentication. (CONFIRMED: a scope-restricted endpoint returns
  HTTP 403 with a scope-related reason phrase while the same token
  succeeds on permitted endpoints)
- **FR-039**: The integration MUST bound its memory use by retaining
  only the reservations that fall inside the configured window.
  Unbounded accumulation of reservation history is prohibited.
- **FR-040**: All integration input and output MUST use asynchronous
  patterns and MUST NOT block the Home Assistant event loop.
- **FR-041**: The integration MUST tear down every HTTP client,
  listener, and background task when a config entry is unloaded or
  removed.

#### Reservation status entities

- **FR-042**: The integration MUST expose exactly one reservation
  status entity per selected property, regardless of how many
  reservations that property has. Per-reservation entities are
  prohibited.
- **FR-043**: The reservation status entity MUST report one of a
  fixed, documented set of states covering at minimum: occupied,
  awaiting check-in, checked out, pending request, checkpoint,
  cancelled, not accepted, unknown, and no reservation. This enum is
  single-dimensional: it encodes reservation status and occupancy
  only. It MUST NOT encode stay type, which is exposed as an attribute
  under FR-049.
- **FR-044**: When a property has more than one reservation in the
  window, the entity MUST select the single most operationally
  relevant reservation using this priority ordering, applied in order
  until one reservation is selected:
  1. A reservation that is currently in progress under FR-045.
  2. The soonest future arrival, by arrival date then scheduled
     check-in time.
  3. The most recent past departure, by departure date then scheduled
     check-out time.

  Reservations whose status category is cancelled or not accepted rank
  below all others within every tier. Any remaining tie MUST be broken
  by ascending reservation identifier, so that selection is
  deterministic. The reservations not selected MUST be exposed as an
  upcoming-reservations attribute.
- **FR-045**: Hospitable publishes no checked-in status, so the
  integration MUST derive occupancy itself. It MUST do so from the
  reservation's scheduled check-in and check-out moments, never from
  calendar-day boundaries. Specifically:
  - A reservation is occupied from its scheduled check-in moment until
    its scheduled check-out moment.
  - Before the scheduled check-in moment, including earlier on the
    arrival date itself, the state is awaiting check-in.
  - At or after the scheduled check-out moment, including later on the
    departure date itself, the state is checked out.
  - All comparisons MUST be evaluated in the property's own timezone.
    Where the property timezone is absent or cannot be interpreted as
    a usable timezone, the integration MUST fall back to the Home
    Assistant instance timezone and MUST log which timezone it chose,
    at most once per property. See OQ-002, which records that the
    platform's timezone field may be a UTC offset string rather than a
    named timezone.
  - A missing or uninterpretable scheduled check-in or check-out time
    is a data error, not a case to work around. On the arrival or
    departure date of an affected reservation the entity MUST report
    the unknown state and MUST log a warning naming the reservation
    and the missing field. It MUST NOT report the property as
    occupied, and it MUST NOT substitute midnight or any other assumed
    time. Away from those two boundary dates the state is unaffected,
    because no scheduled time is needed to evaluate it.

  (CONFIRMED that no checked-in status appears in the published status
  list; see OQ-008 on whether that list is exhaustive)
- **FR-046**: The reservation status entity MUST expose, as
  attributes, at minimum: arrival date, departure date, number of
  nights, scheduled check-in and check-out times, total guest count
  with its adult, child, infant, and pet breakdown, booking channel,
  channel confirmation identifier, booking date, stay type, and the
  reservation identifier.
- **FR-047**: The reservation status entity MUST report the
  no-reservation state, rather than becoming unavailable, when the
  property has no reservation in the window.
- **FR-048**: The integration MUST map an unrecognised platform status
  to the unknown state, MUST log the unrecognised value at most once
  per distinct value, and MUST NOT raise. Every status category in the
  platform's published list MUST map to a defined state under FR-043,
  so this fallback applies only to values outside that list and MUST
  NOT fire for a published category such as checkpoint.
- **FR-049**: The integration MUST expose stay type as an attribute
  distinguishing an owner stay from a guest stay, using the platform's
  stay-type field. Stay type MUST NOT be folded into the status enum
  of FR-043, because it is an orthogonal dimension: an owner stay can
  independently be awaiting check-in, occupied, checked out, or
  cancelled. (CONFIRMED)

#### Property entities

- **FR-050**: The integration MUST create one Home Assistant device
  per selected property.
- **FR-051**: The integration MUST expose next-arrival and
  next-departure timestamp entities per property, reporting no value
  when there is no applicable future reservation.
- **FR-052**: The integration MUST expose a count of upcoming
  reservations within the configured window per property.
- **FR-053**: The integration MUST expose a property information
  entity per property carrying, at minimum, the property address, its
  configured check-in and check-out times, its guest capacity, its
  timezone as reported by the platform, and its channel listings with
  each listing's channel and channel identifier.
- **FR-054**: Entity identifiers MUST follow the pattern
  `sensor.hospitable_<property>_<attribute>`. This specification
  creates entities on the sensor platform only; no other Home
  Assistant entity platform is used.
- **FR-055**: Every entity's unique identifier MUST derive solely from
  immutable identifiers, specifically an account namespace, the
  property identifier, and the entity's own key. The account namespace
  MUST be the stable platform account identifier of FR-013 where one
  is available, which is confirmed to be a UUID returned by the user
  endpoint; where none is available, it MUST be the config entry's
  own immutable entry identifier, which Home Assistant guarantees is
  stable for the life of the entry. That fallback is retained as a
  defensive branch and is not expected to be taken now that the
  platform identifier is confirmed. Whichever namespace is chosen
  MUST be recorded in the config entry when it is created and MUST
  NOT change thereafter, because changing it would orphan every
  entity and destroy its recorded history. Renaming a property in
  Hospitable MUST NOT orphan entities or destroy recorded history.
  (Availability of a platform account identifier: CONFIRMED — see
  OQ-009)
- **FR-056**: When a monitored property disappears from the account,
  its entities MUST become unavailable with an explanatory reason
  rather than being silently deleted.
- **FR-057**: When a poll fails, entities MUST retain their last known
  values, and MUST become unavailable only after three consecutive
  failed polls.

#### Calendar visibility

- **FR-058**: The integration MUST expose each selected property's
  availability for the current day, together with its nightly rate and
  currency, as read-only sensor data, and MUST make a short forward
  window available as attributes. The availability state MUST use a
  term such as "booked" for an unavailable night and MUST NOT use the
  word "unavailable", which Home Assistant reserves to mean that the
  entity's data cannot currently be reached. The response shape of the
  property calendar endpoint has not been examined; if it does not
  carry per-day availability and rate in the assumed form, this
  requirement MUST be revised before implementation. (UNVERIFIED
  response shape — see OQ-010)
- **FR-059**: The integration MUST NOT issue any calendar modification
  request to Hospitable under any circumstance, even though a Personal
  Access Token is permitted to make them.
- **FR-060**: Monetary values MUST be interpreted as integer minor
  currency units accompanied by a currency code, and MUST NOT be
  presented to the user as if they were major units. (CONFIRMED on
  reservation financials; the calendar response has not been examined
  — see OQ-010)
- **FR-061**: Calendar data MUST be refreshed on the property polling
  cadence, not the reservation cadence.

#### Privacy, diagnostics, and platform

- **FR-062**: Guest personal data — names, email addresses, phone
  numbers, and message content — MUST NOT be written at debug level
  and MUST be redacted from diagnostics output.
- **FR-063**: The integration MUST provide a Home Assistant
  diagnostics download containing enough detail to troubleshoot, with
  all credentials and guest personal data redacted.
- **FR-064**: Every user-facing error MUST state what failed and what
  the user should do about it. A bare HTTP status code is not an
  acceptable user-facing error.
- **FR-065**: A configuration entry MUST NOT fail silently and
  permanently. Every credential rejection MUST raise a
  reauthentication flow, and every persistent non-credential failure
  MUST raise a repair issue — except a scope-related HTTP 403, which
  is handled under FR-038 as a permanent capability limitation and
  MUST NOT raise a repair issue, because the affected capability is
  omitted rather than surfaced to the user as failing.
- **FR-066**: The integration MUST declare a minimum supported Home
  Assistant version of 2026.8.0 and MUST remain installable through
  HACS.
- **FR-067**: The integration MUST function correctly using polling
  alone. It MUST NOT depend on webhook delivery for correctness.
- **FR-068**: All user-facing text MUST use the term "property" for
  Hospitable's core rental unit and "listing" only for a channel-side
  mapping, matching Hospitable's own vocabulary.
- **FR-069**: The integration MUST be organized internally into
  separate API client, services, and sensor packages from the outset,
  rather than as flat modules, so that later phases can add domains
  without restructuring. The `services` package holds the domain and
  business logic that sits between the API client and the entities —
  reservation selection, occupancy derivation, status mapping, and
  window computation. It is **not** Home Assistant service-call
  registration, despite the name colliding with that reserved Home
  Assistant term; this specification defines no user-invocable Home
  Assistant services. This is recorded as a binding constraint because
  it governs where later specifications may add code.
- **FR-070**: The config entry MUST carry a version and a minor
  version, and the integration MUST implement a migration path that
  upgrades an entry written by an earlier release. The unique
  identifier format defined in FR-055 is frozen: it MUST NOT be
  changed by any later specification without a migration that
  preserves every existing entity identifier and its recorded history.
- **FR-071**: The integration MUST avoid redundant upstream requests
  by caching responses that are shared across entities for at least
  the duration of the polling interval that produced them, and MUST
  document its cache invalidation strategy. Each entity MUST read from
  shared, coordinated data rather than issuing its own requests.
- **FR-072**: The options flow MUST display the estimated number of
  upstream requests per day implied by the currently entered polling
  intervals, window bounds, and property selection, so that the
  warnings required by FR-023 are actionable rather than abstract. The
  estimate MUST be labelled as an estimate.
- **FR-073**: When the integration retrieves the account record in
  order to obtain the account identifier of FR-013, it MUST retain
  only that identifier. The personal, billing, and address fields
  the same response carries — the account holder's email address,
  name, postal address, company name, VAT number, and tax identifier
  — MUST NOT be persisted, MUST NOT be written to the log at any
  level, and MUST be redacted from diagnostics output. This applies
  the handling FR-062 and FR-063 require for guest personal data to
  the account holder's own personal and billing data.

### Key Entities

- **Property**: Hospitable's core rental unit and the unit of
  selection in this integration. Identified by a stable universally
  unique identifier. Carries a name, an address, configured check-in
  and check-out times, guest capacity, a timezone, and one or more
  Listings. One Home Assistant device is created per selected
  Property.
- **Listing**: A channel-side mapping of a Property onto a booking
  platform such as Airbnb, Vrbo/HomeAway, Booking.com, or a direct
  channel. A Property has one or more Listings. Listings are surfaced
  as property information, never as devices in their own right, and
  are never the unit of selection.
- **Reservation**: A booking against a Property. Identified by a
  stable universally unique identifier. Carries a booking channel and
  channel identifier, booking date, arrival and departure dates, night
  count, scheduled check-in and check-out times, a structured status
  with a current value and a history, a guest breakdown by adults,
  children, infants, and pets, a stay type distinguishing guest stays
  from owner stays, and a conversation identifier. Reservations are
  never modeled as individual Home Assistant entities.
- **Guest**: The person or party on a Reservation. Hospitable exposes
  no standalone guest resource; guest data is reachable only as an
  include on a Reservation. Guest data is personal data and is subject
  to the redaction requirements above.
- **Reservation status**: The structured status object on a
  Reservation, carrying a current value and a history. Its categories
  are request, accepted, cancelled, not accepted, unknown, and
  checkpoint. The integration reads this object and never the
  deprecated flat status fields.
- **Money amount**: Every monetary value the platform returns,
  expressed as an integer count of minor currency units together with
  a currency code and a preformatted display string.
- **Account connection**: A single Home Assistant config entry
  representing one authenticated Hospitable account. Holds the
  Personal Access Token, the account namespace used to prevent
  duplicate entries and to namespace entity identifiers — the platform
  account identifier where one is available, otherwise the config
  entry's own identifier, per FR-055 — the selected Property
  identifiers, the polling and window options, and the entry version
  required by FR-070.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A manager who already holds a Personal Access Token can
  complete setup — token entry through property selection — in under
  three minutes.
- **SC-002**: A reservation change made in Hospitable is reflected in
  the corresponding Home Assistant entity within one reservation
  polling interval, which is five minutes at the default setting, in
  at least ninety-five percent of observations.
- **SC-003**: A full refresh for an account with ten selected
  properties and the default window completes in under thirty seconds.
- **SC-004**: At default settings, with ten selected properties and no
  more than five hundred reservations inside the reservation window,
  the integration issues fewer than two thousand upstream API requests
  per day, counting reservation polls, property polls, and
  per-property calendar polls together. Two thousand requests per day
  averages about 1.4 per minute, but the daily total is the binding
  bound; the per-minute figure is an average derived from it and not a
  second, independent ceiling.
- **SC-005**: The integration runs for thirty consecutive days without
  manual intervention, restart, or entity loss, given a token that
  remains valid.
- **SC-006**: Renaming any property in Hospitable preserves one
  hundred percent of that property's entity identifiers and recorded
  history.
- **SC-007**: When the platform returns a rate-limit response, the
  integration resumes normal polling at the earliest time the response
  permits, or within five minutes if the response supplies no retry
  delay, without losing entity state and without a crash.
- **SC-008**: An audit of all logs at every level and of a full
  diagnostics download finds zero occurrences of the Personal Access
  Token and zero unredacted guest names, email addresses, or phone
  numbers.
- **SC-009**: A revoked or expired token produces a visible,
  actionable reauthentication prompt within one polling interval, and
  supplying a replacement restores polling with zero entity loss.
- **SC-010**: Five Hospitable accounts configured in a single Home
  Assistant instance produce zero entity identifier collisions and
  poll independently.
- **SC-011**: Changing any polling or window option takes effect on
  the next poll with no Home Assistant restart, in one hundred percent
  of cases.
- **SC-012**: A property with no reservations in the window reports a
  definite no-reservation state rather than an unavailable or empty
  one, in one hundred percent of cases.
- **SC-013**: With ten selected properties on Raspberry-Pi-class
  hardware, no single integration operation blocks the Home Assistant
  event loop for more than one hundred milliseconds.

## Assumptions

### About the platform

- The Hospitable account used has a paid plan. Public API access is
  unavailable on the Essentials plan. (DOCUMENTED)
- Personal Access Token permissions are coarse-grained: a read
  permission covering properties, reservations, and calendar, and a
  write permission covering calendar pricing and availability only.
  This specification uses read access only. (DOCUMENTED)
- The reservation resource is read-only. There is no update operation
  on a reservation in the Public API, so no reservation field can be
  written by this integration. (CONFIRMED)
- The enrichment resource, which carries Hospitable's writable
  per-reservation smart-lock code, is vendor-gated and unreachable
  with a Personal Access Token. This was verified empirically: on one
  reservation, with one token, the reservation itself returned success
  while the same reservation's enrichment returned HTTP 403 with a
  scope-related reason. There is no self-serve path to the required
  scopes; they require OAuth vendor credentials obtained through an
  application form and partner approval. Door codes are therefore out
  of scope for this specification. (CONFIRMED)
- Hospitable field naming is `snake_case` throughout, so unlike
  comparable platforms no field-name translation layer is needed.
  (CONFIRMED)
- Hospitable's list endpoints use a conventional page-and-page-size
  paginator with a maximum page size of one hundred and a response
  envelope carrying current page, last page, page size, and total.
  (CONFIRMED)
- Hospitable publishes no general numeric rate limit. The only
  published quantitative limits concern message sending, which this
  specification does not use. (CONFIRMED by absence)
- Task, teammate, and team-group resources are absent from
  Hospitable's published Public API specification, in a snapshot dated
  2025-06-21. Third-party documentation references them, so they may
  exist but be vendor-gated or otherwise non-public. Absence from a
  published specification is not proof of non-existence, so no
  comparable feature from another platform integration is specified
  here. (UNVERIFIED)
- Hospitable exposes no standalone guest resource. Guest data is
  reachable only as an include on a reservation or inquiry.
  (CONFIRMED)
- The Hospitable Public API surface remains at version two, carried in
  the request path.

### About this integration

- Polling is sufficient for correctness in this release. Webhooks
  would improve timeliness but are not required for the integration to
  be correct, and are deferred to their own specification.
- A manager monitors a manageable portfolio, on the order of tens of
  properties rather than hundreds, within one config entry.
- The Home Assistant instance has stable outbound internet access to
  the Hospitable API.
- The minimum supported Home Assistant version is 2026.8.0, which is
  the version pinned by the project's Home Assistant test harness.
- Personal Access Token entry is the primary, self-serve credential
  model and the only one this specification delivers. OAuth is
  deferred to a dedicated future specification, gated on Hospitable
  Vendor access actually being obtained, and is not a precondition for
  any release. The design constraint that keeps that door open is
  recorded as FR-008.
- The internal package structure — separate API client, services, and
  sensor packages — is adopted from the first commit rather than
  refactored into later, because later phases will add domains that
  assume it.

## Open Questions

These are unresolved at specification time. Each one must be settled
during implementation or planning, and none of them may be treated as
settled by assumption. A question that has since been settled is kept
here for the historical record, restated as **RESOLVED**, with the
answer and how it was obtained recorded in place of the original
uncertainty.

- **OQ-001 — Smart-lock code interaction (UNVERIFIED).** Hospitable
  automatically generates smart-lock codes for accepted reservations
  and documents that it "can only manage the codes it creates". How an
  API-set enrichment value would interact with, override, or conflict
  with an account-generated code is entirely undocumented. This does
  not affect the present specification, which writes nothing, but it
  must be resolved before any future door-code specification is
  written.
- **OQ-002 — Property timezone format (LIKELY, needs verification).**
  A third party reports that the property timezone field is a UTC
  offset string such as `-0500` rather than a named IANA timezone. If
  that is correct, the value cannot be used directly by Home Assistant
  and must be mapped, and the mapping must account for a bare offset
  carrying no daylight-saving information — so a property whose offset
  was captured in one season will be an hour wrong in the other. This
  question is load-bearing rather than cosmetic: FR-045 evaluates
  occupancy against scheduled check-in and check-out moments in the
  property's timezone, so an hour of error moves the exact instant at
  which an arrival or departure automation fires. FR-045 already
  mandates a fallback to the Home Assistant instance timezone, with
  the choice logged, so the requirement is implementable either way,
  but this must be verified against a live account before FR-045 is
  implemented.
- **OQ-003 — Reservation status filter semantics (UNVERIFIED).** It is
  not confirmed that a status filter parameter exists on the
  reservations endpoint at all; it is absent from Hospitable's own
  published parameter list. A third party additionally reports that
  the filter accepts an underscored form while responses return a
  spaced form, and that one documented status value is rejected
  outright as a filter. This specification therefore does not rely on
  server-side status filtering; all status handling is performed
  client-side after retrieval. If server-side filtering is later
  confirmed to work, it becomes an optimization, not a correction.
- **OQ-004 — Reservations on unlisted listings (LIKELY, needs
  verification).** A third party reports that reservations belonging
  to unlisted or unpublished channel listings are absent entirely from
  the reservations endpoint, despite appearing in Hospitable's own
  calendar interface. If true, this is a data-completeness limitation
  that users must be told about, because a property could appear
  vacant in Home Assistant while Hospitable shows it as booked. This
  must be verified and, if confirmed, documented in user-facing
  documentation.
- **OQ-005 — Rate limiting (CONFIRMED absent, behavior UNVERIFIED).**
  No general numeric rate limit is published. Whether any rate-limit
  or retry-delay headers are returned at all, and under what
  conditions HTTP 429 is issued, is unverified. The chosen defaults
  are conservative precisely because there is nothing to calibrate
  against; they should be revisited if Hospitable publishes limits or
  if observed behavior provides evidence.
- **OQ-006 — Insecure pagination links (CONFIRMED, permanence
  unknown).** Pagination link values are returned with an insecure
  scheme. It is unknown whether this is a deliberate upstream
  behavior or a defect that may be corrected. The mitigation in
  FR-026 is correct either way, so no action depends on the answer,
  but it should be reported upstream.
- **OQ-007 — Token expiry visibility (UNVERIFIED).** Personal Access
  Tokens expire after one year and Hospitable displays the expiry date
  in its interface, but it is unverified whether expiry is discoverable
  through the API. If it is, the integration could warn ahead of
  expiry instead of only reacting to rejection. If it is not, reactive
  handling under FR-065 is the only option.
- **OQ-008 — Reservation status category coverage (CONFIRMED list,
  coverage UNVERIFIED).** The published status categories are known,
  but the sub-category values beneath them are numerous and it is
  unverified whether the published list is exhaustive. FR-048's
  unknown-state fallback exists precisely to absorb this uncertainty.
  This is also why FR-045 claims only that no checked-in status
  appears in the published list, not that none exists.
- **OQ-009 — Stable account identifier (RESOLVED).** FR-013 and
  FR-055 both depend on the platform exposing a stable, immutable
  account identifier that a Personal Access Token can retrieve. This
  was the most irreversible open question in the specification: the
  account namespace is baked into every entity's unique identifier
  and cannot be changed later without orphaning every entity and
  destroying its recorded history. **Answer:** a live test against a
  real account established that the user endpoint is reachable with a
  Personal Access Token and returns a stable UUID account identifier,
  held in a field distinct from the mutable email field. FR-013 and
  FR-055 therefore rest on confirmed behavior. FR-055 keeps the
  config entry identifier as a defensive fallback, which is no longer
  expected to be taken. The same response also carries personal and
  billing fields, which FR-073 requires be discarded rather than
  persisted, logged, or included in diagnostics.
- **OQ-010 — Property calendar response shape (UNVERIFIED).** US7 and
  FR-058 assume the property calendar endpoint returns per-day
  availability together with a nightly rate and currency. The endpoint
  is confirmed to exist, but no response schema for it has been
  examined, and FR-060's money shape was confirmed on reservation
  financials rather than on calendar days. If the shape differs, US7
  and FR-058 must be revised before implementation. This affects only
  the lowest-priority user story.

## Out of Scope

The following are explicitly excluded from this specification. Each is
excluded for a stated reason, and several are expected to return in
later specifications.

- **Door codes and reservation enrichment.** Hospitable's writable
  per-reservation smart-lock code lives behind a vendor-gated
  enrichment resource that a Personal Access Token cannot reach. This
  was confirmed empirically, not merely inferred from documentation.
  Door codes will be addressed in a dedicated future specification
  once the vendor path is understood. No capability detection, no
  partial implementation, and no placeholder service is included here.
- **OAuth and vendor access.** The OAuth authorization-code flow
  requires vendor credentials obtained through an application form and
  partner-portal approval. There is no self-serve path, so it cannot
  be a prerequisite for a self-hosted Home Assistant user. It is
  deferred to the same future specification as door codes.
- **Webhooks and real-time events.** This specification is
  polling-only. Hospitable webhooks can only be registered through its
  dashboard, with no API for registration, and the signature
  verification mechanism is not officially documented. Webhooks will
  receive their own specification.
- **Calendar writes.** Availability and pricing updates are excluded
  even though a Personal Access Token is permitted to make them.
  Writing to a property's calendar has direct revenue consequences and
  deserves its own specification with its own safeguards.
- **Tasks, teammates, and team groups.** These resources are not
  present in Hospitable's published Public API surface. They may exist
  but be vendor-gated or non-public, so no comparable feature from
  another property-management platform integration is ported here.
  (UNVERIFIED — see the Assumptions section)
- **Guest messaging.** Reading and sending messages on reservations
  and inquiries is possible but is a separate domain with its own
  published sending limits and its own personal-data handling
  obligations.
- **Reviews.** Reading reviews and responding to them is out of scope.
- **Inquiries.** Pre-booking conversation threads are out of scope;
  only confirmed reservations are surfaced.
- **Financials, payouts, and transactions.** Revenue reporting is out
  of scope.
- **Quote generation.** Generating booking quotes is out of scope.
- **Property tags.** Writing tags to a property is possible with a
  Personal Access Token but serves no purpose for this integration.
- **Home Assistant calendar platform entities.** Reservations are not
  exposed as calendar entities in this specification. Only sensor
  entities are created.
- **Per-reservation entities.** Explicitly rejected as a design, not
  merely deferred. One reservation status entity per property is the
  intended end state, not a stepping stone.
