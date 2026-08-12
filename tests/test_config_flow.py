# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Behavioral tests for the Hospitable config flow."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.data_entry_flow import InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    CONF_TOKEN,
    DOMAIN,
)
from tests.helpers import load_fixture


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
    selector = next(iter(result["data_schema"].schema.values()))
    assert {option["value"] for option in selector.config["options"]} == {
        "prop-example-001"
    }


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
    assert result["options"][CONF_SELECTED_PROPERTIES] == ["prop-example-001"]


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


# --- US3 guest-contact-details options toggle (T096, FR-038b) -----------
#
# ``config_flow.py``, ``strings.json`` and ``translations/en.json`` all
# already exist, so these fail on real behaviour rather than on imports.

_RED_TOGGLE = "TDD red phase: T096 the guest-contact toggle does not exist"


def _guest_entry() -> MockConfigEntry:
    """Build a loaded-looking entry with one selected property."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_TOKEN: "hp_test_synthetic_token_000000000000000000000000",
            CONF_ACCOUNT_NAMESPACE: "acct-example-0001",
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            CONF_SELECTED_PROPERTIES: ["prop-example-001"],
            "reservation_interval_minutes": 5,
            "property_interval_minutes": 60,
            "lookback_days": 90,
            "lookahead_days": 90,
        },
        unique_id="acct-example-0001",
    )


def _guest_base_input() -> dict[str, Any]:
    """Return otherwise-valid options-flow input."""
    return {
        CONF_SELECTED_PROPERTIES: ["prop-example-001"],
        "reservation_interval_minutes": 5,
        "property_interval_minutes": 60,
        "lookback_days": 90,
        "lookahead_days": 90,
    }


@pytest.mark.xfail(raises=AssertionError, strict=True, reason=_RED_TOGGLE)
async def test_options_flow_offers_the_guest_contact_toggle(hass: Any) -> None:
    """The options form exposes the guest-contact-details field."""
    from custom_components.hospitable.const import CONF_GUEST_CONTACT_DETAILS

    entry = _guest_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    keys = {str(key) for key in result["data_schema"].schema}
    assert CONF_GUEST_CONTACT_DETAILS in keys


@pytest.mark.xfail(raises=AssertionError, strict=True, reason=_RED_TOGGLE)
async def test_the_guest_contact_toggle_defaults_to_disabled(hass: Any) -> None:
    """Submitting the form untouched leaves the opt-in OFF (FR-038b).

    Default OFF is a requirement, not a preference, so the default is
    asserted through a real submission rather than by reading a
    constant.
    """
    from custom_components.hospitable.const import CONF_GUEST_CONTACT_DETAILS

    entry = _guest_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _guest_base_input()
    )

    assert result["type"] == "create_entry"
    assert CONF_GUEST_CONTACT_DETAILS in result["data"], "the option is not persisted"
    assert result["data"][CONF_GUEST_CONTACT_DETAILS] is False


@pytest.mark.xfail(raises=AssertionError, strict=True, reason=_RED_TOGGLE)
async def test_enabling_the_guest_contact_toggle_persists(hass: Any) -> None:
    """An explicit opt-in is stored on the entry options."""
    from custom_components.hospitable.const import CONF_GUEST_CONTACT_DETAILS

    entry = _guest_entry()
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    user_input = _guest_base_input()
    user_input[CONF_GUEST_CONTACT_DETAILS] = True
    # A schema that does not know the field rejects the submission
    # outright; that is converted here so the red phase fails with a
    # plain assertion about the missing option rather than a voluptuous
    # error type.
    submitted: dict[str, Any] | None = None
    try:
        submitted = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input
        )
    except InvalidData:
        submitted = None
    assert submitted is not None, "the options schema rejects the guest-contact field"
    result = submitted

    assert result["type"] == "create_entry"
    assert CONF_GUEST_CONTACT_DETAILS in result["data"], "the option is not persisted"
    assert result["data"][CONF_GUEST_CONTACT_DETAILS] is True


@pytest.mark.parametrize(
    "relative_path",
    [
        "custom_components/hospitable/strings.json",
        "custom_components/hospitable/translations/en.json",
    ],
)
@pytest.mark.xfail(raises=AssertionError, strict=True, reason=_RED_TOGGLE)
def test_the_toggle_states_its_privacy_implication(relative_path: str) -> None:
    """Both string files label the toggle and explain what it exposes.

    A toggle that says only "guest contact details" does not tell a user
    that enabling it writes an email address and a phone number into
    entity attributes visible on a dashboard.
    """
    import json
    from pathlib import Path

    data = json.loads(Path(relative_path).read_text(encoding="utf-8"))
    init_step = data["options"]["step"]["init"]

    assert "guest_contact_details" in init_step["data"], "the field has no label"

    description = " ".join(
        [
            str(init_step.get("description", "")),
            str(init_step["data"]["guest_contact_details"]),
            str(init_step.get("data_description", {}).get("guest_contact_details", "")),
        ]
    ).lower()

    assert "email" in description
    assert "phone" in description
    assert "attribute" in description
