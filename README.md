<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Hospitable for Home Assistant

Hospitable is a read-only Home Assistant custom integration for the
Hospitable Public API v2. It lets you select properties, then creates
sensor entities for reservation state, property details, and aggregate
calendar availability.

The integration uses Hospitable Personal Access Tokens. Public API
access requires a paid Hospitable plan; Essentials plans are excluded.
The token needs read access to user, property, reservation, and calendar
data.

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
