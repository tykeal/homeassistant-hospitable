# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Repair flows for the Hospitable integration.

The token expiry issue (spec 001 OQ-007) is fixable so the user can act
BEFORE the token stops working. Home Assistant normally offers reauth
only after a credential failure; this flow starts the entry's existing
reauth flow on request instead, reusing its validation and its
same-account check rather than duplicating them.
"""

from __future__ import annotations

from typing import Any

import probatio as vol
from homeassistant.components.repairs import RepairsFlow, RepairsFlowResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir


class TokenExpiringRepairFlow(RepairsFlow):
    """Confirm, then hand off to the entry's reauth flow."""

    def __init__(self, entry_id: str | None) -> None:
        """Remember which config entry the issue belongs to."""
        self._entry_id = entry_id

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        """Handle the first step of the fix flow."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> RepairsFlowResult:
        """Explain the renewal, then start reauth on confirmation.

        The flow ABORTS rather than finishing: Home Assistant deletes an
        issue when its fix flow completes, and this issue must survive
        until a new token is actually stored. The reload that follows a
        successful reauth re-evaluates the token and clears it then.
        """
        entry = (
            self.hass.config_entries.async_get_entry(self._entry_id)
            if self._entry_id
            else None
        )
        if entry is None:
            return self.async_abort(reason="entry_not_found")
        if user_input is not None:
            entry.async_start_reauth(self.hass)
            return self.async_abort(reason="reauth_started")
        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders=self._placeholders(),
        )

    def _placeholders(self) -> dict[str, str] | None:
        """Return the issue's own placeholders for the confirm text."""
        issue = ir.async_get(self.hass).async_get_issue(self.handler, self.issue_id)
        return dict(issue.translation_placeholders or {}) if issue else None


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    """Create the fix flow for a Hospitable repair issue."""
    del hass, issue_id
    entry_id = (data or {}).get("entry_id")
    return TokenExpiringRepairFlow(entry_id if isinstance(entry_id, str) else None)
