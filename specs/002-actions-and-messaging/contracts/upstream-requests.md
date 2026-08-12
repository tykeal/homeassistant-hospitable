<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract: Upstream Requests (Spec 002 Additions)

**Feature**: [../spec.md](../spec.md) | **Plan**: [../plan.md](../plan.md)

This document defines the NEW upstream requests introduced by spec 002
and changes to spec 001's request register. Spec 001's
[upstream-requests.md](../../001-hospitable-ha-integration/contracts/upstream-requests.md)
remains authoritative for all previously defined requests; this
document extends it.

## Changes to spec 001 contract

### Honored-Request Verification table: new entry

| Input | Upstream behavior | Tier | Rule |
| --- | --- | --- | --- |
| `include=guest` on `/reservations` | Valid expansion; adds `guest` key (22 keys total) | CONFIRMED-BY-TEST | SEND; assert `guest` key present on every item (value may be null) |

**Note**: This differs from the `include=guests` (plural) entry which
remains a confirmed no-op under "NEVER SEND." The correct parameter is
singular `guest`.

### Global rules table: modification

The spec 001 rule "No write request of any kind is issued" is
**narrowed** to:

> No write request (POST, PUT, PATCH, DELETE) is issued from any
> polling lifecycle path (coordinator refresh, setup, reload, unload).
> Write requests are permitted ONLY from explicit user-invoked service
> call handlers in the `actions/` package.

This narrowing is FR-001/FR-002 of spec 002.

## New permitted requests

### `POST /reservations/{uuid}/messages`

**When**: User invokes the `hospitable.send_message` service. NEVER
from a coordinator, setup, reload, or unload path.

| Property | Value |
| --- | --- |
| Tier | DOCUMENTED (never executed against live account) |
| Auth | Bearer PAT |
| Content-Type | `application/json` |
| Body | `{"body": string, "images": [uri, ...] optional, "sender_id": string optional}` |
| Success | HTTP 202 Accepted |
| Errors | 400 (bad request), 422 (validation), 403 (scope/capability) |

**Rate limits on SEND** (DOCUMENTED-ONLY — no POST has ever been
executed against a live account, so neither figure has been observed):

- 2 messages per minute per reservation
- 50 messages per 5 minutes per PAT user (token)

**Do not conflate these with the READ limit.** The GET on the same
path is CONFIRMED-BY-TEST at 2 requests per 60 seconds per
reservation. That the observed read limit numerically equals the
documented send limit is exactly what OQ-007 is about: the two may or
may not draw on one shared per-reservation bucket, and this cannot be
determined without issuing a real POST to a real guest, which is
prohibited. Assert neither. Send MUST treat a 429 as
retryable-with-backoff, and polling MUST NOT be allowed to starve the
send path.

**Response body**: Shape UNVERIFIED (OQ-001). May contain
`sent_reference_id` or may be empty/minimal. Implementation handles
both defensively. Note that `sent_reference_id` IS confirmed present
on READ messages (see the key list below); what is unverified is
whether the 202 body carries it.

**Post-conditions**: HTTP 202 means "accepted for delivery." It does
NOT mean delivered. The integration must never claim delivery.

---

### `GET /reservations/{uuid}/messages`

**When**: User invokes the `hospitable.get_messages` service, OR the
awaiting-host-reply option is enabled and the reservation coordinator
polls (at most one call per property per cycle).

| Property | Value |
| --- | --- |
| Tier | CONFIRMED-BY-TEST (busiest thread on the account held 10 messages) |
| Auth | Bearer PAT |
| Response | 200 with `{data: [...]}` envelope — no `meta`, no `links` |
| Pagination | NONE (OQ-002 CLOSED); `page`/`per_page` silently ignored |
| Rate limit | 2 requests per 60 seconds, keyed PER RESERVATION (CONFIRMED-BY-TEST) |
| Rate-limit headers | `x-ratelimit-limit: 2`, `x-ratelimit-remaining: <n>`; on 429 also `retry-after` (59-60 observed) and `x-ratelimit-reset` (unix epoch) |
| 429 body | Laravel envelope `{"status_code":429,"reason_phrase":"Too Many Attempts."}` |

**Rate limit, stated precisely**: the bucket is per reservation, not
per token and not per endpoint. This was proven by burning reservation
A to `remaining: 0`, receiving a 429 on the third call, then
immediately calling reservation B and receiving HTTP 200 with a fresh
`remaining: 1`.

**Do NOT overgeneralise this.** `/properties`, `/reservations`, and
`/tasks` expose NO `x-ratelimit-*` and NO `retry-after` headers. Spec
001's recorded finding that those endpoints return only
`x-hospitable-trace` remains CORRECT for the endpoints spec 001
tested. The messages endpoint is simply a different, throttled
endpoint. This is not a spec 001 defect and spec 001 is not edited.

**OQ-007 (OPEN)**: the observed GET limit of 2/60s/reservation exactly
equals the DOCUMENTED send limit of 2/min/reservation, so reads and
writes may share ONE per-reservation bucket. If they do, an
awaiting-host-reply poll could consume budget a user needs for a real
send. This is NOT testable without issuing a real POST to a real
guest, which is prohibited. Design defensively in both directions and
assert neither.

**Message object keys** (CONFIRMED-BY-TEST): `id`, `platform`,
`platform_id`, `conversation_id`, `reservation_id`, `content_type`,
`body`, `attachments`, `reactions`, `sender_type`, `sender_role`,
`sender`, `created_at`, `source`, `integration`, `sent_reference_id`,
`author`.

**PII**: `body` and `sender` contain personal data. Neither is logged.
Both are returned to the service caller (that is their purpose) but
are otherwise invisible to the integration.

**Pagination handling**: there is none. The envelope carries `data`
only. `per_page=1`, `per_page=2`, `page=1`, `page=2`, and
`per_page=1&page=2` ALL returned the identical full set of 10 items as
the bare request, so both parameters are silently ignored. The
integration MUST consume the thread in a SINGLE request, MUST NOT send
`page` or `per_page`, and MUST NOT write a pagination loop.

**Scope caveat, stated honestly**: the busiest conversation on the
reference account holds only 10 messages, so behaviour above that
volume was NOT observed. Pagination may appear above some threshold.
The integration MUST therefore TOLERATE a `meta`/`links` block
appearing later — logging once and continuing rather than crashing —
but MUST NOT treat pagination as expected or write speculative
paging code for it. Never follow `links` URLs (existing prohibition
from spec 001).

---

### `GET /tasks`

**When**: Task coordinator polls at the configured task interval. ONE
request is issued PER SELECTED PROPERTY (fan-out), not one batched
request naming every property.

| Property | Value |
| --- | --- |
| Tier | CONFIRMED-BY-TEST |
| Auth | Bearer PAT |
| Required params | `properties[]` — MUST always be sent |
| Fan-out | One request per property; `properties[]` carries exactly one |
| Prohibited params | Date parameters — MUST NOT be sent |
| Response | 200 with `{data, links, meta}` envelope |
| Pagination | Mandatory; followed independently per property |
| Rate limit | None published; no `x-ratelimit-*`, no `retry-after` |

**Fan-out rationale**: a batched request has a single outcome for every
property, so one failure would blank every task sensor at once. One
request per property gives the per-property failure isolation FR-034
requires, matching spec 001's calendar coordinator and its last-good
retention. At reference scale this is 13 requests per poll on an
endpoint that publishes no rate limit.

**Pagination scope caveat**: `meta.last_page: 2` was observed for a
BATCHED request returning 164 tasks across 13 properties. It is NOT a
per-property page count. Under fan-out each property returns its own
`meta.last_page`, which MUST be followed independently; most properties
are expected to fit a single page and none may be assumed to.

**Failure mode**: Bare call or dates-only returns HTTP 400
`{"status_code":400,"reason_phrase":"The properties field is required.","errors":{...}}`.
(CONFIRMED-BY-TEST)

**Meta vocabularies** (CONFIRMED-BY-TEST):

- `meta.task_types` — canonical task type labels
- `meta.service_types` — canonical service type labels
- `meta.assignment_statuses` — `{pending, accepted, rejected, cancelled, unassigned}`
- `meta.progress_statuses` — `{not_started, on_the_way, arrived,
  in_progress, completed, cancelled}`

**TRAP**: Maintenance is task_type 5 but service_id 8. These two enum
namespaces are NOT interchangeable. (CONFIRMED-BY-TEST)

**Post-condition**: `meta.current_page` asserted equal to the page
requested (existing pagination contract from spec 001).

---

### `GET /reservations` (modified query parameters)

**Change**: The existing reservation poll adds `include=guest` to its
query parameters alongside the existing `include=properties`.

Combined include: `include=guest,properties` (comma-separated on a
single parameter). Multi-include stacking is CONFIRMED-BY-TEST:

- baseline (no include) → 21 keys
- `include=guest` → 22 keys
- `include=guest,properties` → 23 keys
- `include=guest,listings` → 23 keys
- `include=guest,properties,listings` → 24 keys
- URL-encoding the comma (`%2C`) behaves identically

**Post-condition**: Assert BOTH `guest` AND `properties` keys are
present on every reservation item. A missing key raises
`HospitableIncludeMissingError` per spec 001 FR-075. This is mandatory
because unrecognised include names are silently ignored — one of the
silent-ignore behaviours spec 001 FR-075 enumerates — so the assertion
is what distinguishes "include honoured" from "include silently
discarded."

**Fallback**: If the `guest` include assertion fails, log once at
WARNING, set guest data to None on all reservations, and continue.
Guest attributes report no value. This matches the existing
`include=listings` fallback pattern from spec 001.

## Prohibited requests (reaffirmed)

All spec 001 prohibitions remain in force:

- No `include=guests` (plural) — confirmed no-op
- No `include=customer` — confirmed no-op
- No calendar `listing_id` — confirmed silently discarded
- No `per_page` on `/channels` — confirmed ignored
- No following of `links` URLs — confirmed `http://` scheme
- No PUT/PATCH/DELETE from any path (spec 002 introduces POST only,
  and only from service call handlers)
