<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract: Home Assistant Services (Spec 004 Amendments)

**Feature**: [../spec.md](../spec.md) |
**Data model**: [../data-model.md](../data-model.md)

This document defines the modifications to existing services
introduced by spec 004.

## Modified service

### `hospitable.get_reservations` (MODIFIED)

**Changes from spec 003**:

1. Two optional integer fields added: `lookforward_days` and
   `lookbackward_days`.
2. Docstring rewritten to describe the real default relationship
   between the action window and the sensor window.

**Updated fields**:

| Field | Type | Required | Range | Default | Notes |
| --- | --- | --- | --- | --- | --- |
| `property_id` | string | No | — | — | Unchanged (spec 003) |
| `config_entry_id` | string | No | — | — | Unchanged |
| (target) | entity/device | No | — | — | Unchanged (spec 003) |
| `lookforward_days` | int | No | 1–1095 | Config `lookahead_days` (default 90) | **NEW** FR-023 |
| `lookbackward_days` | int | No | 0–365 | 7 (fixed) | **NEW** FR-023 |

**Default asymmetry (deliberate)**:

- `lookforward_days` default inherits the config entry's
  `lookahead_days` option value (FR-024). This mirrors the sensor
  window by default.
- `lookbackward_days` default is a fixed 7 days, NOT the config
  entry's `lookback_days` (FR-025). The action is a lookup tool
  for messaging; stale bookings rarely matter.

This asymmetry is a deliberate design choice documented in the
spec (FR-025). Do not "correct" it.

**Range justification**:

- `lookforward_days` upper bound 1095 (~3 years): matches the
  upstream reservations endpoint ceiling (CONFIRMED-BY-TEST).
  Exceeds the config option's 730-day `LOOKAHEAD_MAX` deliberately
  — the option governs a polling sensor; the action is a one-shot
  call (FR-027).
- `lookbackward_days` lower bound 0: allows future-only search.
  The config option's `lookback_days` minimum is 7, but that bound
  exists for polling sensors, not one-shot lookups (FR-026).
- `lookbackward_days` upper bound 365: matches `LOOKBACK_MAX`
  (FR-026).

**Validation errors**: Out-of-range values raise
`ServiceValidationError` via Voluptuous `vol.Range` (FR-028).

**`date_query` unchanged**: Remains fixed at `checkin` in
`build_reservation_params` (FR-029).

**Privacy chokepoint preserved**: Response flows through
`serialize_response`. The `found: false` vs `found: true`
distinction is preserved (FR-030).

**Docstring contract (FR-031)**: The handler's docstring is
rewritten from "The queried window matches the one the reservation
coordinator polls" to:

> When both parameters are omitted the forward reach matches the
> reservation coordinator's `lookahead_days`; the backward reach
> defaults to 7 days (not `lookback_days`). Callers who need the
> sensors' exact window must pass both parameters explicitly.

**No changes to options or sensors (FR-032)**: The reservation
coordinator, sensors, and option bounds are untouched.

## Response privacy chokepoint (MODIFIED)

Listing objects within service responses now pass through a listing
allowlist in `actions/response.py` (FR-010, FR-011, FR-012).

| Listing key | In response? |
| --- | --- |
| `platform` | Always |
| `platform_id` | Always |
| `co_hosts` | Always (then gated per co-host) |
| `platform_email` | Only with `guest_contact_details` on |
| `platform_picture` | Only with `guest_contact_details` on |
| Any other key | Dropped (fail-closed) |

This filter handles the list-of-dicts shape listings arrive in,
mirroring `_filter_co_hosts`. Co-hosts within listings continue
through the existing `CO_HOST_KEYS` path (FR-013).

## Error contract (unchanged)

The error taxonomy from specs 002–003 applies.
`ServiceValidationError` for user-correctable input;
`HomeAssistantError` for API failures.

## No new services

No new service is introduced by spec 004.
