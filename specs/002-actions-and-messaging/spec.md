<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Feature Specification: Actions (Services) for Lookup and Guest Messaging

**Feature Branch**: `002-actions-and-messaging`

**Created**: 2026-08-11

**Status**: Draft

**Input**: User description: "Actions (services) for lookup and guest
messaging — send message, read thread, lookup reservations, get
property info, task/cleaning sensors, awaiting-host-reply
indicators, and guest name exposure on reservation entities."

## Overview

Spec 001 delivered a strictly read-only, polling-based integration.
This specification extends it with the first write capability — guest
messaging — alongside lookup actions, task sensors, message-presence
indicators, and guest identity exposure on reservation entities.

The extension is carefully scoped: every write is user-invoked through
a Home Assistant service call. No coordinator, poll, setup, reload, or
unload path may issue a write. The existing `test_no_writes.py`
lifecycle assertion is narrowed from "no non-GET requests anywhere" to
"no non-GET requests in the polling lifecycle," preserving its
protective intent while acknowledging that explicit user actions now
perform POSTs.

### Evidence confidence legend

This specification uses the same confidence tiers as spec 001.

| Marker | Meaning |
| --- | --- |
| **CONFIRMED-BY-TEST** | Verified empirically against a live Hospitable account (read-only probes only; no POST has ever been executed). |
| **CONFIRMED-BY-SPEC** | Read directly from Hospitable's own OpenAPI export, but not confirmed by a live grant. |
| **DOCUMENTED** | Stated in Hospitable's current official documentation, but not verified empirically. |
| **LIKELY** | Reported by an independent third party who claims live verification, but not reproduced by this project. |
| **UNVERIFIED** | Single-source, undocumented, or inferred. Must not be relied upon without a test. |

### Critical architectural decision: narrowing the read-only guarantee

Spec 001 established a structural read-only guarantee: the API client
exposed only `_get`, and `test_no_writes.py` asserted every captured
request across setup, refresh, reload, and unload was a GET.

This specification introduces the first POST (guest messaging). The
new boundary is:

> **Writes occur ONLY via explicit user-invoked service calls; never
> from polling, coordinators, setup, reload, or unload. The
> `test_no_writes.py` assertion is narrowed to cover the polling
> lifecycle (setup → refresh → options change → reload → unload) and
> remains a hard gate. No write may originate from any automated path.**

This narrowing is stated as functional requirements FR-001 through
FR-004 below.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Send a message to a guest (Priority: P1)

As a property manager, I want to send a text message to a guest for a
specific reservation through a Home Assistant service call, so that my
automations can send check-in instructions, welcome messages, or
notifications triggered by property events.

**Why this priority**: This is the core ask and the reason this
specification exists. It introduces the first write capability and
establishes the architectural pattern all future writes will follow.

**Independent Test**: Invoke the service call with a reservation
identifier and message body, confirm the integration issues a POST to
`/reservations/{uuid}/messages` with the correct payload, and confirm
it returns a correlation response indicating acceptance.

**Acceptance Scenarios**:

1. **Given** a valid reservation UUID and a non-empty message body,
   **When** the user invokes the send-message service, **Then** the
   integration issues a POST to the Hospitable messaging endpoint and
   reports acceptance (HTTP 202).
2. **Given** a message body and optional image URLs (up to 3),
   **When** the user invokes the send-message service, **Then** the
   images are included in the request payload.
3. **Given** an Airbnb reservation and a valid co-host `sender_id`,
   **When** the user invokes the send-message service with that
   sender_id, **Then** the message is sent on behalf of the co-host.
4. **Given** a non-Airbnb reservation and a `sender_id`, **When** the
   user invokes the send-message service, **Then** the integration
   rejects the call with a validation error explaining that sender_id
   is only supported for Airbnb reservations.
5. **Given** a reservation that does not exist or is not accessible,
   **When** the user invokes the send-message service, **Then** the
   integration reports a clear error without crashing.
6. **Given** the rate limit is reached (2/min per reservation or
   50/5min per token), **When** the user invokes the service, **Then**
   the integration reports a rate-limit error with a human-readable
   explanation.
7. **Given** the service is called during a coordinator refresh,
   **When** the refresh completes, **Then** no write was issued by the
   refresh; only the explicit service call issued a POST.

---

### User Story 2 — Read the message thread for a reservation (Priority: P2)

As a property manager, I want to retrieve the full message thread for
a reservation through a service call, so that I can display
conversation context in dashboards or feed it into automation logic.

**Why this priority**: Reading messages complements sending them and
uses a confirmed GET endpoint. It exercises the lookup-action pattern
that all other lookup services share.

**Independent Test**: Invoke the read-messages service with a
reservation UUID and confirm it returns the message array with sender,
body, timestamp, and attachments.

**Acceptance Scenarios**:

1. **Given** a valid reservation UUID with messages, **When** the user
   invokes the read-messages service, **Then** it returns the message
   array with each message's body, sender_type, sender_role,
   created_at, and attachments.
2. **Given** a reservation with no messages, **When** the service is
   invoked, **Then** it returns an empty array without error.
3. **Given** an invalid reservation UUID, **When** the service is
   invoked, **Then** it returns a not-found result
   (`{"found": false, ...}`), not an exception.

---

### User Story 3 — Lookup actions for reservations and properties (Priority: P3)

As a property manager, I want service calls that look up reservation
details, list reservations for a property, and retrieve property
information, so that my automations and scripts can query live data on
demand without depending solely on polled state.

**Why this priority**: Lookup actions are the read-only complement to
messaging and are low-risk because they issue only GET requests. They
establish the service-registration infrastructure that messaging also
uses.

**Independent Test**: Invoke each lookup service and confirm it returns
structured data matching the Hospitable API response shape, with
not-found handled as a return value.

**Acceptance Scenarios**:

1. **Given** a reservation UUID, **When** the user invokes
   find-reservation, **Then** it returns the reservation object or
   `{"found": false}`.
2. **Given** a property identifier, **When** the user invokes
   get-reservations, **Then** it returns the list of reservations for
   that property within the configured window.
3. **Given** a property identifier, **When** the user invokes
   get-property-info, **Then** it returns the property's details
   including listings and co-hosts.
4. **Given** multiple config entries, **When** a lookup is called
   without specifying `config_entry_id`, **Then** if exactly one entry
   exists it is auto-selected; if multiple exist, a
   ServiceValidationError explains that `config_entry_id` is required.

---

### User Story 4 — Task and cleaning sensors (Priority: P4)

As a property manager, I want Home Assistant to poll the `/tasks`
endpoint and expose task/cleaning sensors per property, so that I can
automate cleaning schedules, see assignment status, and trigger
notifications when tasks change state.

**Why this priority**: Tasks are a distinct polling domain that
enriches property management automations. They use only GET requests
and the endpoint is confirmed accessible.

**Independent Test**: Confirm each selected property exposes a
next-task sensor and a task-count sensor updated from the `/tasks`
endpoint, and that pagination is handled correctly.

**Acceptance Scenarios**:

1. **Given** a property with upcoming tasks, **When** the task
   coordinator polls, **Then** the property's next-task sensor reports
   the soonest task with its type, assignment status, progress, and
   scheduled date.
2. **Given** tasks span multiple pages, **When** the coordinator
   polls, **Then** all pages are fetched and no tasks are silently
   lost.
3. **Given** a property with no tasks in the window, **When** the
   coordinator polls, **Then** the next-task sensor reports no value
   rather than becoming unavailable.
4. **Given** a task whose type is Maintenance (task_type 5, service_id
   8), **When** the sensor displays it, **Then** it is correctly
   labelled Maintenance, not conflated with another type.

---

### User Story 5 — Message presence indicators (Priority: P5)

As a property manager, I want per-property sensors showing the last
message timestamp and whether a guest message is awaiting a host
reply, so that I can build dashboard indicators and trigger
notification automations.

**Why this priority**: `last_message_at` derives from polled data at
zero extra cost. The awaiting-host-reply indicator requires a per-
property message fetch and is therefore opt-in, defaulting to OFF.

**Independent Test**: Confirm each property with an active reservation
exposes a `last_message_at` timestamp sensor. When the
awaiting-host-reply option is enabled, confirm the indicator sensor
correctly reflects whether the most recent message came from the
guest.

**Acceptance Scenarios**:

1. **Given** a property's active reservation has `last_message_at`
   set, **When** the reservation coordinator polls, **Then** the
   property's last-message-at sensor reports that timestamp.
2. **Given** a property with no active reservation or no messages,
   **When** the reservation coordinator polls, **Then** the last-message-at
   sensor reports no value rather than becoming unavailable.
3. **Given** the awaiting-host-reply option is enabled, **When** the
   most recent message in a reservation thread has `sender_type`
   indicating a guest, **Then** the awaiting-host-reply sensor reports
   true.
4. **Given** the awaiting-host-reply option is disabled (the default),
   **When** the coordinator polls, **Then** no message-fetch API calls
   are made and the awaiting-host-reply sensor is not created.

---

### User Story 6 — Guest name and contact on reservation entities (Priority: P6)

As a property manager, I want the guest's name visible as an attribute
on the reservation status entity, so that my dashboards and
automations can reference who is arriving or currently in-house.

**Why this priority**: Guest identity is high-value for automations
(e.g., welcome messages, door labels) but carries PII obligations.
It is last because it depends on the privacy framework already being
proven.

**Independent Test**: Confirm the reservation status entity's
attributes include the guest name, and confirm that logs and
diagnostics never contain the guest name unredacted.

**Acceptance Scenarios**:

1. **Given** a reservation with `include=guest` returning a non-null
   guest object, **When** the reservation coordinator polls, **Then**
   the reservation status entity attributes include
   `guest_first_name`, `guest_last_name`, `guest_location`, and
   `guest_language`.
2. **Given** the guest-contact-details option is enabled, **When** the
   reservation coordinator polls, **Then** `guest_email` and
   `guest_phone_numbers` are additionally exposed as attributes.
3. **Given** a guest whose `last_name` is null, **When** the entity
   updates, **Then** `guest_last_name` reports no value and any
   display-name derivation shows only the first name.
4. **Given** any log level or diagnostics download, **When** the
   output is audited, **Then** no guest field (`first_name`,
   `last_name`, `email`, `phone_numbers`, `location`, `language`,
   `profile_picture`) is present unredacted.
5. **Given** any service call that returns a reservation or a message
   thread, **When** its response is audited, **Then** `profile_picture`
   is absent unconditionally, and `email` and `phone_numbers` are
   absent unless the guest-contact-details option is enabled
   (FR-046, FR-047).
6. **Given** the `guest` object is null on a reservation, **When** the
   entity updates, **Then** guest attributes report no value rather
   than raising or becoming unavailable.
7. **Given** any guest attribute, **When** Home Assistant writes state
   to the recorder database, **Then** the attribute is NOT persisted
   (marked unrecorded).

---

### Edge Cases

- **A service call is issued while no config entries are loaded.**
  ServiceValidationError explaining no Hospitable accounts are
  configured.
- **A service call targets a reservation on a different config entry
  than expected.** Multi-entry disambiguation requires
  `config_entry_id` when ambiguous.
- **The `/tasks` endpoint returns an error for one property in a
  multi-property account.** Because the poll fans out to one request
  per property (FR-030), only that property's request fails. Its task
  sensors retain their last-good values rather than being wiped, and
  every other property updates normally. (Spec 001 D-15 failure
  isolation, applied per property exactly as the calendar coordinator
  applies it.)
- **A message send returns HTTP 422.** The error is surfaced as a
  HomeAssistantError with the validation detail from the response.
- **Rate limit hit mid-automation.** The service returns an error; it
  does not retry silently, because silent retries in a user-invoked
  action delay feedback and risk exceeding the budget further.
- **Maintenance task has task_type 5 but service_id 8.** These two
  enum namespaces are NOT interchangeable. Confusing them would
  mislabel maintenance as something else. The mapping must be
  explicit.
- **`GET /tasks` called without `properties[]`.** Returns HTTP 400.
  The integration must ALWAYS include `properties[]` — with exactly
  one property per request under the FR-030 fan-out — and MUST NOT
  include date parameters (they are not required and their interaction
  with the response is not verified).
- **Message thread arrives unpaginated.** The messages endpoint
  `GET /reservations/{uuid}/messages` returns a `{data}` envelope
  with no `meta` and no `links`, and `page`/`per_page` are silently
  ignored, so a long conversation arrives in full in one response.
  No code may assume a small list.
  The observation is bounded: the busiest conversation on the
  reference account holds only 10 messages, so behaviour above that
  volume was not observed. A `meta`/`links` block appearing later
  MUST be tolerated rather than crash, but pagination MUST NOT be
  treated as expected. (CONFIRMED-BY-TEST — see FR-023 and OQ-002)
- **The messages endpoint returns HTTP 429.** Unlike every endpoint
  spec 001 exercised, this one is throttled and advertises its budget
  in response headers. A 429 on a message fetch is a throttle, not an
  outage: the indicator sensor retains its last-good value and the
  reservation update as a whole does not fail. (CONFIRMED-BY-TEST —
  see FR-017 and FR-019)
- **Entity_id vs reservation_uuid input.** Services that accept a
  reservation target must accept EITHER an `entity_id` (reading UUID
  from entity attributes) OR an explicit `reservation_uuid`, and must
  validate that exactly one is supplied.
- **Co-host sender_id for non-Airbnb reservation.** Rejected
  client-side with ServiceValidationError before any API call.
- **`last_message_at` is null on a reservation.** The sensor reports
  no value.
- **Guest data is absent.** The `include=` response key check (spec 001
  FR-075) applies. Guest attributes report no value.

## Requirements *(mandatory)*

### Functional Requirements

#### Write boundary and lifecycle integrity

- **FR-001**: No write request (POST, PUT, PATCH, DELETE) may
  originate from a coordinator refresh, a sensor update, integration
  setup, reload, or unload. Writes occur ONLY in direct response to a
  user-invoked Home Assistant service call. This is NON-NEGOTIABLE.

  What this narrows is spec 001's GLOBAL read-only rule, recorded in
  its `contracts/upstream-requests.md` global-rules table as "No write
  request of any kind is issued". That rule is replaced by the
  lifecycle-scoped boundary above; spec 002's own
  [contracts/upstream-requests.md](contracts/upstream-requests.md)
  states the replacement text.

  It does NOT narrow spec 001 FR-059, which is calendar-modification
  only ("MUST NOT issue any calendar modification request ... under any
  circumstance"). FR-059 survives this spec untouched and absolute; see
  the Out of Scope entry for calendar writes. The two rules coexist:
  the global rule becomes "no write from the polling lifecycle", while
  the calendar-specific rule remains "no calendar write, ever, from
  anywhere".
- **FR-002**: The existing `test_no_writes.py` MUST be preserved in
  narrowed form. It MUST continue to assert that every request
  captured during the polling lifecycle (setup → coordinator refresh →
  options change → reload → unload) is a GET. It MUST NOT be deleted.
- **FR-003**: The API client MUST expose a `_post` method (or
  equivalent restricted method) callable only from service-call
  handlers, never from coordinators. The architectural isolation MUST
  be enforced by code structure (separate module path), not merely by
  convention.
- **FR-004**: Service-call handlers MUST NOT call coordinator refresh
  or trigger any polling side effect. A service call is a one-shot
  operation that returns its result directly.

#### Service registration infrastructure

- **FR-005**: Services MUST be registered from `async_setup_entry`
  using a table-driven pattern, following Hostaway's proven approach.
  Registration MUST be idempotent: if services are already registered
  (from an earlier config entry), registration MUST be skipped.
- **FR-006**: Services MUST be removed when the LAST config entry for
  the domain unloads. While any entry remains loaded, services remain
  registered.
- **FR-007**: All service names, descriptions, and field labels MUST
  appear in both `strings.json` and `translations/en.json` for proper
  i18n support. Service definitions MUST NOT rely solely on
  `services.yaml` for user-facing text.
- **FR-008**: Multi-entry disambiguation MUST follow this pattern:
  optional `config_entry_id` field on every service; zero loaded
  entries → ServiceValidationError; exactly one → auto-select;
  multiple → ServiceValidationError requiring `config_entry_id`.

#### Send message service

- **FR-009**: The integration MUST expose a `send_message` service
  that issues `POST /reservations/{uuid}/messages`. (DOCUMENTED —
  never executed against a live account)
- **FR-010**: The `send_message` service MUST accept: `body` (string,
  required), `images` (list of URI strings, optional, max 3),
  `sender_id` (string, optional — co-host user_id). The service MUST
  also accept a reservation target as either `entity_id` or
  `reservation_uuid` (exactly one required).
- **FR-011**: The service MUST report the result as "accepted for
  delivery" and MUST NOT claim "message sent" or "delivered". HTTP 202
  means the API queued the message; delivery is asynchronous and
  unconfirmed. (DOCUMENTED)
- **FR-011a**: The `send_message` service MUST use
  `SupportsResponse.ONLY`. It returns the acceptance result as
  structured data and fires no event. `ONLY` rather than `OPTIONAL` is
  deliberate: FR-011 requires the caller to be told the message was
  accepted for delivery, and a caller that never reads the response
  has no other way to learn that. This requirement exists so
  `send_message`'s response mode rests on a requirement of its own
  rather than borrowing FR-021, which is scoped to `get_messages`.
  (research.md D-14)
- **FR-012**: If the 202 response body contains a `sent_reference_id`
  or equivalent correlation identifier, the service MUST return it to
  the caller. The exact shape of the 202 response body is UNVERIFIED.
- **FR-013**: The service MUST reject a `sender_id` for non-Airbnb
  reservations with a ServiceValidationError before issuing any API
  call. `sender_id` is only supported for Airbnb reservations.
  (DOCUMENTED)

  Platform resolution is defined as follows, and MUST NOT be left to
  implementer discretion:

  - If `sender_id` is NOT supplied, the reservation's platform is not
    needed and MUST NOT be resolved. No extra request is made.
  - If `sender_id` IS supplied and the reservation is present in the
    reservation coordinator's cache, the platform is read from the
    cached reservation's existing `channel` field, which already holds
    the upstream `platform` value. No extra request is made.
  - If `sender_id` IS supplied and the reservation is NOT cached, the
    service MUST issue exactly ONE direct `GET /reservations/{uuid}`
    to resolve the platform. This is a read from a service-call
    handler, which FR-001 permits.
  - If the platform cannot be resolved for any reason — the lookup
    fails, the reservation is not found, or the value is null — the
    service MUST raise `ServiceValidationError` and MUST NOT issue the
    POST.
  - The check MUST NEVER be silently skipped. Skipping it on an
    unresolved platform would let a `sender_id` reach the API on a
    non-Airbnb reservation, which is exactly what this requirement
    forbids. Unresolved means reject, not proceed.
- **FR-014**: The service MUST validate image count (max 3) locally
  before issuing the API call. (DOCUMENTED)
- **FR-015**: The service MUST handle documented error responses:
  HTTP 400 (bad request) and HTTP 422 (validation error) as
  ServiceValidationError; any other API failure as HomeAssistantError.
  (DOCUMENTED responses: 202, 400, 422)
- **FR-016**: A 403 on the send endpoint MUST be treated as a
  permanent capability limitation (consistent with spec 001 FR-038),
  surfaced as a HomeAssistantError explaining the limitation. It MUST
  NOT trigger reauthentication. (403 is NOT documented for this
  endpoint; this is defensive handling only.)

#### Rate-limit enforcement for messaging

- **FR-017**: The integration MUST respect the messaging rate limits:
  2 messages per minute per reservation, and 50 messages per 5 minutes
  per PAT user (token). The two limits sit at different confidence
  tiers and MUST NOT be conflated:
  - The per-reservation limit of **2 requests per 60 seconds** is
    CONFIRMED-BY-TEST on `GET /reservations/{uuid}/messages`. The
    endpoint returns `x-ratelimit-limit: 2` and
    `x-ratelimit-remaining: <n>` on success, and on HTTP 429 also
    returns `retry-after` (59–60 observed) and `x-ratelimit-reset`
    (unix epoch). The buckets are independent per reservation:
    reservation A burned to `remaining: 0` returned 429 while
    reservation B immediately returned HTTP 200 with a fresh
    `remaining: 1`. The identical 2-per-minute-per-reservation figure
    for the SEND endpoint remains DOCUMENTED only — no POST has ever
    been executed. See OQ-007 for whether reads and writes share one
    bucket.
  - The per-token limit of 50 per 5 minutes is DOCUMENTED only and has
    never been tested. It MUST NOT be described as confirmed.
  This throttling is scoped to the messages endpoint. `/properties`,
  `/reservations`, and `/tasks` were re-checked in the same session
  and expose no `x-ratelimit-*` and no `retry-after` headers, so spec
  001's recorded finding remains correct for the endpoints spec 001
  tested. This is not a spec 001 defect.
  When the messages endpoint returns rate-limit headers, the
  integration MUST feed `x-ratelimit-limit`, `x-ratelimit-remaining`,
  and `x-ratelimit-reset` back into its local accounting rather than
  relying solely on its own count, and MUST tolerate their absence.
  The HTTP 429 body is the Laravel envelope with NO `errors` key
  (`{"status_code": 429, "reason_phrase": "Too Many Attempts."}`), so
  the shared envelope parser MUST tolerate the missing key.
  (CONFIRMED-BY-TEST)
- **FR-018**: Rate-limit accounting MUST key on the TOKEN value, not
  the config entry identifier. Two config entries using the same PAT
  share one budget; entries with different PATs have independent
  budgets. This integration is multi-account, so this distinction
  matters.
- **FR-019**: When the integration's own accounting says a rate limit
  would be exceeded, the service MUST reject the call immediately with
  a ServiceValidationError explaining which limit applies
  (per-reservation or per-token) and approximately when it will reset.
  It MUST NOT silently queue or retry.
  An HTTP 429 returned by the upstream messages endpoint is a
  different case and MUST be handled as a retryable-with-backoff
  condition driven by `retry-after`, not as a hard failure: a throttle
  is not an outage. On the user-invoked send path the caller is still
  told immediately; on the opt-in awaiting-host-reply fetch the
  previous indicator value is retained, the entity is NOT marked
  unavailable, and the reservation update as a whole does not fail.
  (CONFIRMED-BY-TEST for the fetch path; the send path is DOCUMENTED
  only — see OQ-007)

#### Read messages service

- **FR-020**: The integration MUST expose a `get_messages` service
  that issues `GET /reservations/{uuid}/messages` and returns the
  message array. (CONFIRMED-BY-TEST)
- **FR-021**: The service MUST use `SupportsResponse.ONLY`, meaning it
  returns structured data and fires no event.
- **FR-022**: The service MUST accept a reservation target as either
  `entity_id` or `reservation_uuid` (exactly one required).
- **FR-023**: `GET /reservations/{uuid}/messages` is NOT paginated:
  the envelope carries `data` only, with no `meta` and no `links`,
  unlike `/reservations` and `/tasks` which carry all three. The
  service MUST therefore consume the thread in a SINGLE request and
  MUST NOT implement a pagination loop. It MUST NOT send `page` or
  `per_page` to this endpoint: both are silently ignored upstream
  (`per_page=1`, `per_page=2`, `page=1`, `page=2`, and
  `per_page=1&page=2` all returned the identical full set of 10
  items), so sending them would create a false impression that the
  payload is bounded. Because there is no upstream mechanism to bound
  the payload, no code may assume a small list — a very long
  conversation arrives in full.
  **Scope caveat**: the busiest conversation on the reference account
  holds only 10 messages, so behaviour above that volume was NOT
  observed and pagination appearing above some threshold cannot be
  ruled out. The implementation MUST therefore tolerate a `meta` or
  `links` block appearing later rather than crashing, but MUST NOT be
  written as though pagination were expected. (CONFIRMED-BY-TEST —
  OQ-002 is closed to the extent stated here)
- **FR-024**: Message bodies are personal data and MUST NOT be logged
  at any level. The service returns them to the caller but the
  integration itself never writes them to logs or diagnostics.

#### Lookup services

- **FR-025**: The integration MUST expose a `find_reservation` service
  that returns reservation details for a given UUID, using
  `SupportsResponse.ONLY`. Not-found is a return value
  (`{"found": false, "reservation": null}`), not an exception.
- **FR-026**: The integration MUST expose a `get_reservations` service
  that returns reservations for a given property within the configured
  window, using `SupportsResponse.ONLY`.
- **FR-027**: The integration MUST expose a `get_property_info`
  service that returns property details including listings and
  co-hosts, using `SupportsResponse.ONLY`.
- **FR-028**: All lookup services MUST handle not-found as a return
  value (`{"found": false, ...}`), not as an exception. API failures
  (network, auth, server errors) MUST raise HomeAssistantError.
- **FR-029**: All lookup services MUST accept the optional
  `config_entry_id` field for multi-entry disambiguation (FR-008).

#### Task sensors

- **FR-030**: The integration MUST poll `GET /tasks` with the
  `properties[]` parameter and MUST NOT include date parameters (the
  default request omits them). Hospitable then applies its own roughly
  14-day forward window, measured on 2026-08-12 as returning tasks
  through 2026-08-24. (CONFIRMED-BY-TEST: `properties[]` required;
  bare call or dates-only → 400)
  The poll MUST FAN OUT: exactly ONE request per selected property,
  each carrying that single property in `properties[]`, rather than one
  batched request naming every selected property. Fan-out is what makes
  the FR-034 per-property failure isolation achievable at all — a
  batched request has one outcome for every property, so a single
  failure would take down every task sensor at once. It matches the
  per-property calendar precedent and its last-good retention from spec
  001. The cost is trivial: 13 requests per poll at reference scale on
  an endpoint that publishes no rate limit and exposes no
  `x-ratelimit-*` headers.
- **FR-031**: The integration MUST paginate `/tasks` from day one.
  A naive single-page fetch silently loses tasks. (CONFIRMED-BY-TEST:
  `per_page=1` on a three-task property returned `last_page: 3`, and
  `page=2` returned the second task.)
  Pagination MUST be followed PER PROPERTY. Each property's response
  carries its own `meta.last_page`, and the integration MUST follow
  each independently rather than assuming a shared page count.
- **FR-032**: The integration MUST expose per-property task sensors:
  at minimum a next-task sensor (type, assignment status, progress,
  start/end datetimes, timezone, duration) and a task-count sensor.
- **FR-033**: Task type mapping MUST explicitly distinguish task_type
  IDs from service_id values. These are two different enums:
  Maintenance is task_type 5 but service_id 8. Conflating them would
  silently mislabel maintenance tasks. (CONFIRMED-BY-TEST: meta
  vocabularies show the divergence)
- **FR-034**: The task coordinator MUST use a separate polling cadence
  (configurable, default and floor TBD in planning) and MUST implement
  failure isolation per spec 001 D-15: a failure for one property MUST
  NOT prevent other properties from updating. The FR-030 fan-out is
  what makes this implementable — one request per property means one
  failure per property. A failed property MUST retain its last-good
  task data rather than have it cleared.

  The citation is deliberately qualified as *spec 001* D-15. Spec 002
  has its own D-15, an unrelated decision about service response
  modes, so an unqualified reference resolves to the wrong artifact.
- **FR-035**: Task sensor data MUST include the assignment status and
  progress status vocabularies from the `/tasks` meta response.
  (CONFIRMED-BY-TEST: assignment_statuses and progress_statuses
  enumerated in meta)

#### Message presence sensors

- **FR-036**: The integration MUST expose a `last_message_at` sensor
  per property, derived from the `last_message_at` field on the
  property's operationally relevant reservation. This field is already
  present on the reservation payload and requires no additional API
  call. (CONFIRMED-BY-TEST: `last_message_at` is one of 21 top-level
  reservation keys)
- **FR-037**: The integration MUST expose an awaiting-host-reply
  indicator sensor per property, gated behind an opt-in configuration
  option that defaults to OFF. When enabled, the indicator is derived
  from `GET /reservations/{uuid}/messages`: if the most recent message
  in the thread has `sender_type` indicating a guest (with no
  subsequent host message), the sensor reports true; otherwise false.
  This is NOT a read receipt and MUST NOT be described as "unread" —
  it cannot detect messages read in the Hospitable UI, the mobile app,
  or any other client. The limitation MUST be stated in the sensor's
  description and documentation. (CONFIRMED-BY-TEST: `sender_type` is
  present on message objects from the messages endpoint)
- **FR-038**: `last_message_at` (FR-036) MUST derive from existing
  polled reservation data and MUST NOT issue additional API calls.
  The awaiting-host-reply indicator (FR-037), when its option is
  disabled (the default), MUST NOT issue any additional API calls. When
  enabled, the indicator MUST issue at most one
  `GET /reservations/{uuid}/messages` call per property per poll cycle,
  bounded to the operationally relevant reservation only. On the
  reference account this adds approximately 13 calls per cycle for 13
  properties. (CONFIRMED-BY-TEST: 29 reservations in a 30-day window,
  22 accepted, across 13 properties)

#### Configuration options for spec 002

- **FR-038a**: The options flow MUST expose an awaiting-host-reply
  toggle that defaults to OFF. When enabled, the integration polls
  `GET /reservations/{uuid}/messages` for the operationally relevant
  reservation of each property during each reservation poll cycle.
  When disabled, no message-fetch calls are made and no
  awaiting-host-reply sensor is created. The option MUST appear in
  `strings.json` and `translations/en.json` with a description that
  explains the additional API cost.
  The EFFECTIVE per-reservation message-fetch interval MUST be at
  least 60 seconds, enforced independently of the configured
  reservation poll interval (whose floor is 1 minute). This floor is a
  DELIBERATELY CONSERVATIVE CHOICE, not a derivation: the confirmed
  upstream limit of 2 requests per 60 seconds per reservation would
  mathematically permit a 30-second interval. The second slot is left
  deliberately unused so that a user-initiated send is not starved if
  reads and writes turn out to share one bucket (OQ-007). No artifact
  may describe the 60-second floor as "derived from" or "required by"
  the rate limit.
- **FR-038b**: The options flow MUST expose a guest-contact-details
  toggle that defaults to OFF. When enabled, the reservation status
  entity additionally exposes `guest_email` and `guest_phone_numbers`
  as attributes. When disabled, those attributes are not created.
  The option MUST appear in `strings.json` and `translations/en.json`
  with a description that explains the privacy implication of
  exposing contact details as entity attributes.

#### Guest identity on reservation entities

- **FR-039**: The reservation polling request MUST include
  `include=guest` (singular) to obtain guest identity data. The
  `guest` object is NOT present on the base reservation payload; it
  appears only when this include is specified. Spec 001 recorded
  `include=guests` (plural) as a no-op — that is an instance of the
  silent-ignore behaviour class spec 001 FR-075 enumerates (an
  unrecognised parameter name returns HTTP 200 with no added keys).
  The correct parameter is singular.
  This include adds no additional API calls; it is a query parameter
  on a request the integration already makes. (CONFIRMED-BY-TEST:
  `include=guest` adds exactly one new top-level key `guest`, taking
  the reservation payload from 21 keys to 22. `include=guests` plural
  and `include=customer` remain no-ops at 21 keys.)
- **FR-039a**: The reservation status entity MUST expose these guest
  attributes BY DEFAULT when `include=guest` returns a non-null
  `guest` object: `guest_first_name`, `guest_last_name`,
  `guest_location`, `guest_language`. (CONFIRMED-BY-TEST: measured
  across 29 upcoming reservations — first_name 29/29, last_name
  28/29, location 19/29, language observed on all with 3 distinct
  values.)
- **FR-039b**: The reservation status entity MUST tolerate a missing
  `last_name` — it was genuinely absent on 1 of 29 live reservations.
  Display-name derivation (e.g., concatenating first and last) MUST
  handle this gracefully, showing only first_name when last_name is
  null. (CONFIRMED-BY-TEST: 28/29)
- **FR-039c**: `guest_email` and `guest_phone_numbers` MUST be
  exposed AS ENTITY ATTRIBUTES ONLY when the guest-contact-details
  option (FR-038b) is enabled. The equivalent control for the service
  response surface is FR-047; this requirement does not reach that
  surface (FR-046). `email` is usually absent (4/29 populated) and MUST NOT be
  assumed present. `phone_numbers` is an array (22/29 populated).
  (CONFIRMED-BY-TEST)
- **FR-039d**: `profile_picture` MUST NOT be exposed as an entity
  attribute. It is additionally barred from service responses by
  FR-047 and from logs and diagnostics by FR-041 and FR-042; it has no
  permitted exposure surface anywhere (FR-046).
- **FR-039e**: ALL guest attributes (both default and opt-in) MUST be
  marked as unrecorded attributes so they live in entity state memory
  only and are NEVER written to the recorder database or captured in
  backups. This follows the `_unrecorded_attributes` precedent
  established by the availability sensor's `forward_window` attribute
  in the existing implementation.
- **FR-040**: The `guest` object response MUST be validated: if
  `include=guest` is requested and the response contains the `guest`
  key, its value may be an object or null. A null `guest` means no
  guest data is available for that reservation; guest attributes MUST
  report no value rather than raising.
- **FR-041**: Guest names, email addresses, phone numbers, location,
  language, and message content MUST NEVER appear in logs at any
  level. This extends spec 001 FR-062 and FR-073 to all guest fields.
- **FR-042**: ALL guest fields (including those behind the opt-in)
  MUST be redacted from diagnostics output. Diagnostics MUST show the
  presence of guest data (e.g., `"guest_first_name": "**REDACTED**"`)
  rather than omitting the field entirely, so that troubleshooting can
  distinguish "field absent from API" from "field present but
  redacted."
- **FR-043**: Exposing guest PII as entity attributes is acceptable
  because Home Assistant entity state is local to the instance and is
  not transmitted externally by the integration. The spec 001 FR-073
  redaction requirement applies to logs and diagnostics output, not to
  entity state visible only within the user's own Home Assistant.

#### Service input patterns

- **FR-044**: Services that target a reservation MUST accept EITHER an
  `entity_id` (from which the reservation UUID is read from entity
  attributes) OR an explicit `reservation_uuid`. Exactly one MUST be
  supplied; providing both or neither is a ServiceValidationError.
- **FR-045**: `ServiceValidationError` MUST be used for
  user-correctable problems (bad input, rate limit, disambiguation).
  `HomeAssistantError` MUST be used for API failures (network, server
  error, permanent capability limitation).

#### Service response privacy (exposure surface parity)

- **FR-046**: **A privacy control scoped to one surface does not
  protect another surface.** Every requirement in this specification
  that restricts personal data MUST name the surface it governs, and
  each surface MUST be given its own explicit control. The exposure
  surfaces recognised by this specification are: entity attributes,
  the recorder database, logs, diagnostics output, exception text, and
  **service call responses**. Service responses are user-visible
  through automation traces, template rendering, script variables, and
  debug logging, and are therefore an exposure surface of equal
  standing to entity attributes — not a private internal channel.
  A future surface added without its own control MUST be treated as
  unprotected until one is written.
- **FR-047**: Guest data returned in a SERVICE CALL RESPONSE MUST
  follow the same policy as guest data exposed as an entity attribute:
  - `profile_picture` MUST NEVER appear in any service response, under
    any option, ever. It has no permitted exposure surface at all.
  - `email` and `phone_numbers` MUST be omitted from service responses
    UNLESS the guest-contact-details option (FR-038b) is enabled for
    the config entry serving the call.
  - `first_name`, `last_name`, `location`, and `language` MAY be
    returned.
  - Any guest key not enumerated here MUST be omitted rather than
    passed through, so that a new upstream key cannot leak by default.
  This governs `find_reservation` and `get_reservations`, which return
  reservation payloads fetched with `include=guest`, and any future
  service that returns a reservation payload.
- **FR-047a**: The `sender` object on a message MUST NOT be returned
  raw by `get_messages`. It is an opaque upstream structure that may
  carry guest identity and contact fields, so it is subject to FR-047
  on the same terms. Only `sender_type` and `sender_role` — which are
  role discriminators, not identity — may be returned. Message `body`
  and `attachments` remain returnable, since retrieving them is the
  service's purpose (FR-024), but MUST NOT be logged.
- **FR-048**: The FR-047 and FR-047a filtering MUST be applied inside
  ONE shared response-builder chokepoint that every service response
  passes through. It MUST NOT be implemented per handler, and it MUST
  NOT rely on the caller to filter. A service added later that
  serialises a guest or sender object MUST inherit the filter by
  construction rather than by remembering to call it.

### Key Entities

- **Task**: A scheduled operational activity for a property (cleaning,
  check-in, check-out, concierge, maintenance). Identified by a
  UUID string. Carries a task_type (1–5), a service_id
  (1–8, NOT interchangeable with task_type), nested task assignment
  status, nullable progress_status, start/end datetimes with timezone,
  duration, reservation association, and nested property association.
- **Message**: A single message in a reservation's conversation
  thread. Identified by a numeric ID. Carries body, sender_type,
  sender_role, sender object, created_at, content_type, attachments,
  and conversation_id.
- **Guest**: The person on a reservation. Exposed as attributes on the
  reservation entity (name, optionally contact details). Personal data
  subject to strict logging/diagnostics redaction.

## Success Criteria *(mandatory)*

### Measurable Outcomes

Each criterion names the task IDs that evidence it. Where a criterion
cannot be evidenced by the automated suite, it says so explicitly
rather than implying a test exists.

- **SC-001**: A user can send a guest message via service call and
  receive an "accepted for delivery" response. (T149, T157)

  **Latency is NOT automatically verified.** The automated suite runs
  against `respx`, which serves responses from memory, so any wall
  clock bound it appears to measure is a property of the mock rather
  than of the integration. A "within 5 seconds" figure asserted there
  would be theatre. Real-world latency is a MANUAL quickstart check
  against a live account and is not claimed as tested.
- **SC-002**: The polling lifecycle test (`test_no_writes.py`)
  continues to pass with zero non-GET requests across setup, refresh,
  options change, reload, and unload — proving that writes remain
  confined to explicit service calls. (T148, T156, T161)
- **SC-003**: An audit of all logs at every level and a full
  diagnostics download finds zero occurrences of guest first names,
  last names, email addresses, phone numbers, locations, languages,
  profile pictures, or message bodies unredacted. (T153, T157)
- **SC-003a**: An audit of the response payload of every registered
  service finds zero occurrences of `profile_picture` and zero
  occurrences of a raw message `sender` object, under every option
  combination; and finds `email` and `phone_numbers` absent when the
  guest-contact-details option is OFF and present when it is ON.
  (T072a to T072e, T153a)
- **SC-004**: All `/tasks` pages are fetched without data loss — the
  task count reported by sensors matches the total across all pages
  returned by the API, for every property independently, and one
  property's failed request leaves the other properties' counts intact.
  (T112, T112a, T117a, T119, T151)
- **SC-005**: Rate-limit enforcement prevents message sends from
  exceeding the documented limits (2/min/reservation, 50/5min/token)
  in 100% of test scenarios. (T155, T155a, T158)

  Note the tiers differ and MUST NOT be merged: 2/min/reservation on
  reads is CONFIRMED-BY-TEST, while 50/5min/token is DOCUMENTED-ONLY
  and has never been observed. The enforcement is tested; the upstream
  existence of the second limit is not.
- **SC-006**: Multi-entry disambiguation correctly auto-selects when
  one entry exists and correctly rejects with an explanatory error when
  multiple entries exist and no `config_entry_id` is provided. (T154)
- **SC-007**: Lookup services return structured data and never fire an
  event or produce a side effect — no coordinator refresh, no state
  write, no bus event. (T150, T150a)

  **Latency is NOT automatically verified**, for the same reason as
  SC-001: under `respx` the response is already in memory. The 10
  second figure previously stated here is removed rather than left
  sitting next to tested claims where it would read as one. Live
  latency is a manual check.
- **SC-008**: Task sensors correctly label Maintenance tasks as
  Maintenance (not as task_type-5's misleading service_id) in 100% of
  cases. (T114, T124, T151)
- **SC-009**: `guest_first_name` and `guest_last_name` are visible as
  reservation entity attributes when the API returns a non-null
  `guest` object, and absent (not errored) when the guest object is
  null or `last_name` is missing. All guest attributes are unrecorded
  and never appear in the recorder database. (T152, T153)

## Assumptions

### About the platform

- `POST /reservations/{uuid}/messages` returns HTTP 202 on success.
  We have NEVER executed a POST against the live account. Everything
  about send behaviour is DOCUMENTED, never CONFIRMED-BY-TEST.
- The 202 response body shape (whether it returns `sent_reference_id`)
  is UNVERIFIED.
- Whether `GET /reservations/{uuid}/messages` paginates is settled for
  the observed range: it does not. The envelope is `{data}` only, and
  `page`/`per_page` are silently ignored. This was measured against a
  busiest thread of 10 messages, so behaviour above that volume is
  unobserved. (CONFIRMED-BY-TEST, bounded — see FR-023, OQ-002)
- `GET /reservations/{uuid}/messages` is rate limited at 2 requests
  per 60 seconds per reservation, with independent per-reservation
  buckets, and advertises `x-ratelimit-limit`,
  `x-ratelimit-remaining`, `x-ratelimit-reset`, and `retry-after`.
  (CONFIRMED-BY-TEST)
- No other endpoint this integration calls is throttled or exposes
  rate-limit headers. `/properties`, `/reservations`, and `/tasks`
  expose none. (CONFIRMED-BY-TEST)
- Whether the send endpoint's DOCUMENTED 2-per-minute-per-reservation
  limit is the SAME bucket as the confirmed GET limit is UNVERIFIED
  and cannot be tested without a real send. (See OQ-007)
- Whether messaging requires a particular plan tier or scope beyond
  what the owner's current token provides is UNVERIFIED.
- The `/tasks` endpoint is reachable with a Personal Access Token
  that has read permissions. (CONFIRMED-BY-TEST: 200 response
  obtained)
- `GET /tasks` requires `properties[]` and does NOT require dates.
  (CONFIRMED-BY-TEST)
- `/tasks` publishes no rate limit and exposes no `x-ratelimit-*` or
  `retry-after` headers, so fanning the poll out to one request per
  property is affordable. (CONFIRMED-BY-TEST)
- Task pagination is real and mandatory: `per_page=1` on a
  three-task property produced `last_page: 3`, and `page=2` returned
  the second task. (CONFIRMED-BY-TEST) Under the FR-030 per-property
  fan-out, each property's own `meta.last_page` must be followed.
- The task_type/service_id enum divergence (Maintenance = task_type
  5 but service_id 8) is stable API behaviour, not a bug.
  (CONFIRMED-BY-TEST)
- `last_message_at` is present on the base reservation payload and
  requires no additional include or API call. (CONFIRMED-BY-TEST)
- The `conversation_id` field on reservations is stable and usable as
  a thread key. (CONFIRMED-BY-TEST)
- Co-host user_id is discoverable via
  `GET /properties?include=listings` → `listings[].co_hosts[].user_id`.
  (CONFIRMED-BY-TEST: 8 of 13 properties have co_hosts)
- Platform census includes platforms not previously catalogued: `gvr`
  (probable Google Vacation Rentals) and `manual`.
  (CONFIRMED-BY-TEST)

### About this integration

- The existing service-package structure (`custom_components/
  hospitable/services/`) is the correct location for service-call
  handlers, distinct from the coordinator/sensor polling path.
- `SupportsResponse.ONLY` is the correct response mode for lookup
  services (return data, no event fired).
- Rate-limit accounting must be per-token because the integration is
  multi-account and two config entries can share a PAT.
- The Hostaway reference integration's table-driven service
  registration pattern is the proven approach to adopt.
- Guest PII in entity attributes is acceptable because entity state is
  instance-local. PII in logs/diagnostics is not.

## Open Questions

- **OQ-001 — Send response body shape (UNVERIFIED).** The exact JSON
  shape of the HTTP 202 response from
  `POST /reservations/{uuid}/messages` has never been observed. If it
  contains `sent_reference_id`, that is the correlation handle for
  delivery confirmation. This must be discovered during
  implementation, ideally via a controlled test send to a test
  reservation.
- **OQ-002 — Message pagination (CLOSED for the observed range,
  CONFIRMED-BY-TEST).** A read-only probe on 2026-08-12 established
  that `GET /reservations/{uuid}/messages` returns a `{data}` envelope
  with no `meta` and no `links`, unlike `/reservations` and `/tasks`
  which carry all three, and that `per_page=1`, `per_page=2`,
  `page=1`, `page=2`, and `per_page=1&page=2` ALL returned the
  identical full set of 10 items. **Answer:** the endpoint is not
  paginated and both parameters are silently ignored — a further
  instance of the silent-ignore behaviour class (spec 001 records five
  distinct instances; this is a new one, and it is endpoint-scoped:
  `page`/`per_page` remain honoured on `/reservations` and `/tasks`).
  The thread is consumed in one request and no pagination loop is
  written (FR-023).
  **Scope caveat, stated honestly**: the busiest conversation on the
  reference account holds only 10 messages, so behaviour above that
  volume was NOT observed. Pagination may appear above some threshold.
  The code must tolerate a `meta`/`links` block appearing later rather
  than crash, but must not treat pagination as expected.
- **OQ-003 — Awaiting-host-reply derivation (RESOLVED).** The base
  reservation payload has no read-state field; `sender_type` exists
  only on message objects from `GET /reservations/{uuid}/messages`.
  **Answer:** the indicator is reframed as "awaiting host reply"
  (not "unread"), derived from the most recent message's
  `sender_type`, gated behind an opt-in option defaulting to OFF, and
  permitted to issue one message-fetch call per property per cycle
  when enabled. This is explicitly not a read receipt.
- **OQ-004 — Task polling cadence.** The appropriate default and floor
  for task polling is not yet determined. Tasks change less frequently
  than reservations but more frequently than properties. A default of
  15–30 minutes is reasonable but must be validated in planning.
- **OQ-005 — Messaging scope requirement (UNVERIFIED).** The exact
  scope name required for sending messages is unknown. The owner's
  token was created with read+write but the vendor does not enumerate
  granted scopes. If a scope is required that the current token lacks,
  messaging will fail at runtime with a 403.
- **OQ-006 — Guest include on reservations (RESOLVED).** Spec 001
  recorded `include=guests` (plural) as a no-op. That was correct but
  misleading: it is one of the silent-ignore behaviours spec 001 FR-075
  enumerates (an unrecognised parameter name returns 200 and is
  ignored), not a statement that no guest data exists. **Answer:** the correct
  parameter is `include=guest` (singular). Verified live:
  `include=guest` adds exactly one new top-level key `guest`, taking
  the payload from 21 keys to 22, on both the collection and single-
  reservation endpoints. `include=guests` (plural) and
  `include=customer` remain no-ops at 21 keys. Guest object keys:
  `id` (string), `first_name` (string), `last_name` (string), `email`
  (null in most cases), `phone_numbers` (array), `location` (string),
  `profile_picture` (string URL), `language` (string). Measured
  population across 29 upcoming reservations: first_name 29/29,
  last_name 28/29, profile_picture 27/29, phone_numbers 22/29,
  location 19/29, email 4/29, 3 distinct language values. All 29 had
  a non-null guest object. This include adds zero extra API calls —
  it is a query parameter on the existing reservation poll.
  (CONFIRMED-BY-TEST)
- **OQ-007 — Shared read/write rate-limit bucket (UNVERIFIED, and
  UNCLOSABLE without a real send).** The CONFIRMED GET limit on
  `GET /reservations/{uuid}/messages` is 2 requests per 60 seconds per
  reservation. The DOCUMENTED send limit on
  `POST /reservations/{uuid}/messages` is also 2 per minute per
  reservation. The identical shape makes it plausible that reads and
  writes share ONE per-reservation bucket, which would mean an
  awaiting-host-reply poll could consume budget a user needs for an
  actual send. It is equally plausible that they are separate buckets.
  **This project asserts neither.** The question cannot be answered
  without issuing a real POST to a real guest, which is absolutely
  prohibited, so it stays open.
  **Required defensive design in both directions**: the send path MUST
  treat an upstream 429 as a retryable-with-backoff condition driven
  by `retry-after` rather than a hard failure (FR-019), and the
  polling path MUST NOT starve the send path — hence the deliberately
  conservative 60-second per-reservation message-fetch floor that
  leaves one of the two slots unused (FR-038a).

## Out of Scope

- **Webhooks for real-time message delivery confirmation.** Deferred
  to the webhooks specification.
- **Automated/scheduled message sending.** This spec provides the
  service call; automation authors wire it into their own triggers.
- **Message templates.** `/messages/templates` returned 404.
  (CONFIRMED-BY-TEST: endpoint does not exist)
- **Calendar writes.** Remain absolutely prohibited. Spec 001 FR-059
  is calendar-modification-specific and is NOT narrowed by FR-001,
  which narrows only spec 001's separate global read-only rule. No
  service introduced here may issue a calendar write, and no future
  service may either without amending FR-059 itself.
- **Door codes and enrichment.** Remain out of scope (vendor-gated).
- **OAuth.** Deferred as in spec 001.
- **Review reading/responding.** Out of scope.
- **Inquiry/pre-booking threads.** Out of scope.
- **Team/teammate management.** Out of scope.
- **Direct webhook registration via API.** No such endpoint exists.
- **Image upload.** The `images` field accepts URIs; the integration
  does not host or upload images itself.
- **Delivery confirmation tracking.** Beyond reporting the 202
  correlation ID (if available), the integration does not track
  whether messages were ultimately delivered.
