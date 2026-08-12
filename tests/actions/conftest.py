# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the Hospitable action (service-call) tests.

This module MUST NOT import any ``custom_components.hospitable`` module
at module scope. A module-level import of a not-yet-existing module in a
``conftest.py`` breaks collection for the whole directory, where no
``xfail`` marker can rescue it (Constitution Principle XII). Every
fixture that needs an integration object is therefore a FACTORY fixture
returning a callable that performs its import inside its own body.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest
import respx

ACCOUNT_NAMESPACE = "acct-example-0001"
SECOND_ACCOUNT_NAMESPACE = "acct-example-0002"
RESERVATION_A = "res-example-accepted"
RESERVATION_B = "res-example-second"
SYNTHETIC_TOKEN = "hp_test_synthetic_token_000000000000000000000000"
SECOND_TOKEN = "hp_test_synthetic_token_111111111111111111111111"


class MessagesRouteBuilder:
    """Build ``respx`` routes for the reservation messages endpoint.

    Every response can carry ``x-ratelimit-limit``,
    ``x-ratelimit-remaining``, and ``x-ratelimit-reset`` headers, and a
    429 can carry ``retry-after`` plus the observed Laravel body. Routes
    are registered per reservation UUID so two reservations hold
    INDEPENDENT header budgets, matching the observed per-reservation
    bucketing (T013, T013a, T013b).
    """

    def __init__(self, router: respx.Router, base_url: str) -> None:
        """Store the router and API base URL used to build routes.

        Args:
            router: Active respx router.
            base_url: Hospitable API base URL.
        """
        self._router = router
        self._base_url = base_url

    def url(self, reservation_uuid: str) -> str:
        """Return the messages endpoint URL for one reservation.

        Args:
            reservation_uuid: Target reservation UUID.

        Returns:
            Fully qualified messages endpoint URL.
        """
        return f"{self._base_url}/reservations/{reservation_uuid}/messages"

    @staticmethod
    def headers(
        *,
        limit: int | None = 2,
        remaining: int | None = None,
        reset: int | None = None,
        retry_after: int | None = None,
    ) -> dict[str, str]:
        """Build rate-limit headers, omitting any value left as None.

        Args:
            limit: ``x-ratelimit-limit`` value.
            remaining: ``x-ratelimit-remaining`` value.
            reset: ``x-ratelimit-reset`` unix epoch value.
            retry_after: ``retry-after`` seconds value.

        Returns:
            Header mapping with only the supplied values present.
        """
        built: dict[str, str] = {}
        if limit is not None:
            built["x-ratelimit-limit"] = str(limit)
        if remaining is not None:
            built["x-ratelimit-remaining"] = str(remaining)
        if reset is not None:
            built["x-ratelimit-reset"] = str(reset)
        if retry_after is not None:
            built["retry-after"] = str(retry_after)
        return built

    def post(
        self,
        reservation_uuid: str,
        *,
        status: int = 202,
        json_body: Any = None,
        content: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> respx.Route:
        """Register one POST response for a reservation.

        Args:
            reservation_uuid: Target reservation UUID.
            status: HTTP status to return.
            json_body: JSON body to return, when not None.
            content: Raw body to return instead of JSON.
            headers: Response headers to attach.

        Returns:
            The registered respx route.
        """
        kwargs: dict[str, Any] = {"headers": headers or {}}
        if content is not None:
            kwargs["content"] = content
        elif json_body is not None:
            kwargs["json"] = json_body
        route = self._router.post(self.url(reservation_uuid))
        route.mock(return_value=httpx.Response(status, **kwargs))
        return route

    def post_sequence(
        self, reservation_uuid: str, responses: list[httpx.Response]
    ) -> respx.Route:
        """Register an ordered sequence of POST responses.

        Args:
            reservation_uuid: Target reservation UUID.
            responses: Responses returned in order.

        Returns:
            The registered respx route.
        """
        route = self._router.post(self.url(reservation_uuid))
        route.mock(side_effect=list(responses))
        return route

    def get(
        self,
        reservation_uuid: str,
        *,
        status: int = 200,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> respx.Route:
        """Register one GET response for a reservation thread.

        Args:
            reservation_uuid: Target reservation UUID.
            status: HTTP status to return.
            json_body: JSON body to return.
            headers: Response headers to attach.

        Returns:
            The registered respx route.
        """
        route = self._router.get(self.url(reservation_uuid))
        route.mock(
            return_value=httpx.Response(status, json=json_body, headers=headers or {})
        )
        return route

    def throttled_response(
        self, *, retry_after: int = 60, reset: int | None = None
    ) -> httpx.Response:
        """Build the observed 429 response.

        Args:
            retry_after: ``retry-after`` seconds value.
            reset: ``x-ratelimit-reset`` unix epoch value.

        Returns:
            A 429 response carrying the observed Laravel body, which has
            NO ``errors`` key.
        """
        from tests.helpers import load_fixture

        return httpx.Response(
            429,
            json=load_fixture("error_envelope_429.json"),
            headers=self.headers(
                limit=2, remaining=0, reset=reset, retry_after=retry_after
            ),
        )


@pytest.fixture
def messages_routes(respx_router: respx.Router) -> MessagesRouteBuilder:
    """Return a messages-endpoint route builder bound to the router.

    Args:
        respx_router: Active respx router.

    Returns:
        Route builder for the reservation messages endpoint.
    """
    const = importlib.import_module("custom_components.hospitable.api.const")
    return MessagesRouteBuilder(respx_router, const.BASE_URL)


@pytest.fixture
def write_client_factory() -> Callable[[httpx.AsyncClient, str], Any]:
    """Return a factory importing the write client only when called.

    Returns:
        Callable building a ``HospitableWriteClient``.
    """

    def _factory(http_client: httpx.AsyncClient, token: str) -> Any:
        """Build a write client from an HTTP client and token.

        Args:
            http_client: Async HTTP client to reuse.
            token: Synthetic personal access token.

        Returns:
            A configured write client instance.
        """
        auth = importlib.import_module("custom_components.hospitable.api.auth")
        write_client = importlib.import_module(
            "custom_components.hospitable.api.write_client"
        )
        return write_client.HospitableWriteClient(
            auth.StaticTokenProvider(token), http_client
        )

    return _factory


@pytest.fixture
def service_call_factory() -> Callable[..., Any]:
    """Return a factory building Home Assistant ``ServiceCall`` objects.

    Returns:
        Callable building a service call for the Hospitable domain.
    """

    def _factory(hass: Any, data: dict[str, Any], *, service: str) -> Any:
        """Build a service call for the Hospitable domain.

        Args:
            hass: Home Assistant instance.
            data: Service call data.
            service: Service name being invoked.

        Returns:
            A ``ServiceCall`` bound to the Hospitable domain.
        """
        core = importlib.import_module("homeassistant.core")
        const = importlib.import_module("custom_components.hospitable.const")
        return core.ServiceCall(
            hass, const.DOMAIN, service, dict(data), return_response=True
        )

    return _factory


def mock_polling_endpoints(router: respx.Router, base_url: str) -> None:
    """Mock every GET endpoint the polling lifecycle needs.

    Args:
        router: Active respx router.
        base_url: Hospitable API base URL.
    """
    from tests.helpers import load_fixture

    def _properties(request: httpx.Request) -> httpx.Response:
        """Return the paginated properties fixture for the page asked for.

        Args:
            request: Captured request.

        Returns:
            The matching properties page.
        """
        page = request.url.params.get("page", "1")
        fixture = "properties_page2.json" if page == "2" else "properties_page1.json"
        return httpx.Response(200, json=load_fixture(fixture))

    router.get(f"{base_url}/properties").mock(side_effect=_properties)
    router.get(f"{base_url}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )
    for property_id, fixture in (
        ("prop-example-001", "calendar_prop1.json"),
        ("prop-example-002", "calendar_prop2.json"),
    ):
        router.get(f"{base_url}/properties/{property_id}/calendar").mock(
            return_value=httpx.Response(200, json=load_fixture(fixture))
        )


@pytest.fixture
def loaded_config_entry_factory(
    respx_router: respx.Router,
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Return a factory that sets up a fully loaded config entry.

    Args:
        respx_router: Active respx router.

    Returns:
        Async callable returning a loaded ``MockConfigEntry``.
    """

    async def _factory(
        hass: Any,
        *,
        token: str = SYNTHETIC_TOKEN,
        account: str = ACCOUNT_NAMESPACE,
        options: dict[str, Any] | None = None,
    ) -> Any:
        """Set up one Hospitable config entry against mocked endpoints.

        Args:
            hass: Home Assistant instance.
            token: Synthetic personal access token.
            account: Account namespace for the entry.
            options: Extra config entry options.

        Returns:
            The loaded ``MockConfigEntry``.
        """
        common = importlib.import_module("pytest_homeassistant_custom_component.common")
        api_const = importlib.import_module("custom_components.hospitable.api.const")
        const = importlib.import_module("custom_components.hospitable.const")
        mock_polling_endpoints(respx_router, api_const.BASE_URL)
        entry = common.MockConfigEntry(
            domain=const.DOMAIN,
            data={
                const.CONF_TOKEN: token,
                const.CONF_ACCOUNT_NAMESPACE: account,
                const.CONF_NAMESPACE_SOURCE: "account",
            },
            options={
                const.CONF_SELECTED_PROPERTIES: [
                    "prop-example-001",
                    "prop-example-002",
                ],
                const.CONF_LOOKAHEAD_DAYS: 30,
            }
            | (options or {}),
            unique_id=account,
        )
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        return entry

    return _factory


@pytest.fixture
def seed_reservations() -> Callable[..., list[Any]]:
    """Return a factory seeding a loaded entry's reservation cache.

    The reservation fixtures are dated in the past, so a live coordinator
    refresh would filter them out of its rolling window. Seeding the
    cache directly models "this reservation is known to the coordinator"
    without pinning the tests to a moving date window.

    Returns:
        Callable seeding the reservations coordinator cache.
    """

    def _factory(
        entry: Any,
        fixture: str = "reservation_with_guest.json",
        *,
        seed_only: bool = False,
    ) -> list[Any]:
        """Seed the reservations coordinator cache from a fixture.

        Args:
            entry: A loaded Hospitable config entry.
            fixture: Fixture file holding a reservations payload.
            seed_only: Return the models without touching the cache, for
                callers that push them through the coordinator instead.

        Returns:
            The seeded reservation models.
        """
        from tests.helpers import load_fixture

        models = importlib.import_module("custom_components.hospitable.api.models")
        payload = load_fixture(fixture)
        reservations = [
            models.HospitableReservation.from_api(item) for item in payload["data"]
        ]
        if not seed_only:
            entry.runtime_data["coordinators"]["reservations"].data = reservations
        return reservations

    return _factory


class LookupRouteBuilder:
    """Build ``respx`` routes for the READ-ONLY lookup endpoints.

    The lookup services and the polling lifecycle share two endpoints,
    so the routes here are distinguished by the ``include`` parameter the
    services send. They MUST be registered BEFORE the config entry is set
    up: ``respx`` matches routes in registration order, and the polling
    routes are registered during setup with a broader pattern that would
    otherwise win.
    """

    def __init__(self, router: respx.Router, base_url: str) -> None:
        """Store the router and API base URL used to build routes.

        Args:
            router: Active respx router.
            base_url: Hospitable API base URL.
        """
        self._router = router
        self._base_url = base_url

    def reservation(
        self,
        reservation_uuid: str,
        *,
        status: int = 200,
        json_body: Any = None,
        include: str = "guest,properties",
    ) -> respx.Route:
        """Register a single-reservation detail response.

        The route is matched on the ``include`` the service is expected
        to send, so a handler that asked for something else -- or asked
        for nothing -- does not silently get served this body.

        Args:
            reservation_uuid: Reservation UUID in the path.
            status: HTTP status to return.
            json_body: JSON body to return.
            include: The ``include`` parameter the request must carry.

        Returns:
            The registered respx route.
        """
        route = self._router.get(
            f"{self._base_url}/reservations/{reservation_uuid}",
            params={"include": include},
        )
        route.mock(return_value=httpx.Response(status, json=json_body))
        return route

    def reservations(self, *, status: int = 200, json_body: Any = None) -> respx.Route:
        """Register the guest-include reservations list response.

        Args:
            status: HTTP status to return.
            json_body: JSON body to return.

        Returns:
            The registered respx route.
        """
        route = self._router.get(
            f"{self._base_url}/reservations",
            params={"include": "guest,properties"},
        )
        route.mock(return_value=httpx.Response(status, json=json_body))
        return route


@pytest.fixture
def lookup_routes(respx_router: respx.Router) -> LookupRouteBuilder:
    """Return a lookup-endpoint route builder bound to the router.

    Args:
        respx_router: Active respx router.

    Returns:
        Route builder for the read-only lookup endpoints.
    """
    const = importlib.import_module("custom_components.hospitable.api.const")
    return LookupRouteBuilder(respx_router, const.BASE_URL)
