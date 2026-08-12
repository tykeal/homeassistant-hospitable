<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract: Home Assistant Services (Actions)

**Feature**: [../spec.md](../spec.md) |
**Data model**: [../data-model.md](../data-model.md)

This document defines the Home Assistant service calls registered by
spec 002. These are the integration's first user-invocable services.

## Registration pattern

Services are registered from `async_setup_entry` via a table-driven
loop (research.md D-02). Registration is idempotent: the first config
entry to load registers all services; subsequent entries skip.
Services are removed when the last config entry unloads.

All service text (names, descriptions, field labels) lives in
`strings.json` and `translations/en.json` (FR-007).

## Response privacy chokepoint (MANDATORY for every service)

Every service response in this document is produced by the single
shared serialiser described in [research.md D-16](../research.md#d-16).
No handler serialises an upstream payload itself. The serialiser
applies an ALLOWLIST, so an upstream key that is not listed is dropped
rather than passed through:

| Guest key | In service response? |
| --- | --- |
| `first_name`, `last_name`, `location`, `language` | Yes |
| `email`, `phone_numbers` | ONLY when the guest-contact-details option (FR-038b) is enabled on the config entry serving the call |
| `profile_picture` | **NEVER, under any option** (FR-047) |
| `id` and any other guest key | Dropped unless added to the allowlist deliberately |

The opaque message `sender` object is stripped unconditionally
(FR-047a); only `sender_type` and `sender_role` survive, because they
are role discriminators rather than identity.

This is required because a privacy control scoped to one surface does
not protect another surface (FR-046). Service responses are visible in
automation traces, template rendering, and debug logs, so they rank
with entity attributes as an exposure surface — the entity-attribute
controls in FR-039c and FR-039d do not reach them.

## Common fields

Every service accepts an optional `config_entry_id` field for
multi-entry disambiguation (FR-008):

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `config_entry_id` | string | No | Auto-selected when exactly one entry exists. Required when multiple entries are loaded. |

Services that target a reservation accept exactly one of:

| Field | Type | Notes |
| --- | --- | --- |
| `entity_id` | string | Entity ID of the reservation_status sensor; UUID read from its `reservation_uuid` attribute |
| `reservation_uuid` | string | Direct UUID of the reservation |

Providing both or neither raises `ServiceValidationError`.

## Service definitions

### `hospitable.send_message`

**Purpose**: Send a text message to a guest for a specific reservation.

**Response mode**: `SupportsResponse.ONLY`

**Fields**:

| Field | Type | Required | Validation | Notes |
| --- | --- | --- | --- | --- |
| `entity_id` | string | One of pair | See above | |
| `reservation_uuid` | string | One of pair | See above | |
| `body` | string | Yes | Non-empty | Message text |
| `images` | list[string] | No | Max 3 items, each a URI | Image attachments (DOCUMENTED: max 5 MB each) |
| `sender_id` | string | No | Must be a valid co-host user_id | Airbnb only; rejected for non-Airbnb reservations |
| `config_entry_id` | string | No | See common fields | |

**Pre-call validation** (before any API request):

1. Exactly one of `entity_id` / `reservation_uuid` provided
2. `body` is non-empty
3. `images` has at most 3 items (if provided)
4. If `sender_id` is provided, the target reservation's `platform`
   must be `airbnb`; otherwise `ServiceValidationError`
5. Rate limit not exceeded (per-reservation: 2/min; per-token: 50/5min)

**API call**: `POST /reservations/{uuid}/messages`

**Request body**:

```json
{
  "body": "<message text>",
  "images": ["<uri1>", "<uri2>"],
  "sender_id": "<co-host user_id if provided>"
}
```

**Response shape** (returned to caller):

```json
{
  "accepted": true,
  "reservation_uuid": "<target UUID>",
  "sent_reference_id": "<from 202 body if present, else null>"
}
```

**Error mapping**:

| Condition | Exception | Notes |
| --- | --- | --- |
| Bad input (empty body, too many images, both/neither target) | `ServiceValidationError` | Client-side, no API call |
| sender_id on non-Airbnb reservation | `ServiceValidationError` | Client-side |
| Rate limit exceeded | `ServiceValidationError` | Client-side; message names which limit and approximate reset |
| HTTP 400 | `ServiceValidationError` | API rejected the request shape |
| HTTP 422 | `ServiceValidationError` | Validation detail from response body |
| HTTP 403 | `HomeAssistantError` | Capability limitation (OQ-005) |
| HTTP 5xx / network | `HomeAssistantError` | Transient API failure |

**Semantic contract**: The service reports "accepted for delivery." It
NEVER claims "sent" or "delivered." HTTP 202 means the API queued the
message; delivery is asynchronous and unconfirmed (FR-011).

---

### `hospitable.get_messages`

**Purpose**: Retrieve the message thread for a reservation.

**Response mode**: `SupportsResponse.ONLY`

**Fields**:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `entity_id` | string | One of pair | |
| `reservation_uuid` | string | One of pair | |
| `config_entry_id` | string | No | |

**API call**: `GET /reservations/{uuid}/messages`

**Pagination**: Defensive (D-07). If `meta`/`links` present, pages
through all results. If absent, treats `data` as complete.

**Response shape**:

```json
{
  "found": true,
  "reservation_uuid": "<target>",
  "messages": [
    {
      "id": 123,
      "body": "<text>",
      "sender_type": "<guest|host|system>",
      "sender_role": "<role or null>",
      "created_at": "<ISO timestamp>",
      "content_type": "<type>",
      "attachments": []
    }
  ]
}
```

**Not-found response** (reservation does not exist or is inaccessible):

```json
{
  "found": false,
  "reservation_uuid": "<target>",
  "messages": []
}
```

**PII rule**: Message bodies are returned to the caller (they are the
purpose of the service) but are NEVER logged at any level (FR-024).
The opaque `sender` object is NOT returned — it may carry guest
identity and contact fields, so the chokepoint strips it and only
`sender_type` and `sender_role` survive (FR-047a).

---

### `hospitable.find_reservation`

**Purpose**: Look up a single reservation by UUID.

**Response mode**: `SupportsResponse.ONLY`

**Fields**:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `reservation_uuid` | string | Yes | Direct UUID |
| `config_entry_id` | string | No | |

**API call**: `GET /reservations/{uuid}?include=guest,properties`

**Response shape** (guest object filtered by the chokepoint above):

```json
{
  "found": true,
  "reservation": {
    "...": "reservation fields",
    "guest": {
      "first_name": "<string or null>",
      "last_name": "<string or null>",
      "location": "<string or null>",
      "language": "<string or null>"
    }
  }
}
```

`email` and `phone_numbers` join the `guest` object only when the
guest-contact-details option is enabled. `profile_picture` never
appears (FR-047).

**Not-found**:

```json
{
  "found": false,
  "reservation": null
}
```

---

### `hospitable.get_reservations`

**Purpose**: List reservations for a property within the configured
window.

**Response mode**: `SupportsResponse.ONLY`

**Fields**:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `property_id` | string | Yes | |
| `config_entry_id` | string | No | |

**API call**: `GET /reservations?properties[]={id}&start_date=...&end_date=...&include=guest,properties`

**Response shape**:

```json
{
  "found": true,
  "property_id": "<target>",
  "reservations": [ /* array; each guest object filtered per FR-047 */ ]
}
```

---

### `hospitable.get_property_info`

**Purpose**: Retrieve property details including listings and co-hosts.

**Response mode**: `SupportsResponse.ONLY`

**Fields**:

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `property_id` | string | Yes | |
| `config_entry_id` | string | No | |

**API call**: `GET /properties?include=listings` (filtered to the
target property from coordinator cache, or single-property fetch if
not cached)

**Response shape**:

```json
{
  "found": true,
  "property": {
    "id": "<id>",
    "name": "<name>",
    "listings": [ /* with co_hosts */ ]
  }
}
```

## Error contract (all services)

| Category | Exception type | When |
| --- | --- | --- |
| User-correctable input | `ServiceValidationError` | Bad field values, missing required fields, rate limit, disambiguation |
| API failure | `HomeAssistantError` | Network error, 5xx, 403 capability limitation |
| Not-found | Return value | `{"found": false, ...}` — NEVER an exception |

This matches the Hostaway pattern and FR-028/FR-045.
