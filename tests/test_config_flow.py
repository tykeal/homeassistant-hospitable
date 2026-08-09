# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Behavioral tests for the Hospitable config flow."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.data_entry_flow import UnknownStep

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    CONF_TOKEN,
    DOMAIN,
)
from tests.helpers import load_fixture


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T041 validates token and fetches properties",
)
async def test_user_step_validates_token_and_fetches_properties(
    hass: Any, respx_router: Any, synthetic_token: str
) -> None:
    """Validate the token with /user and fetch real properties for selection."""
    user_route = respx_router.get(f"{BASE_URL}/user").respond(
        json=load_fixture("user.json")
    )
    properties_route = respx_router.get(f"{BASE_URL}/properties").respond(
        json=load_fixture("properties_single.json")
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: synthetic_token}
    )

    assert user_route.called
    assert properties_route.called
    assert result["type"] == "form"
    assert result["step_id"] == "properties"
    property_schema = result["data_schema"].schema[CONF_SELECTED_PROPERTIES]
    assert "prop-example-001" in property_schema.config["options"]


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T041 creates UUID-namespaced entry",
)
async def test_property_step_creates_account_uuid_namespaced_entry(
    hass: Any, respx_router: Any, synthetic_token: str
) -> None:
    """Create an entry whose unique ID and namespace come from /user data.id."""
    respx_router.get(f"{BASE_URL}/user").respond(json=load_fixture("user.json"))
    respx_router.get(f"{BASE_URL}/properties").respond(
        json=load_fixture("properties_single.json")
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={CONF_TOKEN: synthetic_token}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_SELECTED_PROPERTIES: ["prop-example-001"]}
    )

    assert result["type"] == "create_entry"
    assert result["result"].unique_id == "acct-example-0001"
    assert result["data"][CONF_ACCOUNT_NAMESPACE] == "acct-example-0001"
    assert result["data"][CONF_NAMESPACE_SOURCE] == "account"
    assert result["data"][CONF_ACCOUNT_NAMESPACE] != "pending"
    assert result["options"][CONF_SELECTED_PROPERTIES] == ["prop-example-001"]


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T041 rejects invalid token",
)
async def test_user_step_maps_401_to_invalid_auth(
    hass: Any, respx_router: Any, synthetic_token: str
) -> None:
    """Keep the user form editable when /user rejects the token."""
    user_route = respx_router.get(f"{BASE_URL}/user").respond(
        status_code=401, json=load_fixture("error_401.json")
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={CONF_TOKEN: synthetic_token}
    )

    assert user_route.called
    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.xfail(
    raises=AssertionError,
    strict=True,
    reason="TDD red phase: T041 aborts duplicate account",
)
async def test_user_step_aborts_duplicate_account(
    hass: Any, respx_router: Any, synthetic_token: str
) -> None:
    """Abort a second entry for the same account UUID."""
    respx_router.get(f"{BASE_URL}/user").respond(json=load_fixture("user.json"))
    respx_router.get(f"{BASE_URL}/properties").respond(
        json=load_fixture("properties_single.json")
    )

    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={CONF_TOKEN: synthetic_token}
    )
    await hass.config_entries.flow.async_configure(
        first["flow_id"], {CONF_SELECTED_PROPERTIES: ["prop-example-001"]}
    )
    second = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={CONF_TOKEN: "different-token"}
    )

    assert second["type"] == "abort"
    assert second["reason"] == "already_configured"


@pytest.mark.xfail(
    raises=UnknownStep,
    strict=True,
    reason="TDD red phase: T041 reauth preserves account namespace",
)
async def test_reauth_replaces_token_for_same_account_only(
    hass: Any, respx_router: Any, synthetic_token: str
) -> None:
    """Replace only the token during reauth for the same account UUID."""
    respx_router.get(f"{BASE_URL}/user").respond(json=load_fixture("user.json"))
    respx_router.get(f"{BASE_URL}/properties").respond(
        json=load_fixture("properties_single.json")
    )
    setup = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}, data={CONF_TOKEN: synthetic_token}
    )
    created = await hass.config_entries.flow.async_configure(
        setup["flow_id"], {CONF_SELECTED_PROPERTIES: ["prop-example-001"]}
    )
    entry = created["result"]

    reauth = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "reauth", "entry_id": entry.entry_id},
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        reauth["flow_id"], {CONF_TOKEN: "replacement-token"}
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == "replacement-token"
    assert entry.data[CONF_ACCOUNT_NAMESPACE] == "acct-example-0001"
