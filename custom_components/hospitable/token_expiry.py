# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Warn before a Personal Access Token expires (spec 001 OQ-007).

Hospitable Personal Access Tokens expire one year after issue and
cannot be refreshed, so the only remedy is a new token. Without a
warning the integration notices only once every call fails with 401.

A token is, empirically, a JWT whose payload carries an ``exp`` claim.
Hospitable does not document that format, so reading it is strictly
best-effort: any token that does not decode cleanly yields no expiry
and therefore no warning. The signature is never verified because the
value is only advisory; Hospitable remains the authority on validity.

Nothing derived from the token other than the expiry DATE may leave
this module: not the token, not its segments, and not identifying
claims such as ``sub`` or ``jti``.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from custom_components.hospitable.const import CONF_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

LEAD_TIME = timedelta(days=30)
ISSUE_TRANSLATION_KEY = "token_expiring"
# 1 January 3000. An ``exp`` beyond it is not a credible one-year token
# and would overflow ``datetime`` arithmetic soon after anyway.
_MAX_EXP = 32503680000


def token_expiry(token: str) -> datetime | None:
    """Return when ``token`` expires, or ``None`` if that is unknowable.

    Args:
        token: A Hospitable Personal Access Token.

    Returns:
        The ``exp`` claim as an aware UTC datetime, or ``None`` when the
        token is not a readable JWT carrying a plausible ``exp``.
    """
    segments = token.split(".")
    if len(segments) != 3:
        _LOGGER.debug("Token is not JWT-shaped; expiry is unknown")
        return None
    payload_segment = segments[1]
    try:
        raw = base64.urlsafe_b64decode(
            payload_segment + "=" * (-len(payload_segment) % 4)
        )
        payload: Any = json.loads(raw.decode("utf-8"))
    except ValueError:  # binascii, Unicode and JSON decode errors alike
        _LOGGER.debug("Token payload is not decodable; expiry is unknown")
        return None
    exp = payload.get("exp") if isinstance(payload, dict) else None
    if isinstance(exp, bool) or not isinstance(exp, int | float):
        _LOGGER.debug("Token carries no numeric expiry claim")
        return None
    if not 0 < exp < _MAX_EXP:
        _LOGGER.debug("Token expiry claim is out of range; ignoring it")
        return None
    return datetime.fromtimestamp(exp, tz=UTC)


def issue_id(entry_id: str) -> str:
    """Return the repair issue id for one config entry's token."""
    return f"{ISSUE_TRANSLATION_KEY}_{entry_id}"


@callback
def async_delete_token_issue(hass: HomeAssistant, entry_id: str) -> None:
    """Remove the token expiry issue for one config entry, if raised."""
    ir.async_delete_issue(hass, DOMAIN, issue_id(entry_id))


@callback
def async_track_token_expiry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Raise, escalate, or clear the entry's token expiry issue.

    Evaluated now, then re-evaluated by a one-shot timer at the next
    transition (the start of the lead window, then expiry itself) so a
    long-running instance warns without waiting for a restart. Setup
    calls this on every load, including the reload after reauth, so a
    fresh token clears the issue. The timer is cancelled on unload.

    Args:
        hass: The Home Assistant instance.
        entry: The config entry whose token is checked.
    """
    expires = token_expiry(str(entry.data.get(CONF_TOKEN, "")))
    cancel: list[CALLBACK_TYPE] = []

    @callback
    def _evaluate(_now: datetime | None = None) -> None:
        """Apply the issue state for the current time and re-arm."""
        cancel.clear()
        if expires is None:
            async_delete_token_issue(hass, entry.entry_id)
            return
        now = dt_util.utcnow()
        warn_from = expires - LEAD_TIME
        if now < warn_from:
            async_delete_token_issue(hass, entry.entry_id)
            next_check: datetime | None = warn_from
        else:
            _create_issue(hass, entry, expires, expired=now >= expires)
            next_check = expires if now < expires else None
        if next_check is not None:
            cancel.append(async_track_point_in_utc_time(hass, _evaluate, next_check))

    @callback
    def _cancel() -> None:
        """Cancel whichever timer is currently armed."""
        for unsubscribe in cancel:
            unsubscribe()
        cancel.clear()

    _evaluate()
    entry.async_on_unload(_cancel)


def _create_issue(
    hass: HomeAssistant, entry: ConfigEntry, expires: datetime, *, expired: bool
) -> None:
    """Raise the fixable token expiry issue for one entry."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id(entry.entry_id),
        config_entry_id=entry.entry_id,
        data={"entry_id": entry.entry_id},
        is_fixable=True,
        severity=ir.IssueSeverity.ERROR if expired else ir.IssueSeverity.WARNING,
        translation_key=ISSUE_TRANSLATION_KEY,
        translation_placeholders={
            "expiry": expires.date().isoformat(),
            "title": entry.title,
        },
    )
