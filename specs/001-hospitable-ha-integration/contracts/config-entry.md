<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract: Config Entry, Flows, and Migration

**Feature**: [../spec.md](../spec.md) |
**Data model**: [../data-model.md](../data-model.md)

The config entry is a persisted contract. Once a release writes an
entry into a user's `.storage`, its shape can only be changed through a
migration. This document is what a future migration is written against.

## Entry versioning

| Constant | Value |
| --- | --- |
| `VERSION` | `1` |
| `MINOR_VERSION` | `1` |

`async_migrate_entry` is implemented in the first release even though
it has nothing to migrate (FR-070). It does three things:

1. **Refuses a downgrade.** An entry whose `version` exceeds the
   running `VERSION` returns `False` rather than being interpreted by
   code that does not understand it.
2. **Is the single documented place a future migration is added.**
3. **Carries the frozen unique-ID contract in its docstring**, so the
   FR-055 promise is visible at the one place it could be broken.

Adding this retroactively is the failure mode that orphans entities,
because by then entries written by a version-less release already exist
in the wild.

## `entry.unique_id`

The account UUID from `GET /user` (CONFIRMED, OQ-009). This is what
makes the FR-013 duplicate-account abort work by account identity
rather than by comparing token values — two different tokens for the
same account must still be refused.

## `entry.data` — immutable identity

| Key | Type | Notes |
| --- | --- | --- |
| `token` | `str` | The PAT. Config entry storage only; never a file, environment variable, or integration-managed store (FR-003) |
| `account_namespace` | `str` | Frozen at creation; every unique ID depends on it (FR-055) |
| `namespace_source` | `"account" \| "entry"` | Records which FR-055 branch was taken |

`namespace_source` exists because FR-055 defines two branches and the
fallback is not expected to be taken now that the account UUID is
CONFIRMED. Recording which was used makes a future migration able to
tell the two populations apart without guessing, and makes a
diagnostics bundle self-explanatory.

## `entry.options` — user-changeable

| Key | Type | Default | Bounds | Requirement |
| --- | --- | --- | --- | --- |
| `selected_properties` | `list[str]` | none | at least 1 | FR-011, FR-015 |
| `reservation_interval_minutes` | `int` | 5 | floor 1 | FR-019 |
| `property_interval_minutes` | `int` | 60 | floor 15 | FR-020 |
| `lookback_days` | `int` | 90 | 7 to 365 | FR-021, FR-022 |
| `lookahead_days` | `int` | 90 | 1 to 730 | FR-021, FR-022 |
| `timezone_overrides` | `dict[str, str]` | `{}` | valid IANA per entry | FR-074 |

Splitting identity into `data` and preferences into `options` means an
options change never requires a data migration, and a reauth replaces
exactly one `data` key while leaving every preference and every entity
untouched (FR-014).

The floors cannot be lowered by configuration (FR-019, FR-020,
Principle VIII). They are enforced in the schema, so an out-of-range
value is rejected at submission with a message naming the bound
(FR-016), not silently clamped afterwards.

## Config flow

### Step `user`

| Aspect | Behavior |
| --- | --- |
| Input | Personal Access Token, as a password-type field |
| Help text | States that Public API access requires a paid plan, that Essentials is excluded, and that tokens are generated under Apps then API access (FR-007) |
| Validation | `GET /user` (FR-004) |
| On success | Set `unique_id` to the account UUID, abort if already configured (FR-013), advance to `properties` |
| On 401 | Error `invalid_auth`; the form stays editable for a retry |

The `invalid_auth` message names **both** causes — an invalid or
expired token, and an account whose plan has no Public API access — and
never shows a bare status code (US1 acceptance scenarios 2 and 3,
FR-064).

**OAuth is not offered, and the design does not preclude it** (FR-008,
Principle II). Credential handling sits behind a single interface in
`api/auth.py`, so callers never branch on credential type. Adding the
authorization-code flow later is an internal change to that module plus
one additional config flow step. No OAuth client credential is
requested, accepted, or stored by this feature.

### Step `properties`

| Aspect | Behavior |
| --- | --- |
| Input | Multi-select of properties by human-readable name (FR-010) |
| Empty account | Abort with `no_properties`, not an empty selector (FR-011, US1 acceptance scenario 6) |
| Empty selection | Error `no_properties_selected`; the flow refuses to finish (FR-011, US1 acceptance scenario 5) |
| On success | Create the entry with defaults for every other option |

### Step `reauth_confirm`

| Aspect | Behavior |
| --- | --- |
| Trigger | `HospitableAuthError` (401) raised from any coordinator, surfaced as `ConfigEntryAuthFailed` |
| Never triggered by | A scope-related 403, under any circumstance (FR-038, Principle X) |
| Input | Replacement token |
| Validation | `GET /user`; the returned account UUID must equal the stored namespace |
| On success | Replace `entry.data["token"]` only; reload; all entities, identifiers, and history preserved (FR-014) |
| On account mismatch | Abort with a message explaining the replacement token belongs to a different account |

The account-mismatch abort matters: silently accepting a token for a
different account would leave the entry's frozen namespace pointing at
the wrong account, orphaning every entity — the exact outcome FR-055
exists to prevent.

Reauthentication is scoped to one entry. Another entry with a valid
token continues polling normally (US5 acceptance scenario 3).

### Options flow, step `init`

Exposes every key in `entry.options` (FR-015), validated against the
documented bounds with messages naming the permitted bound (FR-016).

| Element | Behavior |
| --- | --- |
| Property multi-select | Adds and removes selections; removal is non-destructive (FR-018) |
| Interval fields | Floors enforced in the schema (FR-019, FR-020) |
| Window fields | Ranges enforced in the schema (FR-021, FR-022) |
| Per-property timezone override | Optional IANA zone, validated against the runtime database before saving; clearable (FR-074) |
| Help text | States that widening the window increases upstream requests, and that narrowing the lookback can hide in-progress long stays and make an occupied property report no reservation (FR-023) |
| Request estimate | Live estimate of upstream requests per day, labelled as an estimate (FR-072) |

Timezone validation uses `homeassistant.util.dt.async_get_time_zone`,
which is cached and executor-backed. A bare `zoneinfo.ZoneInfo(...)`
call reads the filesystem and would block the event loop, violating
Principle VIII and risking SC-013.

Changes take effect on the next poll without a restart (FR-017,
SC-011), via an update listener that reloads the entry. Coordinator
intervals are re-read on reload, so a cadence change applies without
recreating entities.

### Request estimate formula

Displayed by the options flow (FR-072), labelled as an estimate.

```text
property_polls   = floor(1440 / property_interval_minutes)
calendar_polls   = property_polls * selected_property_count
batches          = ceil(selected_property_count / 50)
pages            = max(1, ceil(last_observed_reservation_count / 100))
reservation_polls= floor(1440 / reservation_interval_minutes) * batches * pages
estimate         = property_polls + calendar_polls + reservation_polls
```

`last_observed_reservation_count` comes from the most recent
reservations refresh. Before the first refresh it is unknown and the
formula assumes one page, which the label states, so the number is
honest about being a floor rather than pretending to precision it does
not have.

## Multiple accounts

| Requirement | Mechanism |
| --- | --- |
| Several accounts side by side (FR-012) | One config entry per account; no shared module-level state |
| No duplicate account (FR-013) | `entry.unique_id` is the account UUID; `_abort_if_unique_id_configured` |
| No identifier collision (FR-055, SC-010) | Every unique ID is namespaced by the account |
| Independent polling (US5) | Coordinators are per-entry; runtime data hangs off the entry |
| Isolated failure (US5 scenario 3) | Reauth is raised on the failing entry only |

## Setup and teardown

`async_setup_entry`:

1. Create the `httpx` client through the Home Assistant helper.
2. Construct the API client with the stored token.
3. Instantiate the coordinators this release wires (see the plan's
   phase table) and perform a first refresh.
4. Store runtime data on the entry.
5. Register the options update listener.
6. Forward the sensor platform.

`async_unload_entry` unloads the platform, shuts down every
coordinator, cancels every background task, removes the update
listener, and closes the HTTP client (FR-041). A leaked task or client
across a reload is a resource leak that accumulates over a long-running
instance and would breach SC-005.

## Failure surfacing

| Condition | Surface | Requirement |
| --- | --- | --- |
| 401 | Reauthentication flow | FR-014, FR-065 |
| 403 scope-related | Capability limitation; the affected capability is omitted. **No repair issue, no retry, no reauth** | FR-038, FR-065 |
| 403 other | Repair issue | FR-065 |
| Persistent non-credential failure | Repair issue | FR-065 |
| Transient failure | Last known values retained; unavailable only after three consecutive failures | FR-057 |

FR-065 carves the scope-403 out of the repair-issue rule explicitly:
the affected capability is omitted rather than surfaced to the user as
failing. A repair issue for something the user can never fix is noise
that trains users to ignore repair issues.

**No configuration entry fails silently and permanently** (FR-065).
Every terminal condition above has a user-visible surface.
