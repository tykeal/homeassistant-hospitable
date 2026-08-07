<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Specification Quality Checklist: Hospitable HA Integration

**Purpose**: Validate specification completeness and quality before
proceeding to planning

**Created**: 2026-08-06

**Last validated**: 2026-08-07

**Feature**: [spec.md](../spec.md)

## Content Quality

- [ ] **DELIBERATE DEVIATION** — No implementation details (languages,
      frameworks, APIs). See "Accepted deviations" below.
- [x] Focused on user value and business needs
- [ ] **DELIBERATE DEVIATION** — Written for non-technical
      stakeholders. See "Accepted deviations" below.
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [ ] **DELIBERATE DEVIATION** — Success criteria are
      technology-agnostic. See "Accepted deviations" below.
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [ ] **DELIBERATE DEVIATION** — No implementation details leak into
      specification. Same deviation as the first Content Quality item;
      listed twice because the template asks twice.

## Accepted deviations

**This checklist does not certify that the specification contains no
implementation detail. It does the opposite: it records that the
specification deliberately carries a substantial amount of upstream
API detail, and explains why.**

This is an integration specification. The product being specified is a
bridge to a third-party API whose concrete, observed, and in places
defective behavior *is* the constraint being specified. A requirement
that said "the integration should page through results sensibly" would
be untestable and would not have caught the insecure-scheme pagination
defect. Removing the detail would not make the document more
product-focused; it would make it unimplementable and would discard
the empirical findings that are this specification's main contribution.

### Requirements that carry upstream API detail

| Requirement | Detail carried |
| --- | --- |
| FR-001 | Base URL, API version, HTTP bearer auth scheme |
| FR-002 | Named exclusion of non-public API surfaces |
| FR-024 | `snake_case` upstream field naming |
| FR-025 | Maximum page size of 100; page/page-size parameters |
| FR-026 | Insecure `http://` scheme in returned pagination links |
| FR-028 | Mandatory property filter on the reservations endpoint |
| FR-029 | Empty result when date bounds are omitted |
| FR-030 | Explicit date-filter mode parameter |
| FR-031 | Batch ceiling of 50 property identifiers per request |
| FR-032 | Structured versus deprecated flat status fields |
| FR-033 | Guest data reachable only as a query include |
| FR-036 | HTTP 429; retry-delay headers; exponential backoff with jitter |
| FR-038 | HTTP 403 scope errors distinguished from HTTP 401 |
| FR-043 | Upstream status categories, including `checkpoint` |
| FR-045 | Absence of a checked-in status upstream |
| FR-049 | Upstream stay-type field |
| FR-058 | Property calendar route and aggregate response shape |
| FR-060 | Integer minor currency units |
| FR-073 | Non-exhaustive upstream fields known to carry personal data |
| FR-075 | Silent-ignore behavior for optional request parameters |

### Other deviations

- **FR-069 prescribes internal package structure.** Normally an
  implementation concern. Retained because it is a stated user
  decision that governs where later specifications may add code, and
  because the `services` package name collides with a reserved Home
  Assistant term and therefore needs defining once, centrally. The
  requirement text says both things explicitly. No other requirement
  prescribes internal structure.
- **SC-004 counts upstream API requests per day** and **SC-013 names
  Raspberry-Pi-class hardware and a 100 ms event-loop bound.** Neither
  names a framework, language, or datastore, but both are closer to
  implementation than a pure outcome metric. Retained because request
  volume is the central operational risk in the absence of any
  published upstream rate limit, and because small-board hardware is
  the constitution's stated deployment target. SC-013's earlier
  wording ("no measurable delay") was unfalsifiable and was replaced
  with a number for exactly this reason.
- **"Written for non-technical stakeholders" is only partly true.**
  The user stories, success criteria, Out of Scope, and Open Questions
  sections are readable by a property manager. The Functional
  Requirements section is not, and is not intended to be — its
  audience is the implementer and the reviewer.

## Notes on confidence marking

This specification uses a four-tier evidence legend (CONFIRMED,
DOCUMENTED, LIKELY, UNVERIFIED) rather than [NEEDS CLARIFICATION]
markers, because the unresolved items are questions about a third
party's undocumented API rather than questions the user can answer.
Thirteen Open Questions (OQ-001 through OQ-013) carry them. OQ-002,
OQ-003, OQ-008, OQ-009, and OQ-010 have since been resolved by live
test and are retained, restated as RESOLVED, for the historical
record.

Two marking rules are enforced and were re-audited on 2026-08-07:

- No claim sourced from Hospitable's user-facing documentation is
  marked CONFIRMED. The DOCUMENTED tier exists because one such claim
  — that a Personal Access Token reaches every Public API endpoint by
  default — was disproved by live test.
- No claim sourced from absence in a third-party specification
  snapshot is marked CONFIRMED. Absence of evidence is recorded as
  UNVERIFIED.

## Status

The checklist records both passing items and deliberate deviations
above. It is **not** a claim that every box is ticked — four are
deliberately not.
