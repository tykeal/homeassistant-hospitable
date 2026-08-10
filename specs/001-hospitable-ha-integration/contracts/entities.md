<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract: Entity Surface

**Feature**: [../spec.md](../spec.md) |
**Data model**: [../data-model.md](../data-model.md)

The entity surface is this integration's public API. Automations and
dashboards bind to it, and Principle VII requires state attributes to
remain backward compatible unless explicitly versioned with a
documented migration path. Everything below is therefore a contract,
not an implementation note.

## Platform scope

**Sensor only.** No `binary_sensor`, no `calendar`, no `switch`, no
`button`, no `event`. FR-054 restricts this feature to the sensor
platform, and the Out of Scope section separately rejects Home
Assistant calendar entities.

**No Home Assistant services are registered.** FR-069 defines the
integration's `services/` package as domain logic — reservation
selection, occupancy derivation, status mapping, window computation —
and explicitly states it is not Home Assistant service-call
registration. This feature defines no user-invocable service.

## Devices

One device per selected property (FR-050).

| Property | Value |
| --- | --- |
| Identifier | `(DOMAIN, f"{account_namespace}_{property_id}")` |
| Name | Property display name, refreshed on each property poll |
| Model | Property type |
| Manufacturer | `Hospitable` |

Renaming a property upstream changes the device name and nothing else.
No identifier is derived from a name (FR-055, SC-006).

## Identifier contracts

| Contract | Format |
| --- | --- |
| Entity ID (default at creation) | `sensor.hospitable_<property_slug>_<entity_key>` |
| Unique ID (frozen, FR-055) | `<account_namespace>_<property_id>_<entity_key>` |

The entity ID is set through `suggested_object_id`, which governs the
identifier assigned at creation; users remain free to rename
afterwards.

The unique ID format is **frozen**. Changing it in any later
specification requires an FR-070 migration that preserves every
existing identifier and its recorder history. Both components are
immutable: the namespace is written into `entry.data` at creation and
never changes, and the property identifier is upstream-immutable.

## Entities

### `reservation_status`

Requirements: FR-042, FR-043, FR-044, FR-045, FR-046, FR-047, FR-048,
FR-049.

| Property | Value |
| --- | --- |
| Device class | `SensorDeviceClass.ENUM` |
| Translation key | `reservation_status` |
| Options | `no_reservation`, `awaiting_checkin`, `occupied`, `checked_out`, `pending_request`, `checkpoint`, `cancelled`, `not_accepted`, `unknown` |

Exactly one per property, regardless of reservation count. Per-reservation
entities are prohibited (FR-042).

**Attributes**:

| Attribute | Type | Requirement |
| --- | --- | --- |
| `reservation_id` | `str \| None` | FR-046 |
| `arrival_date` | `date \| None` | FR-046 |
| `departure_date` | `date \| None` | FR-046 |
| `nights` | `int \| None` | FR-046 |
| `scheduled_checkin` | `datetime \| None` | FR-046 |
| `scheduled_checkout` | `datetime \| None` | FR-046 |
| `guests_total` | `int \| None` | FR-046 |
| `guests_adults` | `int \| None` | FR-046 |
| `guests_children` | `int \| None` | FR-046 |
| `guests_infants` | `int \| None` | FR-046 |
| `guests_pets` | `int \| None` | FR-046 |
| `booking_channel` | `str \| None` | FR-046 |
| `channel_confirmation` | `str \| None` | FR-046 |
| `booking_date` | `datetime \| None` | FR-046 |
| `stay_type` | `str \| None` | FR-049 |
| `upcoming_reservations` | `list[dict]` | FR-044 |

`scheduled_checkin` and `scheduled_checkout` are the reservation's own
offset-aware moments from `check_in` and `check_out`. They are not
reinterpreted in the property's effective timezone. They are `None`
when no usable scheduled time exists, which is exactly when the state
is `unknown` on a boundary date.

`upcoming_reservations` entries carry the reservation identifier,
arrival date, departure date, status category, and stay type. They
carry no guest identity. `arrival_date` and `departure_date` are exposed
as `date`, not a midnight-anchored `datetime`, because the upstream
value is a midnight-anchored date taken in the reservation's own offset;
re-anchoring it as a datetime would reintroduce the day-roll hazard that
converting a midnight instant across zones causes.

`stay_type` is an attribute and never part of the state. An owner stay
can independently be awaiting check-in, occupied, checked out, or
cancelled (FR-049), so folding it into the enum would make the enum
two-dimensional and break FR-043.

**No guest identity appears in any attribute.** No name, email, phone,
picture, or message content. Only counts.

### `next_arrival` and `next_departure`

Requirements: FR-051.

| Property | Value |
| --- | --- |
| Device class | `SensorDeviceClass.TIMESTAMP` |
| State | Reservation offset-aware moment, or `None` |

`None` when there is no applicable future reservation. Never a stale
value (US3 acceptance scenario 2). A stale timestamp on a
`TIMESTAMP` sensor is worse than no value, because an automation
comparing against `now()` would fire on a departure that already
happened.

### `upcoming_reservations`

Requirements: FR-052.

| Property | Value |
| --- | --- |
| State | Count of upcoming reservations within the configured window |
| State class | `MEASUREMENT` |

Counts reservations whose arrival is in the future, excluding those
whose category is `cancelled` or `not accepted`.

### `property_info`

Requirements: FR-053.

| Property | Value |
| --- | --- |
| Entity category | `DIAGNOSTIC` |
| State | Property display name |

**Attributes**:

| Attribute | Type | Requirement |
| --- | --- | --- |
| `address` | `str \| None` | FR-053 |
| `checkin_time` | `str \| None` | FR-053 |
| `checkout_time` | `str \| None` | FR-053 |
| `max_guests` | `int \| None` | FR-053 |
| `effective_timezone` | `str` | FR-053, FR-074 |
| `timezone_source` | `"override" \| "instance"` | FR-074 |
| `listings` | `list[{platform, platform_id}]` | FR-053 |
| `listings_available` | `bool` | FR-075 |

`effective_timezone` is always an IANA zone name. It is **never** the
upstream `timezone` value, which is a fixed UTC offset and is not read
into any model (FR-074).

`timezone_source` exists so a user can see at a glance whether their
per-property override took effect, which turns FR-074 into something a
user can verify rather than trust. The effective timezone applies to
day-boundary determinations and date-relative presentation; it is not
applied to reservation occupancy instants.

`listings_available` is `False` when the `include=listings` post-condition
failed. It makes an FR-075 degradation visible on the entity instead of
only in a log line, so an empty `listings` list is never ambiguous
between "no channel listings" and "the expansion did not arrive".

### `availability`

Requirements: FR-058, FR-059, FR-060, FR-061.

| Property | Value |
| --- | --- |
| Device class | `SensorDeviceClass.ENUM` |
| Translation key | `availability` |
| Options | `available`, `booked`, `unknown` |

**`unavailable` is not an option and never will be.** Home Assistant
reserves that value to mean the integration cannot reach the data, so
FR-058 requires `booked` for an unavailable night. Using `unavailable`
here would make a fully booked property indistinguishable from a broken
integration.

**Attributes**:

| Attribute | Type | Requirement |
| --- | --- | --- |
| `nightly_rate` | `float \| None` | FR-058, FR-060 |
| `currency` | `str \| None` | FR-058 |
| `min_stay` | `int \| None` | FR-058 |
| `closed_for_checkin` | `bool \| None` | FR-058 |
| `closed_for_checkout` | `bool \| None` | FR-058 |
| `forward_window` | `list[dict]` | FR-058 |

`nightly_rate` is converted from integer minor units exactly once, in
this sensor, using the currency's minor-unit exponent. The domain model
carries only `minor_units` and never a float (FR-060). `forward_window`
entries carry date, availability, and rate.

This data is refreshed on the property cadence, not the reservation
cadence (FR-061).

**Read-only, absolutely.** FR-059 prohibits any calendar modification
request under any circumstance. The enforcement is structural: the API
client exposes no calendar write method, and the entity exposes no
service. A test asserts that a full lifecycle — setup, refresh, options
change, unload — issues zero non-`GET` requests.

## Availability semantics

| Condition | Entity availability | Requirement |
| --- | --- | --- |
| Fewer than three consecutive coordinator failures | Available, last known values retained | FR-057 |
| Three or more consecutive coordinator failures | Unavailable | FR-057 |
| Property deselected | Unavailable, registry entry retained | FR-018 |
| Property gone upstream | Unavailable, registry entry retained | FR-056 |
| No reservation in the window | **Available**, state `no_reservation` | FR-047, SC-012 |
| Calendar fetch failed for this property only | Only `availability` unavailable | Research D-15 |

Home Assistant's stock `CoordinatorEntity.available` returns
`last_update_success`, which goes unavailable after a *single* failure.
That violates FR-057, so a shared mixin tracks consecutive failures and
availability is `data is present and consecutive_failures < 3`.

Deselection and upstream disappearance are non-destructive and share
one code path. No registry entry is removed, so reselecting restores
identifiers and recorder history (FR-018, FR-056, US4 acceptance
scenario 4).

## Terminology

FR-068 requires "property" for Hospitable's core rental unit and
"listing" only for a channel-side mapping. This applies to every
user-facing string: entity names, config and options flow labels, error
messages, repair issue text, and translation keys. The word "listing"
appears in exactly one user-facing place, the `listings` attribute of
`property_info`, where it is correct.

Internal identifiers follow the same rule, so a future contributor is
not led into user-facing drift by an internal name.
