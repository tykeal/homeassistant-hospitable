<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract: Upstream Requests

**Feature**: [../spec.md](../spec.md) | **Plan**: [../plan.md](../plan.md)

This is the exhaustive, normative list of HTTP requests the integration
is permitted to issue. A request not listed here is a defect. The list
exists because Hospitable returns HTTP 200 for requests it did not
honor, so "what we send" and "what we verify came back" have to be
specified together.

## Global rules

| Rule | Requirement |
| --- | --- |
| Base URL is a single compiled-in constant `https://public.api.hospitable.com/v2` | FR-001, FR-002, Principle II |
| Scheme is `https` with certificate verification on; no option disables either | FR-027 |
| Auth is `Authorization: Bearer <PAT>` on every request | FR-001 |
| No request is issued to any non-v2 or non-public Hospitable surface | FR-002 |
| No write request of any kind is issued | FR-059, and this feature is read-only |
| All I/O is async on `httpx.AsyncClient`; nothing blocks the event loop | FR-040, Principle VIII |
| Every client is torn down on entry unload | FR-041 |

## Honored-Request Verification

**HTTP 200 is not proof that a request was honored.** Five
independent silent-ignore behaviors are CONFIRMED upstream. Every
optional input therefore appears in this register with either a
post-condition or a prohibition.

| Input | Upstream behavior | Tier | Rule |
| --- | --- | --- | --- |
| `include=listings` on `/properties` | Valid expansion | CONFIRMED | SEND; assert `listings` present on every item |
| `include=properties` on `/reservations` | Valid expansion | CONFIRMED | SEND; assert `properties` present on every item |
| `include=guests` on `/reservations` | Accepted, adds nothing | CONFIRMED no-op | NEVER SEND |
| any other `include` value | Accepted, adds nothing | CONFIRMED | NEVER SEND |
| `listing_id` on the calendar route | Silently discarded | CONFIRMED | NEVER SEND |
| `links[].url`, `meta.path` | Returned with `http://` | CONFIRMED | NEVER FOLLOW |
| `page`, `per_page` | Honored | CONFIRMED | SEND; assert `meta.current_page` equals the page requested |
| `properties[]` on `/reservations` | Required | CONFIRMED | SEND always; assert every returned reservation belongs to the requested set |
| `start_date`, `end_date` on `/reservations` | Effectively required | CONFIRMED | SEND always; re-filter locally |
| `status[]` on `/reservations` | Honored | CONFIRMED (OQ-003) | NEVER SEND; status handling stays client-side |
| `per_page` on `/channels` | Silently ignored; all rows returned | CONFIRMED-BY-TEST (OQ-011) | NEVER SEND; endpoint uncalled and unpaginated |
| unknown parameter *name*, e.g. `date_type`, `filter_date_type` | Accepted, changes nothing; an unknown *value* is rejected instead (`date_query=bogus` → HTTP 400) | CONFIRMED-BY-TEST | NEVER SEND; only registered parameter names are sent |
| `date_query=checkin` | Real, honored, and validated; value set is exactly `checkin` or `checkout`; platform default is currently `checkin` | CONFIRMED-BY-TEST; live probe 2026-08-09 | SEND always, even though it matches the current default, so a future platform default change cannot silently alter window semantics |

A post-condition failure raises `HospitableIncludeMissingError` or
`HospitableResponseError`, never a silent degradation (FR-075).

## Permitted requests

### `GET /user`

**When**: config flow token validation, and reauth token validation
only. Never on a poll.

**Purpose**: FR-004 token verification, and retrieval of the FR-013 and
FR-055 stable account identifier.

| Aspect | Value |
| --- | --- |
| Parameters | none |
| Post-conditions | `data.id` present and non-empty |
| Read into a model | `data.id` only |
| Discarded at the boundary | email, name, postal address, company, VAT number, tax identifier, and every other key (FR-073) |

**Failure mapping**: 401 to `HospitableAuthError`, which the config
flow surfaces as `invalid_auth` with the FR-007 remediation text.

### `GET /properties`

**When**: config flow property list, and every properties coordinator
refresh.

| Aspect | Value |
| --- | --- |
| Parameters | `include=listings`, `page`, `per_page` (clamped to 100) |
| Pagination | Envelope-driven, self-constructed (see below) |
| Post-conditions | `data` is a list; `meta.current_page` equals the requested page; every item carries a `listings` key |
| Requirements | FR-010, FR-025, FR-053, FR-075 |

**On the `listings` assertion failing**: log once at WARNING naming the
endpoint and the missing key; set `listings_available = False` on every
property; continue the refresh. The `property_info` attribute set then
reports the gap explicitly instead of appearing to have no channel
listings.

### `GET /reservations`

**When**: every reservations coordinator refresh.

| Aspect | Value |
| --- | --- |
| Parameters | `properties[]` repeated, `start_date`, `end_date`, date-filter mode, `include=properties`, `page`, `per_page` |
| Batching | At most 50 property identifiers per request; larger selections split and merged into one consistent result set (FR-031) |
| Pagination | Per batch, envelope-driven, self-constructed |
| Post-conditions | `data` is a list; `meta.current_page` matches; every item carries `properties`; every item's property identifier is in the requested batch |
| Requirements | FR-025, FR-028, FR-029, FR-030, FR-031, FR-032, FR-039, FR-075 |

**Never sent**: `include=guests` (CONFIRMED no-op; see
[../research.md D-06](../research.md#d-06)), `status[]` (correctness
must not depend on server-side status filtering, OQ-003).

**The 50-identifier ceiling is defensive, not derived.** No upstream
limit on request length or filter count is published (FR-031,
UNVERIFIED). It is a self-imposed bound to keep the query string from
growing without a known ceiling.

**Local re-filter**: the merged result set is filtered against the
configured window before it reaches the coordinator, so a looser
server-side filter cannot breach the FR-039 memory bound.

**Window mismatch handling**: a returned reservation outside the
requested window is a *filter* discrepancy, not a *shape* violation. It
is logged once and the row is dropped by the local re-filter. It does
not raise, because FR-034's raise-on-mismatch governs response
structure, and treating a filter looseness as a fatal shape error would
take the integration down over data that is otherwise perfectly usable.

### `GET /properties/{property_id}/calendar`

**When**: every calendar coordinator refresh, once per selected
property.

| Aspect | Value |
| --- | --- |
| Parameters | `start_date`, `end_date` only |
| Concurrency | Bounded by a semaphore; self-imposed civility, not a published limit |
| Response shape | `data` is an **object**, not a list. The list-envelope parser must not be applied |
| Post-conditions | `data.days` is a list; each day carries `date`, `status.available`, and either a `price` object or an explicit null |
| Requirements | FR-058, FR-060, FR-061, FR-071 |

**`listing_id` is never sent.** CONFIRMED: passing a bogus value
returns HTTP 200 with identical data, so the parameter is silently
discarded (OQ-010). The desired calendar is the aggregate across all
sales channels, which is what this route already returns, so there is
nothing the parameter could usefully do.

**Failure isolation**: a failure for one property degrades only that
property. Its last-good calendar is retained and its availability
sensor is the only entity affected. The refresh raises `UpdateFailed`
only when every property failed.

## Prohibited requests

| Request | Why prohibited |
| --- | --- |
| Any `PUT`, `POST`, `PATCH`, or `DELETE` | This feature is read-only |
| Any calendar modification | FR-059, absolutely, even though a PAT is permitted to make them |
| `GET /reservations/{id}/enrichment` | Vendor-gated; CONFIRMED 403 on a PAT. No capability detection, no probing |
| `GET /channels` | Not needed; carries a clear-text email in `login` (FR-073); pagination behavior UNVERIFIED (OQ-011) |
| Any Hospitable internal web-application endpoint | FR-002 |
| The Hospitable MCP server | FR-002 |
| Any request to a URL taken from a response body | FR-026, Principle X |

The enrichment prohibition is worth stating positively: the integration
does not call it *even to discover whether it would work*. Out of Scope
rules out capability detection, and a probe would produce a 403 that
some future error-handling change could misroute into reauth.

## Pagination contract

```text
page = 1
loop:
    url    = BASE_URL + path                    # never from the body
    params = {..., "page": page, "per_page": min(requested, 100)}
    body   = GET(url, params)
    assert body["meta"]["current_page"] == page
    yield body["data"]
    if page >= body["meta"]["last_page"]: break
    if page >= ABSOLUTE_PAGE_CEILING:    break   # malformed-envelope guard
    page += 1
```

| Property | Requirement |
| --- | --- |
| Every page URL is constructed from the compiled-in base URL | FR-026 |
| `links`, `meta.path`, and every other URL-valued response field are ignored entirely | FR-026, Principle X |
| `per_page` never exceeds 100 | FR-025 |
| Termination uses `meta`, not link presence | FR-025 |
| An absolute ceiling bounds the loop against a malformed envelope | FR-039 |
| `meta.current_page` mismatch raises | FR-034 |

**Enforcement test**: the `respx` mock registers
`http://public.api.hospitable.com/...` with a side effect that raises.
Any change that starts following body links fails that test rather than
silently downgrading a user's transport security. This is the guard
that makes FR-026 a mechanically enforced rule instead of a convention.

## Retry policy

| Condition | Retried | Delay |
| --- | --- | --- |
| `httpx.TransportError` | Yes | Jittered exponential |
| 429 | Yes | `Retry-After` if present, else jittered exponential |
| 5xx | Yes | Jittered exponential |
| 401 | No | Reauth (FR-014, FR-065) |
| 403 scope-related | No | Capability limitation (FR-038) |
| 403 other | No | Repair issue (FR-065) |
| 404 | No | FR-056 handling |
| Shape or post-condition violation | No | FR-034 |

Attempts are bounded; on exhaustion the last typed exception is raised
with its context intact (FR-037). No quota is hard-coded and no
rate-limit header is assumed to be present (FR-036, OQ-005, A-7).
`Retry-After` is parsed in both delta-seconds and HTTP-date forms if it
appears; absence is the expected case. `MAX_BACKOFF = 300` seconds,
chosen to satisfy SC-007's five-minute resumption bound even when the
computed delay includes maximum jitter.

## Request budget

At default settings with ten selected properties and no more than 500
reservations in the window (SC-004's stated bound):

| Component | Requests per day |
| --- | --- |
| Property polls: `1440 / 60` x 1 page | 24 |
| Calendar polls: `1440 / 60` x 10 properties | 240 |
| Reservation polls: `1440 / 5` x 1 batch x 5 pages | 1,440 |
| **Total** | **1,704** |

Under the SC-004 ceiling of 2,000, with roughly 15% headroom. The
reservation page count dominates, which is why FR-023's window warning
is operationally real and why FR-072 requires the options screen to
show a live estimate.
