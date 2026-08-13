<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract: Entity Surface (Spec 003 Amendments)

**Feature**: [../spec.md](../spec.md) |
**Data model**: [../data-model.md](../data-model.md)

This document defines entity changes introduced by spec 003. Spec
001's entity contract and spec 002's
[entities.md](../../002-actions-and-messaging/contracts/entities.md)
remain authoritative for their respective surfaces.

## Changes to spec 001 entity contract

### `property_info` sensor attribute contract (AMENDED)

Spec 001 established a closed attribute set of exactly eight
attributes on the `property_info` diagnostic sensor. The docstring
on `HospitablePropertyInfoSensor.extra_state_attributes` states
"Return exactly the eight property_info contract attributes."

**Spec 003 amends this to nine attributes.** The addition is
`property_id` — the Hospitable property UUID string.

| Attribute | Type | New? | Notes |
| --- | --- | --- | --- |
| `address` | `str \| None` | No | Unchanged |
| `checkin_time` | `str \| None` | No | Unchanged |
| `checkout_time` | `str \| None` | No | Unchanged |
| `max_guests` | `int \| None` | No | Unchanged |
| `effective_timezone` | `str` | No | Unchanged |
| `timezone_source` | `str` | No | Unchanged |
| `listings` | `list[dict]` | No | Unchanged |
| `listings_available` | `bool` | No | Unchanged |
| `property_id` | `str` | **Yes** | FR-011; opaque UUID, no PII |

**Privacy**: `property_id` is an opaque account-scoped identifier
containing no personal data (FR-014). It is freely recordable,
displayable, and loggable. No unrecorded-attributes treatment is
needed.

**Backward compatibility**: Purely additive. Existing automations
referencing the eight original attributes are unaffected. No state
change event beyond the normal attribute-update-on-next-poll is
expected.

### Service registration statement (EXTENDED)

Spec 002 stated: Five Home Assistant services are registered.

**Spec 003 extends this to**: Six Home Assistant services are
registered. `list_properties` is added alongside the existing five.

## Changes to spec 002 service definitions

### `get_reservations` and `get_property_info` (MODIFIED)

Both services gain a `target` definition enabling entity/device
selectors in the Home Assistant UI picker. The `property_id` field
changes from required to optional. See
[contracts/services.md](./services.md) for the full contract.

## No new entities

Spec 003 introduces no new entity types.

## Device scope (unchanged)

One device per selected property. No new devices.

## Platform scope (unchanged)

Sensor only. No new platform.
