<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Feature Specification: Property Discovery

**Feature Branch**: `003-property-discovery`

**Created**: 2026-08-13

**Status**: Draft

**Input**: User description: "Property discovery — a list_properties
action, property_id exposure on the property sensor, and entity/device
targeting on property-scoped actions, so that identifiers required by
existing actions are discoverable without guessing."

## Overview

Spec 002 delivered five actions. Two of them — `get_reservations` and
`get_property_info` — require the caller to supply a `property_id`.
There is no documented or reasonable way for a user to obtain one.

The defect is best stated by the integration's own description of
`get_property_info` in `strings.json`:

> "Returns a property's details together with its sales channels and
> their co-hosts, **so the identifiers other actions need can be
> discovered.**"

This is circular: the action whose purpose is to let you discover
identifiers requires you to already possess the identifier it claims
to help you find.

This specification closes the discovery gap through three coordinated
changes:

- **A** — A new `list_properties` action that returns every known
  property with curated metadata including co-host user IDs.
- **B** — Exposing `property_id` as an entity attribute on the
  property sensor, providing a UI-visible path to the identifier.
- **C** — Accepting entity and/or device targets on `get_reservations`
  and `get_property_info`, so a property can be selected from a picker
  rather than typed as a raw UUID.

All three changes are strictly read-only. No write is introduced.

### Evidence confidence legend

| Marker | Meaning |
| --- | --- |
| **CONFIRMED-BY-TEST** | Verified empirically against a live Hospitable account (read-only probes only). |
| **CONFIRMED-BY-SPEC** | Read directly from Hospitable's OpenAPI export, not confirmed by a live grant. |
| **DOCUMENTED** | Stated in Hospitable's official documentation, not verified empirically. |
| **UNVERIFIED** | Single-source, undocumented, or inferred. Must not be relied upon without a test. |

### Live evidence (2026-08-13)

`GET /properties?include=listings&per_page=100` returned HTTP 200 with
13 properties. Each property carries 23 top-level keys:

`address`, `amenities`, `calendar_restricted`, `capacity`, `checkin`,
`checkout`, `currency`, `description`, `house_rules`, `ical_imports`,
`id`, `listed`, `listings`, `name`, `parent_child`, `picture`,
`property_type`, `public_name`, `room_details`, `room_type`,
`summary`, `tags`, `timezone`.

One property carries 5 listings. `amenities` is a 53-element list;
`room_details` a 9-element list. Eight populated co-host entries
account-wide, each with exactly `{channel_name, name, user_id}`, all
string-valued. No `email`, `phone_numbers`, or `profile_picture` key
exists on a co-host object today. (CONFIRMED-BY-TEST)

### Asymmetry in current action interfaces

| Action | Target mechanism |
| --- | --- |
| `send_message` | Entity selector (reservation entity) |
| `get_messages` | Entity selector (reservation entity) |
| `find_reservation` | Entity selector (property entity) |
| `get_reservations` | Raw `property_id` text field |
| `get_property_info` | Raw `property_id` text field |

After this specification, the last two will accept entity and device
targets IN ADDITION to the existing `property_id` field.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Discover property identifiers (Priority: P1)

As a property manager setting up automations, I want to call a single
action that lists all my properties with their IDs and co-host
user IDs, so that I can configure `get_reservations`,
`get_property_info`, and `send_message` (sender_id) without inspecting
device registry internals.

**Why this priority**: This is the primary ask. Without it, none of
the property-scoped actions are usable without undocumented hackery.

**Independent Test**: Invoke `list_properties` with no arguments (or a
`config_entry_id` in a multi-account setup). Confirm the response
contains all 13 known properties with curated fields per property.

**Acceptance Scenarios**:

1. **Given** a single configured account with 13 properties,
   **When** the user invokes `list_properties` without arguments,
   **Then** the response contains exactly 13 entries, each with
   `property_id`, `name`, `public_name`, `selected`, and `listings`.
2. **Given** properties that are known but NOT selected for polling,
   **When** the user invokes `list_properties`,
   **Then** unselected properties appear with `selected: false`.
3. **Given** a property with 5 listings each carrying co-hosts,
   **When** the user invokes `list_properties`,
   **Then** each listing includes `platform`, `platform_id`, and a
   `co_hosts` array with `user_id`, `channel_name`, and `name` per
   entry.
4. **Given** multiple configured accounts,
   **When** the user invokes `list_properties` with a specific
   `config_entry_id`,
   **Then** only properties from that account are returned.

---

### User Story 2 — See property_id in entity attributes (Priority: P2)

As a property manager, I want the property sensor's state attributes
to include the property's identifier, so I can read it from the
Developer Tools or use it in templates without calling an action.

**Why this priority**: Provides a passive discovery route that
requires no action call. Lower priority than US1 because it solves
only part of the problem (no co-host IDs, no listing details).

**Independent Test**: Open Developer Tools → States, find a property
sensor. Confirm `property_id` appears among its attributes.

**Acceptance Scenarios**:

1. **Given** a property sensor entity,
   **When** a user inspects its state attributes,
   **Then** a `property_id` attribute is present containing the
   Hospitable property UUID.
2. **Given** the existing eight contract attributes,
   **When** the property sensor loads,
   **Then** all eight remain present and unchanged; `property_id` is
   additive.

---

### User Story 3 — Target property actions by entity/device (Priority: P3)

As a property manager building automations, I want `get_reservations`
and `get_property_info` to accept an entity or device target (like a
property sensor entity_id), so I can use the UI picker rather than
pasting a UUID I had to discover elsewhere.

**Why this priority**: Completes the UX parity with the three
reservation-scoped actions. Lower than US1/US2 because those actions
already work if you possess the ID.

**Independent Test**: Call `get_reservations` with `target:
entity_id: sensor.hospitable_my_property_status` and no `property_id`
field. Confirm the property is resolved and reservations are returned.

**Acceptance Scenarios**:

1. **Given** a property device with device ID `D`,
   **When** the user calls `get_property_info` with `target:
   device_id: [D]` and no `property_id`,
   **Then** the property ID is extracted from the device registry
   identifier and the action succeeds.
2. **Given** a property sensor entity,
   **When** the user calls `get_reservations` with `target:
   entity_id: [entity]` and no `property_id`,
   **Then** the property ID is resolved from the entity's device.
3. **Given** a call supplying BOTH a target AND a `property_id`,
   **When** the action executes,
   **Then** the explicit `property_id` field takes precedence and the
   target is ignored.
4. **Given** a call supplying NEITHER a target NOR a `property_id`,
   **When** the action executes,
   **Then** the integration raises a `ServiceValidationError`
   explaining that one targeting method is required.
5. **Given** existing automations that supply `property_id` directly,
   **When** the integration is upgraded,
   **Then** those automations continue to function without change.

---

### Edge Cases

- What happens when `list_properties` is called with an invalid
  `config_entry_id`? → A `ServiceValidationError` naming the invalid
  entry.
- What happens when a device target resolves to a device belonging to
  a different integration? → The action raises a validation error.
- What happens when a property is known but has no listings? →
  `listings` is an empty array; the property still appears.
- What happens when the coordinator cache has not yet completed its
  first refresh? → `list_properties` returns whatever data the
  coordinator currently holds (potentially empty); it does NOT issue
  a fresh API call.

## Requirements *(mandatory)*

### Write-isolation preservation

- **FR-001**: This feature is entirely read-only. No write request
  (POST, PUT, PATCH, DELETE) may be introduced by any requirement in
  this specification.
- **FR-002**: The existing `test_no_writes.py`,
  `test_write_isolation.py`, and `test_isolation_discovery.py` test
  suites MUST continue to pass without modification of their
  assertions. If the implementation adds new code paths they must be
  exercised under the existing write-isolation harness.

### A — `list_properties` action

- **FR-003**: The integration MUST expose a `list_properties` action
  registered via `async_setup_services` following the same lifecycle
  as the existing five actions (registered on first entry setup,
  removed on last entry teardown).
- **FR-004**: `list_properties` MUST accept one optional field:
  `config_entry_id` (config entry selector, `integration:
  hospitable`). When omitted, all loaded config entries are
  enumerated. When supplied, only properties from that entry are
  returned.
- **FR-005**: The response MUST be a dictionary with a single key
  `properties` containing a list. Each element represents one
  property and MUST include exactly these fields:
  - `property_id` — the Hospitable property UUID (string).
  - `name` — the property's internal name (string).
  - `public_name` — the property's guest-facing name (string).
  - `selected` — boolean, `true` when the property is in the
    `selected_property_ids` set for the config entry; `false`
    otherwise.
  - `listings` — a list of listing objects (may be empty).
- **FR-006**: Each listing object MUST include exactly:
  - `platform` — the listing platform name (string).
  - `platform_id` — the platform-specific listing identifier (string).
  - `co_hosts` — a list of co-host objects (may be empty).
- **FR-007**: Each co-host object MUST be processed through the
  existing response-privacy chokepoint governed by spec 002 FR-047b.
  The resulting shape is:
  - `user_id` — unconditionally returnable (string).
  - `channel_name` — unconditionally returnable (string).
  - `name` — unconditionally returnable (string).
  - `email`, `phone_numbers` — released only when the
    `guest_contact_details` option is enabled for the config entry
    serving the call.
  - Any key not in the FR-047b allowlist MUST be omitted fail-closed.
- **FR-008**: `list_properties` MUST enumerate ALL entries in
  `known_property_ids`, which is a superset of
  `selected_property_ids`. Properties the user has not selected for
  polling MUST still appear (with `selected: false`). The purpose of
  the action is discovery — omitting unselected properties would
  defeat it.
- **FR-009**: `list_properties` MUST serve from the properties
  coordinator cache. It MUST NOT issue an additional API request.
  **Rationale**: The account has a real request budget. The
  coordinator already polls the properties list; a discovery action
  should not double the load. The cache reflects the most recent poll
  and is sufficient for identifier lookup. Freshness is bounded by
  the properties coordinator's polling interval, which is acceptable
  for a discovery-oriented action where identifiers and names change
  rarely.
- **FR-010**: The response MUST be a curated shape, NOT a raw
  property dump. Of the 23 keys present on each raw property object,
  only the five enumerated in FR-005 plus the listing substructure
  (FR-006, FR-007) are returned. All other keys — including
  `address`, `amenities`, `description`, `house_rules`,
  `room_details`, `capacity`, and `picture` — MUST be omitted. This
  bounds the response size and minimises the data-exposure surface.

### B — `property_id` as entity attribute

- **FR-011**: The property sensor's `extra_state_attributes` MUST
  include a `property_id` key containing the Hospitable property UUID
  string.
- **FR-012**: The existing eight contract attributes (`address`,
  `checkin_time`, `checkout_time`, `max_guests`,
  `effective_timezone`, `timezone_source`, `listings`,
  `listings_available`) MUST remain present and unchanged.
  `property_id` is purely additive.
- **FR-013**: This requirement constitutes a formal amendment to the
  spec 001 property sensor attribute contract. Spec 001 established
  the docstring "Return exactly the eight property_info contract
  attributes" and defined the closed attribute set. This
  specification widens it to nine attributes. The docstring MUST be
  updated to reflect the new count.
- **FR-014**: The `property_id` attribute is an opaque,
  account-scoped identifier. It contains no personal data and
  implicates no privacy control. It may be freely recorded by the
  Home Assistant recorder, displayed in the UI, and logged. This
  assessment is recorded explicitly so that future reviewers need not
  re-evaluate it.

### C — Entity/device targeting on property-scoped actions

- **FR-015**: `get_reservations` and `get_property_info` MUST accept
  an optional `target` field supporting both entity and device
  selectors. The target MUST resolve to a property device from which
  the property ID is extracted via `parse_device_identifier`.
- **FR-016**: The existing `property_id` text field MUST remain
  accepted on both actions. Existing automations MUST NOT break.
- **FR-017**: Precedence rule when multiple targeting fields are
  supplied: **explicit `property_id` wins**. If the caller provides
  both a `property_id` text value and a target (entity or device),
  the `property_id` field is used and the target is silently ignored.
  This guarantees backwards compatibility: an automation that already
  supplies `property_id` continues to behave identically regardless
  of whether a UI-added target accompanies it.
- **FR-018**: When NEITHER `property_id` NOR a resolvable target is
  supplied, the action MUST raise a `ServiceValidationError` with a
  message explaining that at least one targeting method is required.
  The error MUST NOT expose internal identifiers.
- **FR-019**: Target resolution MUST follow the same resolution
  pattern used by the reservation-scoped actions
  (`resolve_config_entry` and `resolve_reservation_uuid` in
  `actions/helpers.py`). The implementation MUST produce a
  `resolve_property_id` helper (or equivalent) that:
  1. Checks for an explicit `property_id` field — returns it if
     present.
  2. Falls back to the target — resolves entity → device → device
     identifier → `parse_device_identifier`.
  3. Raises `ServiceValidationError` if neither path yields a
     property ID.
- **FR-020**: A target that resolves to a device not belonging to the
  `hospitable` domain, or belonging to a different config entry than
  the one resolved for the call, MUST raise a
  `ServiceValidationError` explaining the mismatch.

### Constraints and dependencies

- **FR-021**: `HospitableListing` in `api/models.py` currently
  retains only `platform` and `platform_id`; it discards `co_hosts`
  at parse time. Delivering the co-host data required by FR-006 and
  FR-007 therefore requires extending this model. The raw data IS
  already fetched (the client requests `include=listings` and
  verifies arrival via `assert_include`); it is discarded during
  parsing, not un-fetched. This is a known implementation dependency;
  the model extension is part of this feature's scope.
- **FR-022**: Multi-account isolation MUST be maintained.
  `list_properties` iterates over config entries; `parse_device_
  identifier` already validates the `account_namespace` component.
  A property or device from account A MUST NOT be resolvable in a
  call scoped to account B.

### Service registration and UX

- **FR-023**: `list_properties` MUST be documented in `services.yaml`
  and `strings.json` following the conventions established by the
  existing five actions.
- **FR-024**: The `target` field on `get_reservations` and
  `get_property_info` MUST be expressed as a service `target`
  definition (Home Assistant service schema) with `entity` and
  `device` domains, so that the UI renders a standard picker.
  `property_id` remains a field (not a target) for backwards
  compatibility.

## Key Entities

- **Property**: Identified by `property_id` (UUID string, account-
  scoped). Contains `name`, `public_name`, polling-selection flag.
  Owns zero or more Listings.
- **Listing**: Identified by `platform` + `platform_id`. Belongs to
  one Property. Owns zero or more Co-hosts.
- **Co-host**: Identified by `user_id` (string, account-scoped).
  Carries `channel_name` and `name`. Subject to FR-047b privacy
  gating.
- **Property device**: The HA device registry entry whose identifier
  is built by `build_device_identifier(account_namespace,
  property_id)`. Target resolution (FR-019) extracts the property_id
  from this tuple.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can discover every property identifier in the
  account by invoking a single action (`list_properties`) and
  receiving a complete list within the normal action response time.
- **SC-002**: A user can resolve a co-host `user_id` for use in
  `send_message`'s `sender_id` field in ONE action call
  (`list_properties`) rather than requiring a separate call per
  property.
- **SC-003**: The property sensor displays `property_id` in its
  state attributes, visible in Developer Tools without any action
  invocation.
- **SC-004**: `get_reservations` and `get_property_info` can be
  invoked using the standard Home Assistant entity/device picker,
  eliminating the need to paste raw UUIDs.
- **SC-005**: All 564 existing tests continue to pass with no
  modification to write-isolation assertions.
- **SC-006**: Existing automations that supply `property_id` directly
  to `get_reservations` or `get_property_info` continue to function
  without change after upgrade.

## Assumptions

- The Hospitable API will continue to return co-host data as part of
  the listings include on the properties endpoint. If this changes,
  the co-host portion of `list_properties` degrades gracefully to
  empty arrays.
- The coordinator polling interval for properties (currently longer
  than reservations, per constitution Principle II guidelines) provides
  acceptable staleness for a discovery-oriented action. Property names
  and identifiers change extremely rarely.
- The nine-attribute contract (FR-012, FR-013) will not require a
  Home Assistant state-change event for existing entities beyond the
  normal attribute update on next poll — HA handles attribute
  additions transparently.
- Device registry identifiers are stable across restarts (they are
  the HA-standard persistent device identity mechanism).

## Open Questions

- **OQ-001 — Cache freshness notification.** Should `list_properties`
  include a timestamp indicating when the coordinator last
  successfully refreshed? This would let a caller judge staleness.
  Deferred to planning as it does not affect the requirement set —
  it is purely additive and can be included or excluded without
  changing any FR.
- **OQ-002 — Target on `list_properties` itself.** Should
  `list_properties` accept a device target to filter to a single
  property? This would be unusual (it defeats the "list" purpose) and
  is omitted from this specification. If needed, it can be added in a
  future amendment.

## Out of Scope

- **Extending the raw property payload.** The action returns a curated
  subset. Full property details remain available via
  `get_property_info` once the ID is known.
- **Listing management.** No create/update/delete of listings.
- **Co-host management.** No invite/remove of co-hosts.
- **Write operations of any kind.** This feature is read-only.
- **Webhooks.** Deferred to a future specification.
- **OAuth.** Deferred as in spec 001.
- **Property creation or configuration changes.** Out of scope.
- **Changes to reservation-scoped action targeting.** Those already
  have entity selectors and are not modified here.

## Cross-specification references

- **Spec 001** — Property sensor attribute contract (amended by
  FR-013).
- **Spec 002 FR-047b** — Co-host privacy allowlist (governs FR-007).
- **Spec 002 FR-048** — Response-privacy chokepoint (applies to
  `list_properties` response building).
- **Spec 002 FR-005, FR-006** — Service registration lifecycle
  (FR-003 follows the same pattern).
- **Spec 002 FR-008** — Multi-entry disambiguation pattern (FR-004
  follows the same pattern).
