# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Voluptuous schemas for Hospitable services (FR-010, FR-014)."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.helpers import config_validation as cv

ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_ENTITY_ID = "entity_id"
ATTR_RESERVATION_UUID = "reservation_uuid"
ATTR_BODY = "body"
ATTR_IMAGES = "images"
ATTR_SENDER_ID = "sender_id"

# Upstream accepts at most three images, each at most 5MB. Only the
# count is enforceable client-side; the size is not knowable from a URI.
MAX_IMAGES = 3


def non_empty_text(value: str) -> str:
    """Validate that a message body carries actual content.

    Args:
        value: Candidate message body.

    Returns:
        The value unchanged.

    Raises:
        vol.Invalid: The value is blank or whitespace only.
    """
    if not value.strip():
        raise vol.Invalid("body must not be empty")
    return value


SEND_MESSAGE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
        vol.Optional(ATTR_RESERVATION_UUID): cv.string,
        vol.Required(ATTR_BODY): vol.All(cv.string, non_empty_text),
        vol.Optional(ATTR_IMAGES): vol.All(
            cv.ensure_list, [cv.url], vol.Length(max=MAX_IMAGES)
        ),
        vol.Optional(ATTR_SENDER_ID): cv.string,
    }
)


ATTR_PROPERTY_ID = "property_id"

# Every service accepts the optional config_entry_id (FR-029, FR-008).
# The reservation-targeted services additionally accept EITHER an
# entity_id OR a reservation_uuid; exactly one is required, which
# voluptuous cannot express here because either may be omitted. The
# exactly-one rule is enforced in `helpers.resolve_reservation_uuid` so
# that its message can name both fields (FR-044).
_RESERVATION_TARGET = {
    vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
    vol.Optional(ATTR_RESERVATION_UUID): cv.string,
}

GET_MESSAGES_SCHEMA = vol.Schema(dict(_RESERVATION_TARGET))

# contracts/services.md marks find_reservation's reservation_uuid as
# required. FR-044 is broader and governs: a service that targets a
# reservation MUST accept an entity_id too. The schema therefore
# accepts both and defers the exactly-one rule to the shared resolver,
# which is a superset of the contract rather than a departure from it.
FIND_RESERVATION_SCHEMA = vol.Schema(dict(_RESERVATION_TARGET))

GET_RESERVATIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_PROPERTY_ID): cv.string,
    }
)

GET_PROPERTY_INFO_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_PROPERTY_ID): cv.string,
    }
)
