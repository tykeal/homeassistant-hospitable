<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Contract: Errors, Redaction, and Diagnostics

**Feature**: [../spec.md](../spec.md) |
**Research**: [../research.md](../research.md)

## Exception hierarchy

Every exception carries the HTTP status, the endpoint path, and a
redacted body excerpt (FR-035). Bare `Exception` propagation is
prohibited (Principle II).

```text
HospitableError                     status, endpoint, redacted excerpt
├── HospitableAuthError             401
├── HospitableScopeError            403 with a scope-related reason
├── HospitableForbiddenError        403 without a scope-related reason
├── HospitableNotFoundError         404
├── HospitableRateLimitError        429, carries retry_after
├── HospitableConnectionError       transport failure, 5xx
└── HospitableResponseError         shape or envelope violation
    └── HospitableIncludeMissingError   post-condition failure (FR-075)
```

## The 403 classification rule

This is the single most consequential branch in the error handling, and
the one most likely to be implemented wrongly. Getting it wrong in the
permissive direction puts a valid config entry into a reauthentication
loop the user can never satisfy — a failure mode Principle X names
PROHIBITED.

```text
on HTTP 403:
    body = parse_json(response)  # may fail
    reason = body.get("reason_phrase") or body.get("message")
             or body.get("error") or ""
    if "scope" in reason.casefold():
        raise HospitableScopeError(...)
    raise HospitableForbiddenError(...)
```

| Property | Value |
| --- | --- |
| Default branch | `HospitableForbiddenError` — including on an absent, empty, or unparsable body |
| Matching | Case-insensitive substring `scope`, never an exact literal |
| Retried | Neither branch |
| Triggers reauth | Neither branch, ever |
| Raises a repair issue | `HospitableForbiddenError` only |

**Why the default is the non-scope branch**: `HospitableScopeError`
suppresses retry, reauth, and the repair issue. Defaulting to it would
silently swallow a genuine authorization problem. Defaulting the other
way surfaces a repair issue that is at worst noisy.

**Why substring rather than literal**: `"Invalid scope(s) provided."`
is one observed string from one endpoint. Matching it exactly means an
upstream wording change reroutes every scope failure into the
reauthentication loop Principle X prohibits.

**Confirmed instance**: `GET /reservations/{id}/enrichment` returns
`403 {"reason_phrase":"Invalid scope(s) provided."}` on a PAT while
`GET /reservations/{id}` returns 200 with the same token. This
integration does not call the enrichment route at all (see
[upstream-requests.md](./upstream-requests.md#prohibited-requests)), so
the branch exists to be correct rather than to be exercised in normal
operation — which is precisely why it needs a test with a synthetic
fixture rather than reliance on field reports.

## Status to outcome mapping

| Status | Exception | Retried | User-visible outcome |
| --- | --- | --- | --- |
| 401 | `HospitableAuthError` | No | Reauthentication flow (FR-014, FR-065) |
| 403 scope | `HospitableScopeError` | No | Capability omitted; nothing surfaced as failing (FR-038) |
| 403 other | `HospitableForbiddenError` | No | Repair issue (FR-065) |
| 404 | `HospitableNotFoundError` | No | Property entities unavailable with a reason (FR-056) |
| 429 | `HospitableRateLimitError` | Yes | Backoff; normal polling resumes (SC-007) |
| 5xx | `HospitableConnectionError` | Yes | Last known values retained (FR-057) |
| transport | `HospitableConnectionError` | Yes | Last known values retained (FR-057) |
| shape violation | `HospitableResponseError` | No | Repair issue after persistence (FR-034, FR-065) |
| post-condition | `HospitableIncludeMissingError` | No | Documented per-call fallback; logged once (FR-075) |

## User-facing error text

FR-064 and Principle VII: every user-facing error states what failed
and what to do. A bare HTTP status code is not acceptable. A message
must not direct a user to fix a credential when the failure is a
capability limit their credential type cannot satisfy.

| Condition | Must say |
| --- | --- |
| Token rejected | That the token was rejected, that the cause is either an invalid or expired token **or** a plan without Public API access, and where to generate a replacement (Apps then API access) |
| Scope limitation | That a capability is unavailable for this credential type. **Must not** mention fixing the token |
| No properties on the account | That the account contains no properties |
| No properties selected | That at least one property is required |
| Out-of-range option | The permitted bound, by name and value (FR-016) |
| Invalid timezone override | That the value must be an IANA zone name, with an example |
| Property gone upstream | That the property is no longer present in the account |

## Redaction

Two mechanisms for two different problems. See
[../research.md D-10](../research.md#d-10) for why they differ.

### Logs and exception text: denylist plus value sweep

Applied by `api/redaction.py` to anything that could reach a log record
or an exception message.

| Layer | Mechanism |
| --- | --- |
| Key tokens | Substring match on `token`, `authorization`, `secret`, `password`, `email`, `login`, `phone`, `picture`, `co_host`, `vat`, `tax`, `platform_name` |
| Value sweep | Regex over the rendered text for bearer tokens, email addresses, and telephone-shaped strings |
| Truncation | Bounded excerpt length |
| Sanitization | Newlines and control characters stripped, so a payload cannot forge log lines |

The value sweep runs **after** key redaction, as defence in depth
against a key name nobody anticipated.

### Diagnostics: allowlist

FR-073 requires personal data to be treated as sensitive by default
"whether the endpoint is already known to carry personal data **or is
added in a later specification**". A denylist cannot satisfy that
clause — a future endpoint returning an undenied field would be emitted
in full. An allowlist fails closed.

The diagnostics payload contains:

| Section | Content |
| --- | --- |
| Entry | `version`, `minor_version`, `namespace_source`. **Not** the namespace value, **not** the token |
| Options | Every option except that `timezone_overrides` is reduced to a count and the zone names |
| Coordinator health | Per coordinator: last success flag, consecutive failure count, configured interval, last exception **type** and status code |
| Counts | Selected properties, reservations in the window, calendar days held, entities created |
| Response skeletons | Per endpoint, the most recent response rendered as key names paired with the Python **type** of their values, never the values |
| Redaction report | Count of keys dropped by the allowlist, so an omission is visible |

The response skeleton is the design's main triage tool. It answers
"what shape did the API actually return" — which is the question almost
every support request reduces to — while being structurally incapable
of carrying a name, an address, a coordinate, or a token.

### What never appears anywhere

| Category | Examples |
| --- | --- |
| Credentials | The PAT, in any log level, diagnostic, or exception (FR-006) |
| Guest data | Names, email addresses, phone numbers, message content (FR-062) |
| Account data | Email, name, postal address, company, VAT number, tax identifier (FR-073) |
| Listing data | `platform_email`, `platform_name`, `platform_user_id`, `platform_picture`, `co_hosts` (FR-073) |
| Channel data | The `/channels` `login` field, which can be a clear-text email (FR-073) |
| Property data | Street number, street, postcode, coordinates |

Most of these are not merely redacted — they are **never read into a
model at all** (see [../data-model.md](../data-model.md)). Dropping at
the boundary is strictly safer than redacting at the sink, because a
value that was never parsed cannot be forgotten at a new call site.

The `/channels` endpoint is not called by this integration for exactly
this reason: nothing needs it, and it carries a clear-text email.

## Forward-looking: the request trace identifier

Observed but not yet exploited: every Hospitable response carries an
`x-hospitable-trace` header holding a per-request trace identifier
(CONFIRMED-BY-TEST on a `200` from `GET /properties`). Nothing in the
codebase currently captures it. Surfacing it in error logs and in the
diagnostics dump would let a user file a Hospitable support ticket that
the vendor can act on directly, because the identifier ties a failed
request back to Hospitable's own request logs. The value is opaque and
carries no personal data, so it is safe to emit under the allowlist. It
is recorded here as an opportunity only; no requirement or task in this
specification depends on it.

## Verification

SC-008 requires an audit finding zero occurrences of the token and zero
unredacted personal data. That is made mechanically testable:

| Test | Asserts |
| --- | --- |
| Diagnostics leak test | A diagnostics dump built from every synthetic fixture contains none of those fixtures' personal-data values and none of the synthetic token |
| Log leak test | A `caplog` capture at `DEBUG` across a full three-coordinator refresh, an auth failure, a scope failure, and a shape violation contains none of them |
| Exception text test | Every exception type's rendered message contains none of them |
| Skeleton test | The response skeleton contains only key names and type names, proven by asserting no fixture value string appears |
| Fixture PII test | The pre-commit guard fails on a deliberately poisoned fixture, and passes on the real fixture set |

The last row tests the guard itself. A guard nobody has watched fail is
a guard nobody knows works.
