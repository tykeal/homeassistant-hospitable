<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Hospitable for Home Assistant

Hospitable is a Home Assistant custom integration for the Hospitable
Public API v2. It lets you select properties, then creates sensor
entities for reservation state, property details, tasks, messaging
state, and aggregate calendar availability. It also exposes five
services for looking up data on demand and for sending a guest message.

**Polling is strictly read-only.** The only request this integration
ever makes that is not a `GET` is the `POST` behind the
`hospitable.send_message` service, and that happens only when you
explicitly call it. No automatic behaviour writes anything to your
Hospitable account.

The integration uses Hospitable Personal Access Tokens. Public API
access requires a paid Hospitable plan; Essentials plans are excluded.
The token needs read access to user, property, reservation, and calendar
data. Sending a message additionally requires the token to carry a
message-send scope; see [Evidence tiers](#evidence-tiers) for what is
and is not known about that.

## Installation

### HACS custom repository

1. In Home Assistant, open HACS.
2. Go to **Integrations**.
3. Open the menu, choose **Custom repositories**, and add:
   `https://github.com/tykeal/homeassistant-hospitable`
4. Select category **Integration**.
5. Install **Hospitable** and restart Home Assistant.
6. Add the integration from **Settings > Devices & services**.

### Manual installation

1. Copy `custom_components/hospitable/` from this repository into your
   Home Assistant `custom_components/` directory.
2. Restart Home Assistant.
3. Add the integration from **Settings > Devices & services**.

## Configuration

Setup asks for a Hospitable Personal Access Token, fetches the account's
properties, and requires at least one property selection. If the account
has no properties, setup aborts instead of creating an empty entry.

Options are available after setup:

| Option key | UI label | Default | Floor or range | Notes |
| --- | --- | --- | --- | --- |
| `selected_properties` | Properties | `[]` | At least one | Selected property ids are polled. Deselected properties keep their entity ids and history, but stop polling and become unavailable. |
| `reservation_interval_minutes` | Reservation polling interval (minutes) | `5` | Minimum `1` | Drives reservation status, next arrival, next departure, and upcoming reservation data. |
| `property_interval_minutes` | Property polling interval (minutes) | `60` | Minimum `15` | Drives property details and calendar availability. |
| `lookback_days` | Lookback days | `90` | `7` to `365` | Shortening the lookback can hide long in-progress stays and make an occupied property look like it has no reservation. |
| `lookahead_days` | Lookahead days | `90` | `1` to `730` | Widening the window can increase reservation pages per poll. |
| `guest_contact_details` | Include guest contact details | `false` | On or off | **Privacy opt-in.** Off by default. When on, the reservation status entity gains `guest_email` and `guest_phone_numbers`, and the lookup services return `email` and `phone_numbers` in their responses. Anyone who can read a dashboard or write a template on this Home Assistant instance can then read them. Guest first name, last name, location and language are always exposed; guest attributes are never written to the recorder database. |
| `awaiting_host_reply` | Track awaiting host reply | `false` | On or off | **API cost opt-in.** Off by default. When on, each reservation poll makes one extra request per property to read that property's message thread; a 13-property account adds roughly 13 requests per cycle. See [Rate limits](#rate-limits) — this consumes per-reservation budget that sending a message may also need. |
| `task_interval_minutes` | Task polling interval (minutes) | `15` | Minimum `5` | Drives the next-task and task-count sensors. Costs one request per selected property per poll, so the cost scales with how many properties you selected. |
| `task_window_days` | Task window (days) | `14` | `1` to `730` | How many days ahead tasks are fetched, counting from today. Tasks are never fetched backwards. Hospitable rejects a window ending more than three years ahead. |
| `timezone_overrides` | Property timezone overrides | `{}` | IANA timezone names | Stored as a mapping by property id. Blank submitted values remove an override. |

## Entities

Each selected or previously selected property has one Home Assistant
device. Entity unique ids derive from the Hospitable account namespace,
the property id, and the entity key, not from the display name.

| Entity | Key | Classification | State | Main attributes |
| --- | --- | --- | --- | --- |
| Reservation status | `reservation_status` | Enum | `no_reservation`, `awaiting_checkin`, `occupied`, `checked_out`, `pending_request`, `checkpoint`, `cancelled`, `not_accepted`, `unknown` | `reservation_id`, `arrival_date`, `departure_date`, `nights`, `scheduled_checkin`, `scheduled_checkout`, guest counts, `booking_channel`, `channel_confirmation`, `booking_date`, `stay_type`, `status_sub_category`, `upcoming_reservations` |
| Next arrival | `next_arrival` | Timestamp | Soonest future active check-in instant, or no value | None |
| Next departure | `next_departure` | Timestamp | Soonest future active check-out instant, or no value | None |
| Upcoming reservations | `upcoming_reservations` | Measurement state class | Count of forthcoming reservations | None |
| Property info | `property_info` | Diagnostic entity category | Current property display name, or no value | `address`, `checkin_time`, `checkout_time`, `max_guests`, `effective_timezone`, `timezone_source`, `listings`, `listings_available` |
| Availability | `availability` | Enum | `available`, `booked`, `unknown` | `nightly_rate`, `currency`, `min_stay`, `closed_for_checkin`, `closed_for_checkout`, `forward_window` |
| Next task | `next_task` | Timestamp | Start instant of the soonest task in the window, or no value | `task_id`, `task_type`, `service_type`, `service_id`, `start_date`, `end_date`, `progress_status`, `assignment_status`, `assignment_updated_at` |
| Task count | `task_count` | Measurement state class | Number of tasks in the configured window | `pending_count`, `in_progress_count`, `completed_count` |
| Last message | `last_message_at` | Timestamp | Instant of the most recent message in the thread, or no value | `last_guest_message_at` |
| Awaiting host reply | `awaiting_host_reply` | Enum | `on` (guest wrote last), `off` (host wrote last) | Created only when the `awaiting_host_reply` option is on |

Message bodies are never stored as an entity attribute and are never
logged. The awaiting-host-reply indicator reports only *who wrote last*.
It is **not** a read receipt: the Hospitable API publishes no read
state, so it cannot tell you whether anyone has already seen a message
in the Hospitable web UI or mobile app.

Availability reads Hospitable's aggregate property calendar. It never
uses Home Assistant's `unavailable` state to mean a booked night; that
state is reserved for integration data that cannot currently be reached.

## Request economy

The integration has exactly three polling coordinators:

- properties coordinator: fetches `/properties` pages;
- reservations coordinator: fetches `/reservations` pages for selected
  property ids;
- calendar coordinator: fetches one `/properties/{property_id}/calendar`
  response per selected property.

Sensor entities read shared coordinator data and issue zero upstream
requests of their own.

At defaults, the request budget is:

```text
property_polls_per_day = floor(1440 / 60) = 24
calendar_polls_per_day = 24 * selected_property_count
reservation_polls_per_day = floor(1440 / 5) * batches * pages
batches = ceil(selected_property_count / 50)
pages = max(1, ceil(last_observed_reservation_count / 100))
```

For SC-004's example of ten selected properties and no more than 500
reservations in the window, the actual code gives this formula:

| Component | Arithmetic | Requests/day |
| --- | --- | --- |
| Properties | `24 * 1` page, assuming at most 100 account properties | 24 |
| Calendar | `24 * selected_property_count` | 240 for 10 selected properties |
| Reservations | `288 * 1` batch `* 5` pages | 1,440 |
| **Total** | `24 + 240 + 1,440` | **1,704** |

That matches the task text and is below SC-004's 2,000 requests/day
ceiling for the ten-property scenario. The general formula is:

```text
daily_requests =
  floor(1440 / property_interval_minutes) * property_pages
  + floor(1440 / property_interval_minutes) * selected_property_count
  + floor(1440 / reservation_interval_minutes) * reservation_batches
    * reservation_pages
```

The property endpoint is paginated, so accounts with more than 100
total properties add another property-list request per property poll for
each extra page. Calendar traffic scales directly with the number of
selected properties. Reservation traffic scales with the selected
property batches and the number of reservation pages in the configured
window.

A live sequential refresh measured on 2026-08-11 against a 13-property
account took 15.2 seconds total: properties 0.56 seconds, reservations
0.77 seconds, and 13 calendar fetches 13.9 seconds. That is a point-in-
time measurement, not a guarantee. It is below SC-003's 30-second
threshold even without concurrency; the integration fetches calendars
concurrently.

## Services

Five services are registered. All five return a response, so every call
needs `response_variable` in an automation. All five accept an optional
`config_entry_id`; it is required only when more than one Hospitable
account is configured, and is auto-selected when exactly one is.

**Not-found is a return value, not an error.** Every lookup returns
`found: false` rather than raising, so an automation can branch on it
without a `try`/`except`. Genuine failures still raise.

### `hospitable.send_message`

Submits a message to a reservation's guest thread. This is the only
service that writes.

**It returns acceptance, not delivery confirmation.** Hospitable
answers with HTTP 202, which means the message was *accepted for
asynchronous delivery*. It confirms that Hospitable took
responsibility for the message, and nothing beyond that: not that the
guest's channel received it, and not that the guest read it. The
integration has no way to observe either, so it never claims them.

| Field | Required | Notes |
| --- | --- | --- |
| `body` | Yes | The message text. Transmitted exactly as written. |
| `entity_id` | One of | A Hospitable entity identifying the reservation. |
| `reservation_uuid` | One of | The reservation UUID. Give this or `entity_id`, not both. |
| `images` | No | Up to three image URLs. |
| `sender_id` | No | Co-host `user_id` to send on behalf of. **Airbnb only** — supplying it for any other platform is rejected before any request is made. Discover the value with `get_property_info`. |
| `config_entry_id` | No | Account to use. |

### `hospitable.get_messages`

Returns the message thread for a reservation. Takes `entity_id` or
`reservation_uuid`, plus optional `config_entry_id`.

The Hospitable messages endpoint silently ignores `page` and `per_page`,
so the whole thread comes back in one response. Message bodies are
returned to the caller but are never logged and never stored as entity
attributes.

### `hospitable.find_reservation`

Returns one reservation's detail. Takes `entity_id` or
`reservation_uuid`, plus optional `config_entry_id`.

### `hospitable.get_reservations`

Returns the reservations for one property. **Requires `property_id`**,
because Hospitable rejects a reservations request without a property
filter (see [OQ-004](#known-upstream-limitation-oq-004)).

### `hospitable.get_property_info`

Returns one property's raw detail including `listings` and their
`co_hosts`. **Requires `property_id`.** This is where you find a
co-host `user_id` for `send_message`'s `sender_id`.

Note that co-host entries may include that co-host's own contact
details. Those are third-party details belonging to your team rather
than to a guest, and the `guest_contact_details` option does not govern
them.

### `hospitable.list_properties`

Returns every known property for the account with curated metadata
including listing co-host identifiers. Served entirely from the
coordinator cache — no additional API request is made. Use this to
discover the `property_id` values that `get_reservations` and
`get_property_info` require.

### Worked example

```yaml
automation:
  - alias: Greet the guest once they have checked in
    triggers:
      - trigger: state
        entity_id: sensor.example_beach_house_reservation_status
        to: occupied
    actions:
      # send_message accepts the entity directly, so no lookup is
      # needed just to address the message. find_reservation is used
      # here only to confirm there really is a reservation to answer,
      # and to show that not-found is a value rather than an error.
      - action: hospitable.find_reservation
        data:
          entity_id: sensor.example_beach_house_reservation_status
        response_variable: reservation
      - condition: template
        value_template: "{{ reservation.found }}"
      - action: hospitable.send_message
        data:
          entity_id: sensor.example_beach_house_reservation_status
          body: >-
            Welcome! The wifi password is on the fridge. Message us here
            if you need anything.
        response_variable: outcome
      # outcome.accepted is TRUE when Hospitable accepted the message
      # for delivery. It does NOT mean the guest has received it.
      - action: persistent_notification.create
        data:
          message: "Welcome message accepted: {{ outcome.accepted }}"
```

## Rate limits

Two limits apply. **They have different evidence tiers and must not be
treated as equally certain.**

| Limit | Scope | Applies to | Evidence tier |
| --- | --- | --- | --- |
| 2 requests per 60 seconds | Per **reservation** | Reading a message thread; documented as also applying to sending | **CONFIRMED-BY-TEST** |
| 50 requests per 5 minutes | Per **token** | Message operations | **DOCUMENTED-ONLY** |

The per-reservation limit was confirmed by a read-only probe on
2026-08-12: exhausting one reservation into an HTTP 429 and immediately
requesting a different reservation returned HTTP 200 with a fresh
allowance, which proves the bucket is per reservation and not global.
The messages endpoint returns the `x-ratelimit-limit` and
`x-ratelimit-remaining` headers, and on a 429 also `retry-after` and
`x-ratelimit-reset`.

The per-token 50-per-5-minutes limit is taken from Hospitable's
documentation and **has never been observed**. The integration enforces
it locally anyway, because enforcing a limit that may not exist costs
nothing and exceeding one that does is worse. What is tested is the
enforcement; the upstream existence of this limit is not.

`/properties`, `/reservations` and `/tasks` expose **no** rate-limit
headers at all. The limits above should not be generalised to them.

The budget is shared per **token**, not per config entry. Two config
entries using the same Personal Access Token draw on one budget.

### Enabling awaiting-host-reply consumes budget

The `awaiting_host_reply` option reads message threads, so it consumes
per-reservation budget. The message poll is therefore held to at most
one fetch per 60 seconds per reservation, which deliberately leaves
half the confirmed allowance free for messages you send yourself.

That floor is a **conservative choice, not a measured upstream
maximum**, and the reason is [OQ-007](#open-questions): it is not known
whether reads and writes draw on the same per-reservation bucket. If
they do, an aggressive poll could consume budget you need to send a
message. The integration is defensive in both directions rather than
assuming an answer.

If a poll is refused or throttled, the message entities keep their last
known values and the poll does not fail. A 429 carrying `retry-after`
is honoured; one without it backs off on a local schedule.

## Evidence tiers

This documentation distinguishes three tiers, and they are not
interchangeable:

- **CONFIRMED-BY-TEST** — observed against the live API by a read-only
  probe, or enforced by an automated test in this repository.
- **DOCUMENTED-ONLY** — stated by Hospitable's documentation and never
  observed here.
- **INFERRED** — deduced from behaviour and neither documented nor
  directly observed.

## Open questions

Three questions remain genuinely open. **They cannot be closed without
issuing a real message send to a real guest**, which has deliberately
not been done.

- **OQ-001 — the shape of the 202 response body.** The integration
  handles a correlation identifier if one is present and treats an
  empty body as success rather than as an error, because it does not
  know which it will get.
- **OQ-005 — whether a Personal Access Token carries the message-send
  scope.** An HTTP 403 from the send endpoint is reported with wording
  that names a possible missing scope, rather than being reported as a
  generic failure.
- **OQ-007 — whether reads and writes share one per-reservation
  bucket.** The confirmed read limit and the documented send limit are
  both 2 per 60 seconds per reservation, which makes a shared bucket
  plausible but unproven. Nothing in the code or the tests asserts an
  answer either way.

**OQ-002 is closed** (CONFIRMED-BY-TEST, 2026-08-12): the messages
endpoint is not paginated and silently ignores `page` and `per_page`.
`/tasks` pagination, by contrast, is real.

## Diagnostics

Downloading diagnostics from the integration's entry gives configuration
and coordinator state with guest fields shown as `**REDACTED**`. The
Personal Access Token is never included.

## Terminology

User-facing text calls the rental object a **property**. It must not call
that object a listing or a unit. The `property_info` diagnostic attribute
named `listings` is the code-level API-derived channel reference list;
it is not a user-facing name for the property itself.

## Known upstream limitation: OQ-004

Hospitable requires a `properties[]` filter on `GET /reservations`. A
request without that filter returns HTTP 400. Because of that upstream
API design, the integration cannot enumerate reservations for properties
that the user has not selected.

Consequence: if a reservation belongs to a property that is not selected,
it is invisible to this integration. There is no orphan-reservation
discovery path, and this is not a bug the integration can fix locally.
