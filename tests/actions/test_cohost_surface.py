# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Co-host discovery and co-host privacy surface (FR-013, FR-047).

Two things are covered here, and they are separate.

The first is COVERAGE. Every properties fixture in the suite carries
``co_hosts: []``, and the only existing assertion is that the key is
present, which an empty list satisfies. FR-013 exists so an operator
can discover a co-host ``user_id`` to pass as ``sender_id``; that
purpose was never exercised with actual content. A populated co-host
is served here so the discovery path is proven to carry data through,
not merely to carry a key.

The second is a CHARACTERIZATION of an open design question, not an
assertion that current behaviour is correct. The privacy chokepoint in
``actions/response.py`` filters the ``guest`` container. A co-host is
not a guest, so a co-host's contact fields pass through untouched even
when the ``guest_contact_details`` option is OFF, while that same
co-host's ``profile_picture`` IS dropped, because ``profile_picture``
is stripped at any depth. The result is internally inconsistent: the
picture of a third party is considered sensitive and their email
address and phone number are not.

FR-047 governs GUEST data by its terms, so this is not a violation of
any written requirement, and it is deliberately NOT "fixed" here.
Filtering it would change a documented service contract, and
``get_property_info`` exists precisely to return co-host detail.
Whether the contact routes of a third party should be part of that
detail is a decision for the spec owner. These tests pin the behaviour
so the decision is made knowingly rather than discovered later, and
they will fail loudly if the behaviour changes either way.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

PROPERTY_A = "prop-example-001"

CO_HOST_USER_ID = "user-cohost-001"
CO_HOST_EMAIL = "cohost@example.com"
CO_HOST_PHONE = "+15550100"
CO_HOST_PICTURE = "https://example.com/cohost.png"

#: A co-host entry carrying the identifier FR-013 needs alongside the
#: contact fields whose handling is the open question. The shape mirrors
#: the platform-user shape the listing itself uses; the upstream co-host
#: shape is not documented in ``contracts/services.md``, so this is a
#: superset chosen to make the privacy question visible rather than a
#: claim about what Hospitable always returns.
CO_HOST = {
    "user_id": CO_HOST_USER_ID,
    "first_name": "Cohost",
    "last_name": "Example",
    "email": CO_HOST_EMAIL,
    "phone_numbers": [CO_HOST_PHONE],
    "profile_picture": CO_HOST_PICTURE,
}


def _properties_payload_with_cohost() -> dict[str, Any]:
    """Return the single-property fixture with a populated co-host.

    Returns:
        The properties payload, deep-copied and mutated.
    """
    fixture = Path("tests/fixtures/properties_single.json")
    payload = json.loads(fixture.read_text())
    data: dict[str, Any] = copy.deepcopy(payload)
    data["data"][0]["listings"][0]["co_hosts"] = [copy.deepcopy(CO_HOST)]
    return data


def serve_cohost_properties(respx_router: respx.Router) -> None:
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
    """
    import importlib

    const = importlib.import_module("custom_components.hospitable.api.const")
    respx_router.get(f"{const.BASE_URL}/properties").mock(
        return_value=httpx.Response(200, json=_properties_payload_with_cohost())
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
    serve_cohost_properties(respx_router)

    co_host = _co_hosts(await _property_info(hass))[0]

    assert "profile_picture" not in co_host, (
        "profile_picture must be dropped at any depth"
    )
    assert CO_HOST_PICTURE not in json.dumps(co_host)


@pytest.mark.parametrize("guest_contact", [False, True])
async def test_co_host_contact_details_survive_regardless_of_the_option(
    hass: Any,
    respx_router: respx.Router,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    guest_contact: bool,
) -> None:
    """CHARACTERIZATION of an open question, not an endorsement.

    A co-host's email address and phone number are returned whether the
    ``guest_contact_details`` option is on or off, because the
    chokepoint's identity filter keys on the ``guest`` container and a
    co-host is not a guest. Their profile picture is dropped in the
    same response.

    No written requirement is violated: FR-047 is scoped to guest data.
    But the surface is a third party's contact routes, and the option
    an installer would expect to govern "contact details" does not
    reach it. Pinned here, deliberately unfixed, and reported as a
    design decision for the spec owner.

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
    serve_cohost_properties(respx_router)

    co_host = _co_hosts(await _property_info(hass))[0]

    assert co_host.get("email") == CO_HOST_EMAIL, (
        "co-host email is currently unfiltered; if this now fails, the "
        "open design question was answered and this test must be "
        "updated to match the decision"
    )
    assert co_host.get("phone_numbers") == [CO_HOST_PHONE], (
        "co-host phone numbers are currently unfiltered; see above"
    )
