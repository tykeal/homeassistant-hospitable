<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Data Model: Hospitable Home Assistant Integration

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) |
**Research**: [research.md](./research.md)

**Date**: 2026-08-08

## Scope of this document

This describes the in-memory domain model, the entity surface, and the
persisted config entry shape. It does not describe HTTP wire format;
that is [contracts/upstream-requests.md](./contracts/upstream-requests.md).

Every model is a frozen dataclass built by an explicit `from_api()`
classmethod that validates required keys and raises
`HospitableResponseError` on a shape violation (FR-034). No third-party
deserializer is used; see [research.md](./research.md#d-04) for why.

## Domain models

### `HospitableAccount`

Built from `GET /user`. Used only during config flow and reauth; it is
never held by a coordinator, because it carries account-level personal
data (FR-073) that nothing in this feature displays.

| Field | Type | Source | Tier | Notes |
| --- | --- | --- | --- | --- |
| `account_id` | `str` | `data.id` | CONFIRMED | 36-char UUID. The FR-013 duplicate guard and the FR-055 namespace |

Every other key on that response — email, name, billing and postal
address, company name, VAT number, tax identifier — is **read into
nothing**. The model has no field for any of them, so they cannot reach
a log, a diagnostic, or the config entry. This mirrors the D-11
technique of enforcing a prohibition structurally.

### `HospitableProperty`

Built from an item of `GET /properties`.

| Field | Type | Source | Tier | Notes |
| --- | --- | --- | --- | --- |
| `property_id` | `str` | `id` | CONFIRMED | Immutable; part of every unique ID |
| `name` | `str` | `name` | CONFIRMED | Display name; mutable upstream |
| `public_name` | `str \| None` | `public_name` | CONFIRMED | |
| `address` | `PropertyAddress` | `address` | CONFIRMED | Nested model below |
| `checkin` | `str \| None` | `checkin` | CONFIRMED | Raw string; FR-045 scheduled-time source |
| `checkout` | `str \| None` | `checkout` | CONFIRMED | Raw string; FR-045 scheduled-time source |
| `capacity` | `PropertyCapacity \| None` | `capacity` | CONFIRMED | |
| `currency` | `str \| None` | `currency` | CONFIRMED | ISO 4217 |
| `listed` | `bool` | `listed` | CONFIRMED | |
| `property_type` | `str \| None` | `property_type` | CONFIRMED | Device model string |
| `listings` | `tuple[HospitableListing, ...]` | `listings` | CONFIRMED | Present only with `include=listings`; empty tuple when the FR-075 assertion fails |
| `listings_available` | `bool` | derived | — | `False` when the include assertion failed; surfaced as an attribute so the gap is visible |

**Deliberately absent**: `timezone`. See
[research.md D-11](./research.md#d-11). The upstream value is a fixed
UTC offset and FR-074 prohibits its use, so the model provides no way
to reach it. A unit test asserts the attribute does not exist.

**Also absent**: `picture`, `summary`, `description`, `amenities`,
`room_details`, `house_rules`, `tags`, `calendar_restricted`,
`parent_child`, `ical_imports`. Nothing in FR-042 through FR-061
requires them, and every field admitted to the model is a field that
must then be redaction-audited. Admitting only what is used is the
cheapest way to keep FR-073 true.

### `PropertyAddress`

| Field | Type | Source | Tier |
| --- | --- | --- | --- |
| `city` | `str \| None` | `address.city` | CONFIRMED |
| `state` | `str \| None` | `address.state` | CONFIRMED |
| `country` | `str \| None` | `address.country` | CONFIRMED |
| `display` | `str \| None` | `address.display` | CONFIRMED |

`number`, `street`, `postcode`, and `coordinates` are not read.
FR-053 requires "the property address" as an attribute; `display` is
the upstream-composed human-readable form and satisfies it without
admitting a street number and postcode into diagnostics scope.

### `PropertyCapacity`

| Field | Type | Source | Tier |
| --- | --- | --- | --- |
| `max` | `int \| None` | `capacity.max` | CONFIRMED-BY-TEST (13/13) |
| `bedrooms` | `int \| None` | `capacity.bedrooms` | CONFIRMED-BY-TEST (13/13) |
| `beds` | `int \| None` | `capacity.beds` | CONFIRMED-BY-TEST (13/13) |
| `bathrooms` | `float \| None` | `capacity.bathrooms` | CONFIRMED-BY-TEST (13/13) |

The `capacity` object and all four inner keys are CONFIRMED-BY-TEST
from the 2026-08-09 live property probe across 13 properties. Every
field remains optional in the model as defensive degradation, and an
unexpected inner shape yields `None` rather than failing the poll.

### `HospitableListing`

Built from an item of `property.listings`, present only under
`include=listings`.

| Field | Type | Source | Tier | Notes |
| --- | --- | --- | --- | --- |
| `platform` | `str` | `platform` | CONFIRMED | FR-053 "channel" |
| `platform_id` | `str` | `platform_id` | CONFIRMED | FR-053 "channel identifier" |

`platform_user_id`, `platform_picture`, `co_hosts`, `platform_name`,
and `platform_email` are **not read into the model**. FR-073 names all
five as personal data. FR-053 asks only for the channel and its
identifier, so the personal fields have no consumer and are dropped at
the boundary rather than admitted and then redacted. Dropping is
strictly safer than redacting, because it cannot be forgotten at a new
call site.

### `HospitableReservation`

Built from an item of `GET /reservations`.

| Field | Type | Source | Tier | Notes |
| --- | --- | --- | --- | --- |
| `reservation_id` | `str` | `id` | CONFIRMED | FR-044 deterministic tiebreak; FR-046 attribute |
| `property_id` | `str` | property reference | CONFIRMED | Asserted to be in the requested set (D-05) |
| `status_category` | `ReservationStatusCategory` | `reservation_status.current` | CONFIRMED-BY-TEST | FR-032; live probe 2026-08-09 confirmed `reservation_status` has `{current, history}` |
| `raw_status` | `str` | `status` | CONFIRMED-BY-TEST | Retained for the FR-048 log-once path |
| `arrival_date` | `datetime` | `arrival_date` | CONFIRMED-BY-TEST | Midnight-anchored date serialized as an offset-aware datetime; live probe 2026-08-09 |
| `departure_date` | `datetime` | `departure_date` | CONFIRMED-BY-TEST | Midnight-anchored date serialized as an offset-aware datetime; live probe 2026-08-09 |
| `nights` | `int \| None` | `nights` | CONFIRMED-BY-TEST | FR-046; live probe 2026-08-09 |
| `scheduled_checkin_raw` | `str \| None` | `check_in` | CONFIRMED-BY-TEST | ISO 8601 datetime with UTC offset; live probe 2026-08-09 |
| `scheduled_checkout_raw` | `str \| None` | `check_out` | CONFIRMED-BY-TEST | ISO 8601 datetime with UTC offset; live probe 2026-08-09 |
| `guests` | `GuestBreakdown` | `guests` | CONFIRMED-BY-TEST | Counts only; base payload confirmed by live probe 2026-08-09 — not the `include=guests` expansion, which is a separate, unrelated no-op |
| `channel` | `str \| None` | `platform` | CONFIRMED-BY-TEST | FR-046 booking channel; live probe 2026-08-09 confirmed the reservation payload has no `channel` key |
| `channel_confirmation` | `str \| None` | `platform_id` | CONFIRMED-BY-TEST | FR-046 confirmation code; live probe 2026-08-09; `code` matched `platform_id` in 50/50 samples but is an alias and MUST NOT be relied on independently |
| `booking_date` | `datetime \| None` | `booking_date` | CONFIRMED-BY-TEST | FR-046; UTC timestamp with trailing `Z`; live probe 2026-08-09 |
| `stay_type` | `str \| None` | `stay_type` | CONFIRMED-BY-TEST | FR-049; orthogonal to status |

**Deliberately absent**: any guest identity. No name, email, phone,
picture, or conversation content is read. `conversation_id` is not read
either, because nothing displays it and it is a handle to message
content.

`arrival_date` and `departure_date` are midnight-anchored dates
serialized as offset-aware datetimes. Parse each as an offset-aware
datetime, then take the date component in the reservation's own offset.
Never convert to another zone before taking the date — the value is
midnight-anchored, so an eastward conversion can roll it to the
following day. `check_in` and `check_out` carry the real scheduled
times and are not equal to the midnight anchors.

### `GuestBreakdown`

| Field | Type | Tier |
| --- | --- | --- |
| `total` | `int` | CONFIRMED-BY-TEST |
| `adults` | `int` | CONFIRMED-BY-TEST |
| `children` | `int` | CONFIRMED-BY-TEST |
| `infants` | `int` | CONFIRMED-BY-TEST |
| `pets` | `int` | CONFIRMED-BY-TEST |

Counts are not personal data. Identities are, and are not modelled.
The live probe on 2026-08-09 confirmed the upstream inner keys are
`total`, `adult_count`, `child_count`, `infant_count`, and `pet_count`.

### `CalendarDay` and `PropertyCalendar`

Built from `GET /properties/{id}/calendar`. The response `data` is an
object, not a list — unusual for this API and worth stating, because
the generic list-envelope parser must not be applied to it.

`PropertyCalendar`:

| Field | Type | Source | Tier |
| --- | --- | --- | --- |
| `property_id` | `str` | request path | — |
| `start_date` | `date` | `data.start_date` | CONFIRMED |
| `end_date` | `date` | `data.end_date` | CONFIRMED |
| `days` | `tuple[CalendarDay, ...]` | `data.days` | CONFIRMED |

`data.listing_id` and `data.provider` are **not read**. They are
cosmetic listing metadata on an aggregate calendar (OQ-010 RESOLVED),
and reading them into the model would invite a future contributor to
treat the aggregate as listing-scoped.

`CalendarDay`:

| Field | Type | Source | Tier |
| --- | --- | --- | --- |
| `day_date` | `date` | `date` | CONFIRMED |
| `available` | `bool` | `status.available` | CONFIRMED |
| `reason` | `str \| None` | `status.reason` | CONFIRMED |
| `min_stay` | `int \| None` | `min_stay` | CONFIRMED |
| `closed_for_checkin` | `bool` | `closed_for_checkin` | CONFIRMED |
| `closed_for_checkout` | `bool` | `closed_for_checkout` | CONFIRMED |
| `price` | `MoneyAmount \| None` | `price` | CONFIRMED |

`note` is not read; it is free text that could carry anything a manager
typed, which under FR-073's default-sensitive rule is not worth the
risk for zero requirement coverage.

### `MoneyAmount`

| Field | Type | Source | Tier |
| --- | --- | --- | --- |
| `minor_units` | `int` | `amount` | CONFIRMED |
| `currency` | `str` | `currency` | CONFIRMED |

FR-060 requires integer minor units and prohibits presenting them as
major units. The model name and field name both say `minor_units` so a
call site cannot mistake it. Conversion to a display value happens once,
in the sensor layer, using the currency's minor-unit exponent; the model
never carries a float.

## Field binding table

Bindings the specification does not pin. Confirmed rows name the single
key the live probe established. Remaining UNVERIFIED rows are resolved
by a documented candidate list and have defined behavior when no
candidate is present.

| Role | Candidate keys, in order | Tier | Absent behavior |
| --- | --- | --- | --- |
| Reservation status category | `reservation_status.current` | CONFIRMED-BY-TEST; live probe 2026-08-09 | `HospitableResponseError` — FR-032 makes this load-bearing, so it must fail loudly |
| Reservation arrival datetime | `arrival_date` | CONFIRMED-BY-TEST; live probe 2026-08-09 | `HospitableResponseError`; FR-044 and FR-045 cannot run without it |
| Reservation departure datetime | `departure_date` | CONFIRMED-BY-TEST; live probe 2026-08-09 | `HospitableResponseError` |
| Reservation nights | `nights` | CONFIRMED-BY-TEST; live probe 2026-08-09 | Attribute reports `None`; state is unaffected (FR-046) |
| Reservation scheduled check-in time | `check_in` | CONFIRMED-BY-TEST; live probe 2026-08-09 | Attribute reports `None`; boundary occupancy becomes `unknown` (FR-045) |
| Reservation scheduled check-out time | `check_out` | CONFIRMED-BY-TEST; live probe 2026-08-09 | Attribute reports `None`; boundary occupancy becomes `unknown` (FR-045) |
| Reservation channel confirmation identifier | `platform_id` | CONFIRMED-BY-TEST; live probe 2026-08-09 | Attribute reports `None`; state is unaffected (FR-046) |
| Reservation booking date | `booking_date` | CONFIRMED-BY-TEST; live probe 2026-08-09 | Attribute reports `None`; state is unaffected (FR-046) |
| Stay type | `stay_type` | CONFIRMED-BY-TEST; live probe 2026-08-09 | Attribute reports `None`; state is unaffected (FR-049) |

**Rule**: a required-role binding that resolves to nothing raises. An
optional-role binding that resolves to nothing degrades an attribute.
The two scheduled-time roles are confirmed top-level datetimes, not a
candidate search. If either is absent or unusable, FR-045's `unknown`
path fires on the affected boundary date. Silent substitution of a
default time is prohibited at every tier.

## Reservation status mapping

Six upstream categories (FR-043). All six are mapped; none is dropped.

| Upstream category | Tier | Maps to |
| --- | --- | --- |
| `accepted` | CONFIRMED observed | Occupancy derivation (below) |
| `cancelled` | CONFIRMED observed | `cancelled` |
| `not accepted` | CONFIRMED observed | `not_accepted` |
| `checkpoint` | CONFIRMED observed | `checkpoint` |
| `request` | UNVERIFIED (A-6, OQ-013) | `pending_request` |
| `unknown` | UNVERIFIED (A-6, OQ-013) | `unknown` |
| anything else | — | `unknown`, logged once per distinct value (FR-048) |

FR-048 explicitly forbids the fallback from firing for a published
category, so `checkpoint` has its own state rather than collapsing into
`unknown`. The log-once cache is keyed on the raw value and bounded, so
a hostile or buggy upstream cannot grow it without limit (FR-039).

## Sensor state enum

The reservation status sensor is a `SensorDeviceClass.ENUM` with a
fixed, closed option list (FR-043). It is single-dimensional: it
encodes reservation status and occupancy, and nothing else. Stay type
is an attribute (FR-049), never a state.

| State | Meaning | Produced when |
| --- | --- | --- |
| `no_reservation` | No reservation in the window | The window contains no reservation for this property (FR-047) |
| `awaiting_checkin` | Accepted, not yet arrived | Accepted, and now is before the scheduled check-in moment |
| `occupied` | Guest or owner in residence | Accepted, and the scheduled check-in moment has passed but not the check-out moment |
| `checked_out` | Stay complete | Accepted, and the scheduled check-out moment has passed |
| `pending_request` | Awaiting host decision | Category `request` |
| `checkpoint` | Platform verification step | Category `checkpoint` |
| `cancelled` | Cancelled | Category `cancelled` |
| `not_accepted` | Declined or expired | Category `not accepted` |
| `unknown` | Undeterminable | Category `unknown`, an unrecognized category, or an FR-045 missing-time data error |

`unavailable` is not in this list and never will be. Home Assistant
owns that value and it means the integration cannot reach the data
(FR-047, FR-057).

## Occupancy derivation

Governed by FR-045. Hospitable publishes no checked-in status
(CONFIRMED by census, OQ-008), so occupancy is derived.

```text
checkin_at    = parse_moment(res.check_in)
checkout_at   = parse_moment(res.check_out)
now           = current instant
today         = current date in the property's effective IANA zone (FR-074)

if checkin_at is None or checkout_at is None:
    if today is local_date(arrival_date) or
       today is local_date(departure_date):               -> unknown + warn once
    else:                                                 -> evaluate by date alone
elif now <  checkin_at:                                    -> awaiting_checkin
elif now <  checkout_at:                                   -> occupied
else:                                                      -> checked_out
```

Four properties of this algorithm are load-bearing and each is
separately required:

1. **All occupancy comparisons are instant comparisons using the
   reservation's own offset-aware timestamps.** Never reinterpret
   `check_in` or `check_out` in the configured timezone. The effective
   IANA zone of FR-074 is only for the boundary-date `today` test and
   date-relative presentation.
2. **A missing time is a data error, not a case to smooth over.** No
   midnight fallback exists anywhere in the code. This is stated as a
   negative requirement in FR-045 and is tested as one: a test asserts
   that a reservation with an unparsable check-in string on its
   arrival date yields `unknown`, not `occupied` and not
   `awaiting_checkin`.
3. **The degradation is scoped to the two boundary dates.** A
   reservation three days into a stay needs no scheduled time to be
   known occupied, so a missing time does not blank out a mid-stay
   property.
4. **Owner stays derive occupancy identically to guest stays**
   (US2 acceptance scenario 7). Stay type never enters this function.

## Reservation selection

Governed by FR-044. Exactly one reservation drives the sensor state; the
rest populate an `upcoming_reservations` attribute.

Ordering, applied until one reservation is selected:

1. A reservation currently in progress under the occupancy derivation.
2. The soonest future arrival, by arrival datetime then scheduled
   check-in moment.
3. The most recent past departure, by departure datetime then scheduled
   check-out moment.

Within every tier, reservations whose category is `cancelled` or
`not accepted` rank below all others. Any remaining tie breaks by
ascending reservation identifier, which makes selection deterministic
and therefore testable — a non-deterministic selection would produce an
entity that flaps between two equally ranked reservations across polls.

## Entity surface

Six sensors per selected property, one device per selected property
(FR-050). No entity is created for an unselected property, and no
entity is ever created per reservation (FR-042, and the Out of Scope
section's explicit rejection).

| Entity key | Class | Device class | Requirements |
| --- | --- | --- | --- |
| `reservation_status` | Enum sensor | `ENUM` | FR-042, FR-043, FR-044, FR-045, FR-046, FR-047, FR-048, FR-049 |
| `next_arrival` | Timestamp sensor | `TIMESTAMP` | FR-051 |
| `next_departure` | Timestamp sensor | `TIMESTAMP` | FR-051 |
| `upcoming_reservations` | Numeric sensor | none | FR-052 |
| `property_info` | Diagnostic sensor | none | FR-053 |
| `availability` | Enum sensor | `ENUM` | FR-058, FR-060, FR-061 |

`next_arrival` and `next_departure` report `None` when there is no
applicable future reservation, never a stale value (US3 acceptance
scenario 2). Reservation instants retain their own offset-aware
timestamps; the property's effective IANA zone is only for day-boundary
and date-relative presentation.

`property_info` is `EntityCategory.DIAGNOSTIC`. Its state is the
property's display name; its attributes carry the FR-053 payload.

`availability` options are `available`, `booked`, and `unknown`.
`booked` is used for an unavailable night, never the word
`unavailable` (FR-058, US7 acceptance scenario 2).

### Entity identifiers

FR-054 requires `sensor.hospitable_<property>_<attribute>`. Home
Assistant's `_attr_has_entity_name` would otherwise generate
`sensor.<device>_<entity>` with no domain prefix, so each entity sets:

```text
suggested_object_id = f"hospitable_{slugify(property.name)}_{key}"
```

`suggested_object_id` governs the identifier assigned at entity
creation. A user remains free to rename afterwards; FR-054 constrains
the default, which is what the integration controls.

### Unique identifiers

FR-055 freezes this format. It is composed exclusively of immutable
parts:

```text
unique_id = f"{account_namespace}_{property_id}_{entity_key}"
```

`account_namespace` is the `HospitableAccount.account_id` UUID where
available (CONFIRMED to be, OQ-009), otherwise the config entry's own
`entry_id`. Whichever is chosen is written into `entry.data` at
creation and never changes (FR-055). Nothing derived from a property
*name* appears, so renaming a property upstream cannot orphan an entity
or destroy recorder history (FR-055, SC-006, US3 acceptance scenario 3).

This format is frozen. Changing it in any later specification requires
a migration under FR-070 that preserves every existing identifier.

### Attribute contracts

Full attribute payloads are normative in
[contracts/entities.md](./contracts/entities.md). Summarized here:

`reservation_status` carries the FR-046 set — arrival datetime,
departure datetime, nights, scheduled check-in and check-out times,
total guest count with its adult, child, infant and pet breakdown,
booking channel,
channel confirmation identifier, booking date, stay type, reservation
identifier — plus `upcoming_reservations` from FR-044.

`property_info` carries the FR-053 set — address, configured check-in
and check-out times, guest capacity, the **effective IANA timezone the
integration is actually using**, and channel listings with each
listing's channel and channel identifier — plus `listings_available` so
a failed `include=listings` assertion is visible rather than silent.

`availability` carries the nightly rate and currency for today plus a
short forward window of days.

### Availability semantics

| Condition | Entity availability |
| --- | --- |
| Fewer than three consecutive coordinator failures | Available, showing last known values (FR-057) |
| Three or more consecutive coordinator failures | Unavailable (FR-057) |
| Property deselected by the user | Unavailable, registry entry retained (FR-018) |
| Property disappeared upstream | Unavailable, registry entry retained (FR-056) |
| Property has no reservation in the window | **Available**, state `no_reservation` (FR-047, SC-012) |

The last row is the one most often got wrong, and SC-012 requires it in
100% of cases.

Deselection and upstream disappearance are handled by the same code
path and are both non-destructive. Nothing is removed from the entity
registry, so reselecting a property restores its identifiers and its
recorder history (FR-018, US4 acceptance scenario 4).

## Persisted config entry

`VERSION = 1`, `MINOR_VERSION = 1` (FR-070).

`entry.unique_id` is the account UUID, which is what makes FR-013's
duplicate-account abort work without comparing token values.

### `entry.data` — immutable identity

| Key | Type | Notes |
| --- | --- | --- |
| `token` | `str` | The PAT. Config entry storage only (FR-003) |
| `account_namespace` | `str` | Frozen at creation (FR-055) |
| `namespace_source` | `"account" \| "entry"` | Records which FR-055 branch was taken |

### `entry.options` — user-changeable

| Key | Type | Default | Bounds | Requirements |
| --- | --- | --- | --- | --- |
| `selected_properties` | `list[str]` | none | at least 1 | FR-011, FR-015, FR-018 |
| `reservation_interval_minutes` | `int` | 5 | floor 1 | FR-019 |
| `property_interval_minutes` | `int` | 60 | floor 15 | FR-020 |
| `lookback_days` | `int` | 90 | 7 to 365 | FR-021, FR-022 |
| `lookahead_days` | `int` | 90 | 1 to 730 | FR-021, FR-022 |
| `timezone_overrides` | `dict[str, str]` | `{}` | valid IANA | FR-074 |

Splitting identity into `data` and preferences into `options` means an
options change never triggers a data migration, and a reauth replaces
exactly one `data` key while leaving every preference and every entity
untouched (FR-014).

## Coordinator data shapes

| Coordinator | Generic type |
| --- | --- |
| `HospitablePropertiesCoordinator` | `DataUpdateCoordinator[dict[str, HospitableProperty]]` |
| `HospitableReservationsCoordinator` | `DataUpdateCoordinator[dict[str, tuple[HospitableReservation, ...]]]` |
| `HospitableCalendarCoordinator` | `DataUpdateCoordinator[dict[str, PropertyCalendar]]` |

All three key on `property_id`. Every entity reads from coordinator
data and issues no request of its own (FR-071, Principle VIII).

The reservations coordinator re-filters its merged result set against
the configured window before storing it, so retained memory is bounded
by the window regardless of what the server returns (FR-039). Widening
the window is the only way to grow it, and doing so is a deliberate,
warned user action (FR-023).
