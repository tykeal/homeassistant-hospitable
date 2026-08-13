<!--
SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
SPDX-License-Identifier: Apache-2.0
-->

# Hospitable

Hospitable for Home Assistant connects to the Hospitable Public API so
property managers can select properties and poll vacation-rental data
from a custom integration.

## Entities

Per selected property: reservation status, next arrival, next
departure, upcoming reservations, property info, calendar availability,
next task, and task count. Enabling the awaiting-host-reply option adds
a last-message timestamp and an awaiting-host-reply indicator.

## Services

- `hospitable.send_message` — submit a message to a guest thread.
  Hospitable answers with HTTP 202, which means **accepted for
  asynchronous delivery**. It is not a confirmation that the guest
  received or read anything.
- `hospitable.get_messages` — read a reservation's message thread.
- `hospitable.find_reservation` — look up one reservation.
- `hospitable.get_reservations` — list a property's reservations.
- `hospitable.get_property_info` — property detail, listings, and
  co-host identifiers.

All five return a response. A lookup that finds nothing returns
`found: false` instead of raising, so automations can branch on it.

## Privacy and cost opt-ins

Both are **off by default**:

- Guest contact details are exposed only if you opt in. Guest
  attributes are never written to the recorder database, and message
  bodies are never stored as attributes or logged.
- Awaiting-host-reply tracking costs one extra API request per property
  per reservation poll.

## Rate limits

Message operations are limited to 2 requests per 60 seconds **per
reservation** (confirmed by test) and a documented 50 per 5 minutes per
token (documented only, never observed). The budget is shared per
token, so two config entries using the same token share it.

Polling is strictly read-only. The only non-`GET` request the
integration ever makes is the one behind `send_message`, and only when
you call it.
