# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for the three lookup services (T067-T071).

``find_reservation``, ``get_reservations``, and ``get_property_info``
are GET-only. Not-found is a RETURN VALUE everywhere — an explicit
``found: false`` — and never an exception, so an automation can branch
on it without a try/except. API failures still raise, which is the
distinction these tests hold apart: a handler that swallowed every
failure into ``found: false`` would satisfy the not-found tests and be
wrong.

``include=guest`` is SINGULAR. Unrecognised include NAMES are silently
ignored upstream, so the code must ASSERT the expected key is present
rather than assume the include was honoured (spec 001 FR-075).

As in ``test_get_messages.py``, every test drives the real service bus
and asserts registration first, so the red phase fails with a genuine
``AssertionError`` rather than an import error. This is a disclosed
deviation from the ``raises=ModuleNotFoundError`` in tasks.md.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest

from tests.actions.conftest import (
    SECOND_ACCOUNT_NAMESPACE,
    SECOND_TOKEN,
)

PROPERTY_A = "prop-example-001"
PROPERTY_B = "prop-example-002"
UNKNOWN_PROPERTY = "prop-example-999"
RESERVATION_WITH_GUEST = "res-example-guest-full"

LOOKUP_SERVICES = ("find_reservation", "get_reservations", "get_property_info")


async def _call(hass: Any, service: str, data: dict[str, Any]) -> Any:
    """Invoke one lookup service through the real service bus.

    Args:
        hass: Home Assistant instance.
        service: Service name to call.
        data: Service call data.

    Returns:
        The service response.
    """
    from custom_components.hospitable.const import DOMAIN

    assert hass.services.has_service(DOMAIN, service), (
        f"hospitable.{service} is not registered"
    )
    return await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=True
    )


def _single_reservation(index: int = 0) -> dict[str, Any]:
    """Return a single-reservation detail envelope built from a fixture.

    Args:
        index: Which reservation of the guest fixture to wrap.

    Returns:
        A ``{"data": {...}}`` envelope, the shape the detail endpoint
        returns.
    """
    from tests.helpers import load_fixture

    return {"data": load_fixture("reservation_with_guest.json")["data"][index]}


async def test_find_reservation_returns_the_reservation(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    lookup_routes: Any,
) -> None:
    """A known UUID returns the reservation payload."""
    payload = _single_reservation()
    route = lookup_routes.reservation(RESERVATION_WITH_GUEST, json_body=payload)
    await loaded_config_entry_factory(hass)

    response = await _call(
        hass, "find_reservation", {"reservation_uuid": RESERVATION_WITH_GUEST}
    )

    assert route.called
    assert response["found"] is True
    reservation = response["reservation"]
    assert reservation["id"] == RESERVATION_WITH_GUEST
    assert reservation["code"] == payload["data"]["code"]
    assert reservation["guest"]["first_name"] == "Example"


async def test_find_reservation_requests_the_guest_include(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    lookup_routes: Any,
    respx_router: Any,
) -> None:
    """The include is SINGULAR ``guest``, and is verified as honoured.

    Plural ``guests`` is a silently-ignored no-op upstream, so asserting
    the exact parameter matters.
    """
    lookup_routes.reservation(RESERVATION_WITH_GUEST, json_body=_single_reservation())
    await loaded_config_entry_factory(hass)
    before = len(respx_router.calls)

    await _call(hass, "find_reservation", {"reservation_uuid": RESERVATION_WITH_GUEST})

    issued = [
        call
        for call in list(respx_router.calls)[before:]
        if call.request.url.path.endswith(f"/reservations/{RESERVATION_WITH_GUEST}")
    ]
    assert issued, "no reservation detail request was issued"
    include = issued[0].request.url.params.get("include", "")
    parts = [part.strip() for part in include.split(",")]
    assert "guest" in parts, f"include did not request guest: {include!r}"
    assert "guests" not in parts, "plural guests is a silently-ignored no-op"


async def test_find_reservation_rejects_a_dishonoured_include(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    lookup_routes: Any,
) -> None:
    """A response without the requested key is an error, not a silence.

    Unrecognised include names are silently ignored upstream, so a
    missing key must be detected rather than assumed honoured.
    """
    from homeassistant.exceptions import HomeAssistantError

    payload = _single_reservation()
    payload["data"].pop("guest")
    lookup_routes.reservation(RESERVATION_WITH_GUEST, json_body=payload)
    await loaded_config_entry_factory(hass)

    with pytest.raises(HomeAssistantError):
        await _call(
            hass, "find_reservation", {"reservation_uuid": RESERVATION_WITH_GUEST}
        )


async def test_find_reservation_tolerates_a_missing_surname(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    lookup_routes: Any,
) -> None:
    """One live guest in twenty-nine genuinely has no ``last_name``."""
    payload = _single_reservation(1)
    assert "last_name" not in payload["data"]["guest"]
    lookup_routes.reservation("res-example-guest-no-surname", json_body=payload)
    await loaded_config_entry_factory(hass)

    response = await _call(
        hass, "find_reservation", {"reservation_uuid": "res-example-guest-no-surname"}
    )

    assert response["found"] is True
    assert response["reservation"]["guest"]["first_name"] == "Anonymous"
    assert "last_name" not in response["reservation"]["guest"]


async def test_get_reservations_returns_the_window(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    lookup_routes: Any,
    respx_router: Any,
) -> None:
    """Reservations for one property are returned with their filters."""
    from tests.helpers import load_fixture

    payload = load_fixture("reservation_with_guest.json")
    route = lookup_routes.reservations(json_body=payload)
    await loaded_config_entry_factory(hass)
    before = len(respx_router.calls)

    response = await _call(hass, "get_reservations", {"property_id": PROPERTY_A})

    assert route.called
    assert response["found"] is True
    assert response["property_id"] == PROPERTY_A
    assert [item["id"] for item in response["reservations"]] == [
        item["id"] for item in payload["data"]
    ]
    issued = [
        call
        for call in list(respx_router.calls)[before:]
        if call.request.url.path.endswith("/reservations")
    ]
    assert issued, "no reservations request was issued"
    params = issued[0].request.url.params
    assert params.get_list("properties[]") == [PROPERTY_A]
    assert params.get("start_date")
    assert params.get("end_date")


async def test_get_reservations_reports_an_unknown_property(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    lookup_routes: Any,
) -> None:
    """A property this account does not hold is ``found: false``.

    The distinction that matters: "no such property" and "this property
    has no bookings in the window" are DIFFERENT answers, and a caller
    must be able to tell them apart.
    """
    from tests.helpers import load_fixture

    lookup_routes.reservations(json_body=load_fixture("reservation_with_guest.json"))
    await loaded_config_entry_factory(hass)

    response = await _call(hass, "get_reservations", {"property_id": UNKNOWN_PROPERTY})

    assert response["found"] is False
    assert response["reservations"] == []


async def test_get_reservations_returns_an_empty_window_as_found(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    lookup_routes: Any,
) -> None:
    """A known property with no bookings is found, with no reservations."""
    lookup_routes.reservations(
        json_body={
            "data": [],
            "meta": {"current_page": 1, "last_page": 1, "per_page": 100, "total": 0},
        }
    )
    await loaded_config_entry_factory(hass)

    response = await _call(hass, "get_reservations", {"property_id": PROPERTY_B})

    assert response["found"] is True
    assert response["reservations"] == []


async def test_get_property_info_returns_listings_and_co_hosts(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """Listings carry the co-host identifiers FR-013 depends on."""
    await loaded_config_entry_factory(hass)

    response = await _call(hass, "get_property_info", {"property_id": PROPERTY_A})

    assert response["found"] is True
    prop = response["property"]
    assert prop["id"] == PROPERTY_A
    assert prop["name"] == "Example Beach House"
    listings = prop["listings"]
    assert listings, "no listings were returned"
    assert listings[0]["platform"] == "airbnb"
    assert "co_hosts" in listings[0], "co-host identifiers are required by FR-013"


async def test_get_property_info_reports_an_unknown_property(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """An unknown property id is ``found: false``, not an exception."""
    await loaded_config_entry_factory(hass)

    response = await _call(hass, "get_property_info", {"property_id": UNKNOWN_PROPERTY})

    assert response["found"] is False
    assert response["property"] is None


async def test_find_reservation_reports_not_found_as_a_value(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    lookup_routes: Any,
) -> None:
    """A 404 becomes ``found: false``, never an exception."""
    from tests.helpers import load_fixture

    lookup_routes.reservation(
        "res-example-absent", status=404, json_body=load_fixture("error_404.json")
    )
    await loaded_config_entry_factory(hass)

    response = await _call(
        hass, "find_reservation", {"reservation_uuid": "res-example-absent"}
    )

    assert response["found"] is False
    assert response["reservation"] is None


@pytest.mark.parametrize("service", LOOKUP_SERVICES)
async def test_api_failures_still_raise(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    respx_router: Any,
    service: str,
) -> None:
    """A transport failure raises rather than reporting not-found.

    This is the guard that stops ``found: false`` from becoming a
    catch-all that hides a broken integration.
    """
    from homeassistant.exceptions import HomeAssistantError

    from custom_components.hospitable.api.const import BASE_URL

    respx_router.get(f"{BASE_URL}/reservations/res-example-boom").mock(
        side_effect=httpx.ConnectError("synthetic transport failure")
    )
    await loaded_config_entry_factory(hass)
    for route in respx_router.routes:
        route.mock(side_effect=httpx.ConnectError("synthetic transport failure"))
    data = (
        {"reservation_uuid": "res-example-boom"}
        if service == "find_reservation"
        else {"property_id": PROPERTY_A}
    )

    with pytest.raises(HomeAssistantError):
        await _call(hass, service, data)


@pytest.mark.parametrize("service", LOOKUP_SERVICES)
async def test_config_entry_id_is_required_when_ambiguous(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    service: str,
) -> None:
    """Two loaded accounts make ``config_entry_id`` mandatory.

    The same disambiguation rules proven for ``send_message`` in T029
    apply to every lookup service.
    """
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.hospitable.const import DOMAIN

    await loaded_config_entry_factory(hass)
    await loaded_config_entry_factory(
        hass, token=SECOND_TOKEN, account=SECOND_ACCOUNT_NAMESPACE
    )
    data = (
        {"reservation_uuid": RESERVATION_WITH_GUEST}
        if service == "find_reservation"
        else {"property_id": PROPERTY_A}
    )

    assert hass.services.has_service(DOMAIN, service), (
        f"hospitable.{service} is not registered"
    )
    with pytest.raises(ServiceValidationError):
        await _call(hass, service, data)


@pytest.mark.parametrize("service", LOOKUP_SERVICES)
async def test_an_explicit_config_entry_id_disambiguates(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    lookup_routes: Any,
    service: str,
) -> None:
    """Naming the account resolves the ambiguity rather than failing."""
    from tests.helpers import load_fixture

    lookup_routes.reservation(RESERVATION_WITH_GUEST, json_body=_single_reservation())
    lookup_routes.reservations(json_body=load_fixture("reservation_with_guest.json"))
    first = await loaded_config_entry_factory(hass)
    await loaded_config_entry_factory(
        hass, token=SECOND_TOKEN, account=SECOND_ACCOUNT_NAMESPACE
    )
    data: dict[str, Any] = {"config_entry_id": first.entry_id}
    data |= (
        {"reservation_uuid": RESERVATION_WITH_GUEST}
        if service == "find_reservation"
        else {"property_id": PROPERTY_A}
    )

    response = await _call(hass, service, data)

    assert response["found"] is True


@pytest.mark.parametrize("service", LOOKUP_SERVICES)
async def test_an_unknown_config_entry_id_is_rejected(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
    service: str,
) -> None:
    """An entry id that names no loaded account is user-correctable."""
    from homeassistant.exceptions import ServiceValidationError

    await loaded_config_entry_factory(hass)
    data: dict[str, Any] = {"config_entry_id": "not-a-real-entry"}
    data |= (
        {"reservation_uuid": RESERVATION_WITH_GUEST}
        if service == "find_reservation"
        else {"property_id": PROPERTY_A}
    )

    with pytest.raises(ServiceValidationError):
        await _call(hass, service, data)


@pytest.mark.parametrize("service", LOOKUP_SERVICES)
def test_no_lookup_handler_builds_a_write_client(service: str) -> None:
    """The lookup handlers read with the GET-only client.

    Write-isolation gate 3 extended to the new READ services. These are
    GET-only by contract, so a reference to the write client or to
    ``_post`` in any of them is a defect regardless of what it is used
    for.
    """
    from pathlib import Path

    from tests.helpers.ast_isolation import scan_module

    module = Path(f"custom_components/hospitable/actions/{service}.py")
    assert module.is_file(), f"the {service} handler does not exist"
    facts = scan_module(module)
    assert not facts.references("HospitableWriteClient")
    assert not facts.references("_post")
