<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Phase 0 Research: Property Discovery

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

**Date**: 2026-08-13

## Purpose

This document records decisions taken before design, reasoning, and
rejected alternatives for spec 003. It uses the same evidence legend
as the specification.

## Decision index

| ID | Decision | Governing requirements |
| --- | --- | --- |
| D-01 | Co-host data retained at parse time, gated at chokepoint | FR-006, FR-007, FR-021, FR-047b |
| D-02 | `list_properties` served entirely from coordinator cache | FR-009, FR-008 |
| D-03 | `list_properties` in `actions/list_properties.py` | FR-003, FR-023 |
| D-04 | Shared `resolve_property_id` helper for target conflict | FR-017, FR-019 |
| D-05 | `property_id` as ninth property sensor attribute | FR-011, FR-012, FR-013 |
| D-06 | HA service `target` definition for entity/device picker | FR-015, FR-024 |
| D-07 | Cross-entry device target rejection | FR-020, FR-022 |
| D-08 | Red-phase strategy for Principle XII compliance | Constitution XII |

## D-01: Co-host data retained at parse, gated at chokepoint {#d-01}

**Decision**: Extend `HospitableListing` with a `co_hosts` field of
type `tuple[HospitableCoHost, ...]`. Introduce a new frozen dataclass
`HospitableCoHost` with fields `user_id`, `channel_name`, and `name`
— ALL three are unconditionally returnable per FR-047b. Parse ALL
three at the model layer.

Do NOT parse `email`, `phone_numbers`, or any other co-host key at
the model layer. The live evidence (2026-08-13) shows co-host objects
carry exactly `{channel_name, name, user_id}` — no `email`,
`phone_numbers`, or `profile_picture` key exists today. FR-007
specifies that `email` and `phone_numbers` are released from the
response chokepoint when the guest-contact opt-in is enabled, which
means the chokepoint must be able to filter them IF they appear in
future. The chokepoint already handles this: `CO_HOST_CONTACT` in
`actions/response.py` gates `email` and `phone_numbers` behind
`guest_contact`, and unknown keys are dropped fail-closed by the
allowlist. So the chokepoint is already correct for a future where
the API adds those keys.

**Why parse the three fields into the model rather than keeping raw
dicts**: The model layer elsewhere (`HospitableGuest` in
`api/guest.py`) establishes a "never parse PII at all" precedent —
`profile_picture` is not a field on `HospitableGuest` BECAUSE it has
no permitted exposure surface.

The tension here: co-host `name` IS returnable per FR-047b, unlike
`profile_picture`. `teammate.name` in `api/task_model.py` was dropped
because it had no permitted surface. Co-host `name` has an explicit
surface (it is in `CO_HOST_ALLOWED`). Therefore the guest.py
precedent does not apply — the co-host fields are all surfaceable,
so parsing them is correct.

**Why gating happens at the chokepoint, not the parser**: The opt-in
is per-config-entry. The parsed model is shared across the
integration (coordinator cache). If gating happened at the parser,
the model would need to know which config entry's options apply,
which breaks the shared-cache design. The chokepoint receives the
config entry context at call time and applies the correct filter.
This is exactly how guest PII works: `HospitableGuest` parses
`email` and `phone_numbers` into the model; the chokepoint gates
them per-entry.

**Where the new dataclass lives**: In `api/models.py`. The
`HospitableListing.from_api` method gains co-host parsing.
`api/models.py` is currently 439 lines — already at the aislop
threshold (~440 effective). Adding ~20 lines pushes it to ~459,
which is OVER the limit. The plan records this as Deviation 1 and
the implementation stage must resolve it (extract, trim, or
consolidate).

**Alternatives considered**:

- *Keep raw dicts on the listing, filter at the chokepoint only*:
  Rejected. Untyped dicts bypass mypy and make it impossible to
  assert shape in tests without re-parsing.
- *Parse co-hosts in a separate `api/co_host.py` module*: Rejected
  as over-engineering. The dataclass is three fields.
- *Drop `name` at the parser like `teammate.name`*: Rejected. The
  precedents differ — `teammate.name` has no permitted surface;
  co-host `name` is explicitly in `CO_HOST_ALLOWED`.

## D-02: `list_properties` served from coordinator cache {#d-02}

**Decision**: The `list_properties` handler reads directly from the
properties coordinator's cache (`entry.runtime_data["coordinators"]
["properties"]`). It does NOT issue any API request.

**Implementation**: For each config entry in scope:

1. Read `coordinators["properties"].data` — a
   `dict[str, HospitableProperty]` keyed by property_id.
2. Read `known_property_ids` and `selected_property_ids` from
   `entry.runtime_data`.
3. For each property_id in `known_property_ids`, build the curated
   response shape. If the property_id is in the coordinator data,
   use its model fields. If NOT (deselected property with no cached
   data), return the property_id with `name: null`,
   `public_name: null`, `selected: false`, `listings: []`.

**The co-host problem**: The coordinator cache holds
`HospitableProperty` objects whose `listings` contain
`HospitableListing` objects. After D-01, those listings carry
`co_hosts`. So the cache already has everything `list_properties`
needs. No API call is required.

**Rationale**: FR-009 is explicit. The account has a real request
budget.

## D-03: `list_properties` module placement {#d-03}

**Decision**: `actions/list_properties.py` with handler
`async_handle_list_properties`. Registered in the `SERVICE_DEFINITIONS`
table in `actions/__init__.py` as the sixth entry.

**Schema**: One optional field `config_entry_id` (same pattern as
the existing five). No `property_id`, no target — FR-004 is
explicit about the signature.

**Response mode**: `SupportsResponse.ONLY` — consistent with all
five existing services (spec 002 D-14).

**Registration lifecycle**: Same as the existing five — registered on
first entry setup, removed on last entry teardown. No change to the
registration pattern (FR-003).

**Service text**: Added to `strings.json`, `translations/en.json`,
and `services.yaml` (FR-023).

## D-04: Shared `resolve_property_id` for target conflict {#d-04}

**Decision**: Add `resolve_property_id` to `actions/helpers.py`. It
follows the same pattern as `resolve_reservation_uuid` but resolves
property IDs from targets:

```python
def resolve_property_id(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    property_id: str | None,
    target: dict[str, Any] | None,
) -> str:
```

The function:

1. If `target` is supplied, resolves device(s) → property_id via
   `parse_device_identifier` from entity.py. For entity targets,
   looks up the entity's device first.
2. If `property_id` is supplied, uses it directly.
3. If BOTH yield a property ID and they DIFFER →
   `ServiceValidationError` per FR-017.
4. If BOTH yield the SAME property ID → proceeds.
5. If NEITHER yields a property ID →
   `ServiceValidationError` per FR-018.

**Both `get_reservations` and `get_property_info` call this ONE
function** rather than each implementing its own conflict logic.
This is the FR-019 requirement: one resolution path, two consumers.

**Cross-entry check (FR-020)**: When the target resolves a device,
the function checks that the device's config_entry_id matches the
entry resolved by `resolve_config_entry`. A mismatch raises
`ServiceValidationError`.

**Integration domain check**: If the device has no identifier tuple
where the domain is `hospitable`, the function raises
`ServiceValidationError` — the target is not a Hospitable device.

## D-05: `property_id` as ninth attribute {#d-05}

**Decision**: Add `"property_id"` to `PROPERTY_INFO_ATTRIBUTES` tuple
in `sensor/property.py` and return `self._property_id` in
`extra_state_attributes`. Update the docstring from "eight" to "nine".

**Spec 001 requirement being amended**: The property sensor attribute
contract established in spec 001's `contracts/entities.md`. The
docstring on `extra_state_attributes` (line 219 of
`sensor/property.py`) says "Return exactly the eight property_info
contract attributes." FR-013 amends this to nine.

**Tests that assert the count of eight**:

- `tests/sensor/test_property_info.py` line 35:
  `EXPECTED_ATTRIBUTES = set(PROPERTY_INFO_ATTRIBUTES)` — this
  derives from the tuple, so it auto-updates.
- `tests/sensor/test_property_info.py` line 139: docstring says
  "exposing eight attributes" — needs text update.
- The test at line 139 asserts on the SET derived from the tuple,
  so as long as `PROPERTY_INFO_ATTRIBUTES` is updated, the set
  assertion passes. The docstring is the only hard-coded "eight".

**Privacy assessment (FR-014)**: `property_id` is an opaque,
account-scoped UUID. It contains no personal data and implicates
no privacy control. It may be freely recorded, displayed, and logged.

## D-06: HA service `target` definition for entity/device picker {#d-06}

**Decision**: Express the target on `get_reservations` and
`get_property_info` using Home Assistant's service schema `target`
definition in `services.yaml`. This renders the standard entity/device
picker in the UI.

The `target` is defined with:

```yaml
target:
  entity:
    integration: hospitable
  device:
    integration: hospitable
```

The existing `property_id` field remains as a `vol.Optional` field in
the Voluptuous schema (FR-016). The `target` is passed through the
`ServiceCall` object, not through the Voluptuous schema — HA handles
target parsing separately.

**Schema changes**: `GET_RESERVATIONS_SCHEMA` and
`GET_PROPERTY_INFO_SCHEMA` change `property_id` from `vol.Required`
to `vol.Optional`. The exactly-one-or-conflict rule is enforced in
`resolve_property_id` (D-04), not in the schema.

## D-07: Cross-entry device target rejection {#d-07}

**Decision**: When a device target resolves to a device that belongs
to config entry B, but the call is scoped to config entry A (either
explicitly via `config_entry_id` or by auto-selection), the call
raises `ServiceValidationError`.

**Detection**: The device registry entry carries `config_entry_id`.
Compare it against the `entry.entry_id` from `resolve_config_entry`.

**Same pattern as reservation resolution**: `resolve_reservation_uuid`
already does this for entity targets — it checks
`registry_entry.config_entry_id != entry.entry_id`. The property
resolver mirrors this check on the device level.

## D-08: Red-phase strategy for Principle XII {#d-08}

**Decision**: Concrete red-phase plan for each deliverable.

### Deliverable A — `list_properties`

**Tests that can be genuinely red with `AssertionError`**:

- Test that `list_properties` is a registered service → red-phase
  imports `actions/__init__.py` and checks the `SERVICE_DEFINITIONS`
  tuple for a "list_properties" entry. Fails with `AssertionError`
  because the entry does not exist yet.
- Test that calling `list_properties` returns the curated shape →
  red-phase calls the service and asserts on the response keys.
  Fails with `AssertionError` (service not registered, or wrong
  response shape).

**Tests that fail with `ImportError`**:

- Test that `HospitableCoHost` exists as a frozen dataclass → imports
  from `api.models`, fails with `ImportError` because the class
  does not exist.
- Test that `list_properties` handler exists → imports from
  `actions.list_properties`, fails with `ImportError`.

Both are valid Principle XII red phases: `ImportError` is the
expected failure because the module/class genuinely does not exist
yet, and each test pins `raises=ImportError`.

### Deliverable B — `property_id` attribute

**Tests that can be genuinely red with `AssertionError`**:

- Test that `PROPERTY_INFO_ATTRIBUTES` contains `"property_id"` →
  imports the tuple and asserts membership. Fails with
  `AssertionError` because the tuple currently has eight elements.
- Test that the property sensor's `extra_state_attributes` includes
  `property_id` → sets up a sensor and asserts on attributes. Fails
  with `AssertionError` because the attribute is not returned.

These are clean red phases: the code exists, the tests run fully,
and the failure is `AssertionError` — the behavior is wrong, not
missing.

### Deliverable C — entity/device targeting

**Tests that fail with `ImportError`**:

- Test that `resolve_property_id` exists → imports from
  `actions.helpers`, fails with `ImportError` (the name does not
  exist yet; actually `ImportError` for a missing name from an
  existing module is re-coded to `raises=ImportError` when the
  function is added to an existing module — but the actual error
  is an `ImportError` on a `from ... import resolve_property_id`).

**Correction**: importing a non-existent name from an existing module
raises `ImportError` in Python 3.14 (it's the same exception type
for both missing modules and missing names in `from X import Y`).
So `raises=ImportError` is correct.

**Tests that can be genuinely red with `AssertionError`**:

- Test that `get_reservations` accepts a target and resolves the
  property → calls the service with a target, asserts on success.
  Fails with `AssertionError` or `ServiceValidationError` because
  the schema still requires `property_id`.
- Test that conflicting target and property_id raises
  `ServiceValidationError` → fails with `AssertionError` because
  the conflict check does not exist.

### Characterization tests that ship green

- Write-isolation tests (`test_no_writes.py`,
  `test_write_isolation.py`, `test_isolation_discovery.py`) — these
  are existing tests that MUST STAY green. They are not red-phase
  tests for spec 003; they are regression gates.
- The existing `test_property_info.py` test at line 139 — after
  updating `PROPERTY_INFO_ATTRIBUTES`, this test auto-passes. It
  legitimately ships green because it tests the UPDATED contract.

## Assumptions

| ID | Assumption | Tier | Fallback |
| --- | --- | --- | --- |
| A-01 | Co-host objects carry exactly `{channel_name, name, user_id}` | CONFIRMED-BY-TEST (2026-08-13) | Allowlist drops unknown keys |
| A-02 | No `email`/`phone_numbers`/`profile_picture` on co-host objects today | CONFIRMED-BY-TEST (2026-08-13) | Chokepoint gates them if they appear |
| A-03 | Properties coordinator cache is populated before `list_properties` can be called | Design invariant | Handler returns empty list if cache is None |
| A-04 | Device identifier format is stable: `(DOMAIN, f"{namespace}_{property_id}")` | Code invariant (entity.py) | `parse_device_identifier` is the single source |
