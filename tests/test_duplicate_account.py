# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Adding a second entry for a configured account aborts (FR-013).

A second config-flow attempt whose ``/user`` UUID matches an existing
entry must abort with ``already_configured`` and an actionable message,
while a genuinely different account is accepted. This asserts no new
production behavior -- US1 already aborts on a duplicate unique ID -- so
per Principle XII Exemptions it carries no red-phase commit. It also
verifies the abort message is a real, actionable sentence rather than a
bare code, satisfying FR-064.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_SELECTED_PROPERTIES,
    CONF_TOKEN,
    DOMAIN,
)
from tests.helpers import load_fixture

_STRINGS = Path("custom_components/hospitable/strings.json")


def _user_payload(account_id: str) -> dict[str, Any]:
    """Return a ``/user`` payload for a specific account UUID."""
    payload: dict[str, Any] = load_fixture("user.json")
    payload["data"]["id"] = account_id
    return payload


def _install_api(respx_router: Any, state: dict[str, Any]) -> None:
    """Serve the account currently selected by ``state`` plus properties."""

    def _user(request: httpx.Request) -> httpx.Response:
        """Return the account UUID currently armed in shared state."""
        return httpx.Response(200, json=_user_payload(state["account_id"]))

    respx_router.get(f"{BASE_URL}/user").mock(side_effect=_user)
    respx_router.get(f"{BASE_URL}/properties").respond(
        json=load_fixture("properties_single.json")
    )


async def _run_full_flow(hass: Any, token: str) -> Any:
    """Run the user + properties steps and return the terminal result."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={CONF_TOKEN: token}
    )
    if result["type"] == "abort":
        return result
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SELECTED_PROPERTIES: ["prop-example-001"]}
    )


async def test_duplicate_account_aborts_but_new_account_accepted(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """Reject a second entry for a configured account, accept a new one."""
    state: dict[str, Any] = {"account_id": "acct-dup-0001"}
    _install_api(respx_router, state)

    first = await _run_full_flow(hass, synthetic_token)
    assert first["type"] == "create_entry"
    assert first["result"].unique_id == "acct-dup-0001"

    # A second flow for the SAME account UUID -- even with a different token --
    # must abort as already configured.
    duplicate = await _run_full_flow(hass, f"{synthetic_token}-other")
    assert duplicate["type"] == "abort"
    assert duplicate["reason"] == "already_configured"

    # A DIFFERENT account is accepted, proving the abort keys on the account
    # identifier and not on any shared state.
    state["account_id"] = "acct-dup-0002"
    accepted = await _run_full_flow(hass, f"{synthetic_token}-second")
    assert accepted["type"] == "create_entry"
    assert accepted["result"].unique_id == "acct-dup-0002"

    # FR-064: the abort message names the problem and is not a bare code.
    strings = json.loads(_STRINGS.read_text(encoding="utf-8"))
    message = strings["config"]["abort"]["already_configured"]
    assert message != "already_configured"
    assert "account" in message.casefold()
    assert message.endswith(".")
