<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract: Home Assistant Services (Spec 003 Additions)

**Feature**: [../spec.md](../spec.md) |
**Data model**: [../data-model.md](../data-model.md)

This document defines the new service and the modifications to existing
services introduced by spec 003. Spec 002's
[services.md](../../002-actions-and-messaging/contracts/services.md)
remains authoritative for the base service surface.

## Response privacy chokepoint (unchanged)

All service responses — including the new `list_properties` and the
modified `get_reservations` and `get_property_info` — continue to be
built by the single shared serialiser in `actions/response.py`
(spec 002 D-16). Co-host objects are filtered through
`CO_HOST_ALLOWED` / `CO_HOST_CONTACT` per FR-047b. No second
filtering path is introduced (FR-048).

## New service

### `hospitable.list_properties`

**Purpose**: Return every known property for the account(s) with
curated metadata including listing co-host identifiers.

**Response mode**: `SupportsResponse.ONLY`

**Fields**:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `config_entry_id` | string | No | Auto-selected when one entry; required when multiple |

**No target**: This service does not accept entity or device targets.
It lists ALL known properties; filtering to one would defeat the
discovery purpose (spec OQ-002).

**API call**: NONE. Served entirely from the properties coordinator
cache (FR-009).

**Response shape**:

```json
{
  "properties": [
    {
      "property_id": "<UUID>",
      "name": "<internal name>",
      "public_name": "<guest-facing name or null>",
      "selected": true,
      "listings": [
        {
          "platform": "<platform name>",
          "platform_id": "<platform listing id>",
          "co_hosts": [
            {
              "user_id": "<co-host user id>",
              "channel_name": "<channel name>",
              "name": "<co-host name>"
            }
          ]
        }
      ]
    }
  ]
}
```

**Co-host privacy gating**: Each co-host object passes through the
response chokepoint. Per FR-047b:

| Co-host key | In response? |
| --- | --- |
| `user_id`, `channel_name`, `name` | Always |
| `email`, `phone_numbers` | Only with `guest_contact_details` on |
| Any other key | Dropped (allowlist fail-closed) |

Today co-host objects carry only the three unconditional keys
(CONFIRMED-BY-TEST). The chokepoint is forward-compatible.

**Error mapping**:

| Condition | Exception | Notes |
| --- | --- | --- |
| Invalid `config_entry_id` | `ServiceValidationError` | Entry not loaded or unknown |
| Ambiguous multi-entry | `ServiceValidationError` | `config_entry_id` required |
| No entries loaded | `ServiceValidationError` | Integration not set up |

**Not-found is not applicable**: The service lists whatever the cache
holds, which may be empty. An empty list is a valid response, not an
error (spec edge case: cache not yet refreshed).

## Modified services

### `hospitable.get_reservations` (MODIFIED)

**Changes from spec 002**:

1. `property_id` changes from REQUIRED to OPTIONAL.
2. A `target` definition is added supporting entity and device
   selectors.
3. Resolution uses the shared `resolve_property_id` helper (D-04).

**Target definition** (in `services.yaml`):

```yaml
target:
  entity:
    integration: hospitable
  device:
    integration: hospitable
```

**Updated fields**:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `property_id` | string | No | Direct property UUID (FR-016) |
| `config_entry_id` | string | No | Multi-entry disambiguation |
| (target) | entity/device | No | HA standard picker (FR-024) |

**Resolution rules** (FR-017, FR-018, FR-019):

| `property_id` | Target | Result |
| --- | --- | --- |
| Supplied | Not supplied | Use `property_id` |
| Not supplied | Supplied | Resolve property from target |
| Supplied | Supplied, same property | Proceed |
| Supplied | Supplied, different property | `ServiceValidationError` |
| Not supplied | Not supplied | `ServiceValidationError` |

**Direct-ID path preserved**: Callers that supply `property_id` directly
continue to work unchanged (FR-016, SC-006).

### `hospitable.get_property_info` (MODIFIED)

Identical changes to `get_reservations` above. Same target definition,
same resolution rules, same direct-ID preservation.

## Error contract (unchanged)

The error taxonomy from spec 002 applies to all services including the
new and modified ones. `ServiceValidationError` for user-correctable
input; `HomeAssistantError` for API failures; return values for
not-found.
