<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Data Model: Property Discovery

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) |
**Research**: [research.md](./research.md)

**Date**: 2026-08-13

## Scope

This describes the new and modified domain models introduced by spec
003. No new coordinators, no new entities beyond the attribute
addition. No config entry changes.

## New domain models

### `HospitableCoHost`

A frozen dataclass representing one co-host on a listing. Lives in
`api/models.py` alongside `HospitableListing`.

| Field | Type | Source key | Tier | Notes |
| --- | --- | --- | --- | --- |
| `user_id` | `str` | `user_id` | CONFIRMED-BY-TEST | Unconditionally returnable (FR-047b) |
| `channel_name` | `str` | `channel_name` | CONFIRMED-BY-TEST | Unconditionally returnable (FR-047b) |
| `name` | `str` | `name` | CONFIRMED-BY-TEST | Unconditionally returnable (FR-047b) |

**Deliberately absent**: `email`, `phone_numbers`,
`profile_picture`. None of these keys exists on co-host objects
today (CONFIRMED-BY-TEST 2026-08-13). The response chokepoint
(`actions/response.py`) already handles them if they appear in
future: `CO_HOST_CONTACT` gates `email` and `phone_numbers` behind
the guest-contact opt-in, and unknown keys are dropped by the
allowlist. Parsing absent fields into the model would be fabricating
evidence.

**Privacy assessment**: All three fields are non-contact identifiers
of the property operator's own team members, not guest PII. They are
unconditionally returnable per FR-047b. No recorder exclusion or
diagnostics redaction is needed.

### Why `name` is parsed (resolving the precedent tension)

The `api/guest.py` module establishes a "never parse PII at all"
precedent: `profile_picture` is not a `HospitableGuest` field because
it has no permitted exposure surface. The `api/task_model.py` module
follows the same pattern: `teammate.name` is dropped because it has
no permitted surface.

Co-host `name` differs: it IS in `CO_HOST_ALLOWED` in
`actions/response.py` and is explicitly returnable. The precedent
that applies is: "a field with no permitted surface is not modelled."
Co-host `name` has a permitted surface, so it is modelled.

## Modified domain models

### `HospitableListing` (extended)

The existing two-field listing model gains co-hosts:

| Field | Type | Source key | Tier | Notes |
| --- | --- | --- | --- | --- |
| `platform` | `str` | `platform` | Existing | Unchanged |
| `platform_id` | `str` | `platform_id` | Existing | Unchanged |
| `co_hosts` | `tuple[HospitableCoHost, ...]` | `co_hosts` | NEW | Parsed from listing payload |

**Parser change**: `HospitableListing.from_api` reads
`payload.get("co_hosts", [])` and builds `HospitableCoHost` objects
from each dict item, following the same defensive pattern as
`HospitableProperty.from_api` uses for listings.

**Backward compatibility**: The `co_hosts` field has a default of
`()` so that any code constructing `HospitableListing` without it
continues to work. Since this is a frozen dataclass, a default must
use `field(default=())`.

## Modified entities

### `property_info` sensor (attribute addition)

The property information diagnostic sensor gains one attribute:

| Attribute | Type | Unrecorded | Notes |
| --- | --- | --- | --- |
| `property_id` | `str` | No | Opaque UUID, no PII (FR-014) |

The eight existing attributes are unchanged (FR-012). The attribute
tuple `PROPERTY_INFO_ATTRIBUTES` in `sensor/property.py` grows from
eight to nine entries. The docstring is updated from "eight" to
"nine" (FR-013).

This constitutes a formal amendment to the spec 001 property sensor
attribute contract. The spec 001 docstring "Return exactly the eight
property_info contract attributes" is replaced with "Return exactly
the nine property_info contract attributes."

## No new entities

Spec 003 does not introduce new entity types. It modifies one
existing entity's attributes and adds a new service.

## No config entry changes

No new options are added. The `guest_contact_details` option from
spec 002 governs co-host contact field gating in the response
chokepoint; no new option is needed.

## No new coordinators

`list_properties` serves from the existing
`HospitablePropertiesCoordinator` cache. No new coordinator is
introduced.
