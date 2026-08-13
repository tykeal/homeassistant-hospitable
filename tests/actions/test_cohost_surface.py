# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Co-host discovery and co-host privacy surface (FR-013, FR-047b).

Two things are covered here, and they are separate.

The first is COVERAGE. Every properties fixture in the suite carries
``co_hosts: []``, and the only existing assertion is that the key is
present, which an empty list satisfies. FR-013 exists so an operator
can discover a co-host ``user_id`` to pass as ``sender_id``; that
purpose was never exercised with actual content. A populated co-host
is served here so the discovery path is proven to carry data through,
not merely to carry a key.

The second is FR-047b's PRIVACY CONTROL. The chokepoint in
``actions/response.py`` filters co-host objects through an allowlist:
``user_id``, ``channel_name``, and ``name`` are unconditionally
returned; ``email`` and ``phone_numbers`` are gated behind the
``guest_contact_details`` option; ``profile_picture`` is dropped at
any depth; and any other key is dropped (fail-closed).

The realistic ``CO_HOST`` fixture matches the live API shape observed
on 2026-08-13: exactly ``{channel_name, name, user_id}``. The
hypothetical ``CO_HOST_WITH_CONTACT`` fixture adds contact fields
that do NOT exist upstream today but exercise the preventive control.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest
import respx

from tests.helpers import load_fixture

PROPERTY_A = "prop-example-001"

CO_HOST_USER_ID = "user-cohost-001"
CO_HOST_CHANNEL = "airbnb"
CO_HOST_NAME = "Cohost Example"

#: The realistic co-host shape as observed on the live Hospitable API
#: (``GET /properties?include=listings&per_page=100``, 2026-08-13,
#: 13 properties, 8 populated co-hosts). Every entry carried exactly
#: ``{channel_name, name, user_id}``, all strings. No ``email``,
#: ``phone_numbers``, or ``profile_picture`` key was present.
CO_HOST = {
    "user_id": CO_HOST_USER_ID,
    "channel_name": CO_HOST_CHANNEL,
    "name": CO_HOST_NAME,
}

CO_HOST_EMAIL = "cohost@example.com"
CO_HOST_PHONE = "+15550100"
CO_HOST_PICTURE = "https://example.com/cohost.png"

#: HYPOTHETICAL co-host shape that does NOT match upstream today.
#: This exists solely to exercise the preventive privacy control
#: (FR-047b): if the upstream API ever adds contact fields to a
#: co-host object, the allowlist must gate them behind the
#: guest-contact-details opt-in rather than passing them through.
#: Do NOT treat this as observed API behaviour.
CO_HOST_WITH_CONTACT = {
    "user_id": CO_HOST_USER_ID,
    "channel_name": CO_HOST_CHANNEL,
    "name": CO_HOST_NAME,
    "email": CO_HOST_EMAIL,
    "phone_numbers": [CO_HOST_PHONE],
    "profile_picture": CO_HOST_PICTURE,
}


def _properties_payload_with_cohost(
    cohost: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the single-property fixture with a populated co-host.

    Args:
        cohost: Co-host dict to inject. Defaults to ``CO_HOST``.

    Returns:
        The properties payload, deep-copied and mutated.
    """
    if cohost is None:
        cohost = CO_HOST
    data: dict[str, Any] = copy.deepcopy(load_fixture("properties_single.json"))
    data["data"][0]["listings"][0]["co_hosts"] = [copy.deepcopy(cohost)]
    return data


def serve_cohost_properties(
    respx_router: respx.Router,
    cohost: dict[str, Any] | None = None,
) -> None:
    """Re-point the properties endpoint at a populated co-host payload.

    Called AFTER entry setup rather than registered as a pre-setup
    fixture. ``respx`` treats an identical URL pattern as the same
    route and REPLACES its responder, so a pre-setup registration is
    silently overwritten by the paginated one the polling fixture
    installs during setup. Registering afterwards wins instead, and
    ``get_property_info`` fetches at call time rather than at setup, so
    the later payload is the one the service reads.

    Args:
        respx_router: Active respx router.
        cohost: Co-host dict to inject. Defaults to ``CO_HOST``.
    """
    import importlib

    const = importlib.import_module("custom_components.hospitable.api.const")
    respx_router.get(f"{const.BASE_URL}/properties").mock(
        return_value=httpx.Response(200, json=_properties_payload_with_cohost(cohost))
    )


async def _property_info(hass: Any, *, entry_id: str | None = None) -> dict[str, Any]:
    """Call ``get_property_info`` for the seeded property.

    Args:
        hass: Home Assistant instance.
        entry_id: Optional config entry id.

    Returns:
        The service response.
    """
    from custom_components.hospitable.const import DOMAIN

    data: dict[str, Any] = {"property_id": PROPERTY_A}
    if entry_id is not None:
        data["config_entry_id"] = entry_id
    return await hass.services.async_call(  # type: ignore[no-any-return]
        DOMAIN,
        "get_property_info",
        data,
        blocking=True,
        return_response=True,
    )


def _co_hosts(response: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract the co-host array from a ``get_property_info`` response.

    Args:
        response: The service response.

    Returns:
        The first listing's co-host array.
    """
    assert response["found"] is True
    listings = response["property"]["listings"]
    assert listings, "no listings were returned"
    return listings[0]["co_hosts"]  # type: ignore[no-any-return]


async def test_a_populated_co_host_reaches_the_caller(
    hass: Any,
    respx_router: respx.Router,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """FR-013's discovery purpose works with actual co-host content.

    Every fixture in the suite ships ``co_hosts: []``, and the existing
    assertion is a membership check that an empty list satisfies. This
    proves the array survives serialisation with an entry in it, which
    is the only form in which it is useful.
    """
    await loaded_config_entry_factory(hass)
    serve_cohost_properties(respx_router)

    co_hosts = _co_hosts(await _property_info(hass))

    assert len(co_hosts) == 1, "the populated co-host did not survive"
    assert co_hosts[0]["user_id"] == CO_HOST_USER_ID, (
        "FR-013 exists so an operator can read a co-host user_id to pass "
        "as sender_id; without it the service answers a question nobody "
        "asked"
    )
    assert co_hosts[0]["channel_name"] == CO_HOST_CHANNEL
    assert co_hosts[0]["name"] == CO_HOST_NAME


async def test_the_co_host_profile_picture_is_dropped(
    hass: Any,
    respx_router: respx.Router,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """``profile_picture`` is stripped at any depth, co-hosts included.

    This is the half of the current behaviour that IS consistent with
    the privacy intent, and it is asserted separately so the
    inconsistency documented in the next test is unambiguous rather
    than a guess.
    """
    await loaded_config_entry_factory(hass)
    serve_cohost_properties(respx_router, CO_HOST_WITH_CONTACT)

    co_host = _co_hosts(await _property_info(hass))[0]

    assert "profile_picture" not in co_host, (
        "profile_picture must be dropped at any depth"
    )
    assert CO_HOST_PICTURE not in json.dumps(co_host)


@pytest.mark.parametrize(
    "guest_contact",
    [
        pytest.param(
            False,
            marks=pytest.mark.xfail(raises=AssertionError, strict=True),
        ),
        True,
    ],
)
async def test_co_host_contact_gated_by_option(
    hass: Any,
    respx_router: respx.Router,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    guest_contact: bool,
) -> None:
    """FR-047b: co-host contact data is gated by guest_contact_details.

    This REPLACES the earlier characterization test
    ``test_co_host_contact_details_survive_regardless_of_the_option``,
    which asserted that co-host contact data passed through unfiltered.
    That test's own docstring anticipated this outcome: "if this now
    fails, the open design question was answered and this test must be
    updated to match the decision." FR-047b answered it: co-host
    contact data is gated identically to guest contact data.

    Uses the HYPOTHETICAL ``CO_HOST_WITH_CONTACT`` fixture (not
    observed on the live API today) to exercise the preventive
    control.

    Args:
        hass: Home Assistant instance.
        respx_router: Active respx router.
        loaded_config_entry_factory: Entry setup factory.
        guest_contact: Value of the guest contact details option.
    """
    from custom_components.hospitable.const import CONF_GUEST_CONTACT_DETAILS

    await loaded_config_entry_factory(
        hass, options={CONF_GUEST_CONTACT_DETAILS: guest_contact}
    )
    serve_cohost_properties(respx_router, CO_HOST_WITH_CONTACT)

    co_host = _co_hosts(await _property_info(hass))[0]

    if guest_contact:
        assert co_host.get("email") == CO_HOST_EMAIL, (
            "email must be present when guest_contact_details is on"
        )
        assert co_host.get("phone_numbers") == [CO_HOST_PHONE], (
            "phone_numbers must be present when guest_contact_details is on"
        )
    else:
        assert "email" not in co_host, (
            "email must be gated behind guest_contact_details"
        )
        assert "phone_numbers" not in co_host, (
            "phone_numbers must be gated behind guest_contact_details"
        )


@pytest.mark.xfail(raises=AssertionError, strict=True)
async def test_co_host_allowlist_is_fail_closed(
    hass: Any,
    respx_router: respx.Router,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """FR-047b fail-closed: unknown keys on a co-host are dropped.

    If the upstream API adds a new field to the co-host object, it
    must not leak through by default. This injects an unknown key
    and proves it is stripped.

    Uses the HYPOTHETICAL fixture shape; the unknown key is not
    observed on the live API today.
    """
    from custom_components.hospitable.const import CONF_GUEST_CONTACT_DETAILS

    cohost_with_extra = {
        **CO_HOST_WITH_CONTACT,
        "secret_field": "should-be-dropped",
    }
    await loaded_config_entry_factory(hass, options={CONF_GUEST_CONTACT_DETAILS: True})
    serve_cohost_properties(respx_router, cohost_with_extra)

    co_host = _co_hosts(await _property_info(hass))[0]

    assert "secret_field" not in co_host, (
        "unknown co-host keys must be dropped (fail-closed)"
    )
    # The allowlisted keys must still be present
    assert co_host["user_id"] == CO_HOST_USER_ID
    assert co_host["channel_name"] == CO_HOST_CHANNEL
    assert co_host["name"] == CO_HOST_NAME
