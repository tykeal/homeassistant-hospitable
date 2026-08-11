# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Reauth with a different account aborts (FR-013, FR-014).

A reauthentication whose replacement token belongs to a DIFFERENT account
must abort with ``wrong_account`` rather than silently re-pointing the
entry at another account, and the stored token must be left untouched. A
reauth for the SAME account still succeeds and replaces the token. This
asserts no new production behavior -- US1 already compares the ``/user``
UUID against the stored namespace -- so per Principle XII Exemptions it
carries no red-phase commit. It also verifies the ``wrong_account`` message
is actionable (FR-064).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
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


async def test_reauth_with_different_account_aborts(
    hass: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """Reauth aborts when the replacement token is a different account."""
    state: dict[str, Any] = {"account_id": "acct-reauth-0001"}
    _install_api(respx_router, state)

    setup = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={CONF_TOKEN: synthetic_token}
    )
    created = await hass.config_entries.flow.async_configure(
        setup["flow_id"], {CONF_SELECTED_PROPERTIES: ["prop-example-001"]}
    )
    entry = created["result"]
    assert entry.unique_id == "acct-reauth-0001"

    # The replacement token authenticates as a DIFFERENT account.
    state["account_id"] = "acct-reauth-9999"
    reauth = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        reauth["flow_id"], {CONF_TOKEN: f"{synthetic_token}-wrong"}
    )

    # The flow must abort and must NOT re-point the entry at the new account.
    assert result["type"] == "abort"
    assert result["reason"] == "wrong_account"
    assert entry.data[CONF_TOKEN] == synthetic_token
    assert entry.data[CONF_ACCOUNT_NAMESPACE] == "acct-reauth-0001"
    assert entry.unique_id == "acct-reauth-0001"

    # A reauth for the SAME account still succeeds and swaps the token.
    state["account_id"] = "acct-reauth-0001"
    reauth_ok = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    ok = await hass.config_entries.flow.async_configure(
        reauth_ok["flow_id"], {CONF_TOKEN: f"{synthetic_token}-fresh"}
    )
    assert ok["type"] == "abort"
    assert ok["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == f"{synthetic_token}-fresh"
    assert entry.data[CONF_ACCOUNT_NAMESPACE] == "acct-reauth-0001"

    # FR-064: the wrong-account message explains what happened, not a code.
    strings = json.loads(_STRINGS.read_text(encoding="utf-8"))
    message = strings["config"]["abort"]["wrong_account"]
    assert message != "wrong_account"
    assert "different account" in message.casefold()
    assert message.endswith(".")
