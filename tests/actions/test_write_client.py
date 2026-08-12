# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for the write-capable API client (T019-T021).

The base client is ``HospitableApiClient`` — NOT ``HospitableClient`` as
``plan.md`` and ``research.md`` D-01 write it. That is a documentation
discrepancy, reported rather than silently reconciled; these tests use
the real name.

The write client lives in its own module so that a coordinator cannot
reach a POST without an import a reviewer and a static scan can both
see (D-01). Because ``api/write_client.py`` genuinely does not exist in
the red phase, the honest failure is ``ModuleNotFoundError``. The half
of T019 that is testable TODAY — that the base client exposes no
``_post`` — is asserted without a marker, because it must hold at every
commit, not merely after the green phase.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

import httpx
import pytest
import respx

from tests.actions.conftest import SYNTHETIC_TOKEN


def test_base_client_exposes_no_post_method() -> None:
    """The GET-only base client has no ``_post`` attribute at all.

    This is write-isolation gate 1's premise: the coordinator's client
    attribute is annotated as this class, so annotating it here and
    having no ``_post`` on it is what makes ``coordinator.client._post``
    a type error rather than a runtime surprise.
    """
    from custom_components.hospitable.api.client import HospitableApiClient

    assert not hasattr(HospitableApiClient, "_post")
    assert not hasattr(HospitableApiClient, "post")


def test_write_client_subclass_adds_post() -> None:
    """``HospitableWriteClient`` subclasses the base and adds ``_post``."""
    from custom_components.hospitable.api.client import HospitableApiClient
    from custom_components.hospitable.api.write_client import (
        HospitableWriteClient,
    )

    assert issubclass(HospitableWriteClient, HospitableApiClient)
    assert hasattr(HospitableWriteClient, "_post")


async def test_write_client_inherits_every_get_helper(
    write_client_factory: Callable[[httpx.AsyncClient, str], Any],
    mock_httpx_client: httpx.AsyncClient,
) -> None:
    """The write client reuses the base client's GET surface verbatim."""
    from custom_components.hospitable.api.client import HospitableApiClient

    client = write_client_factory(mock_httpx_client, SYNTHETIC_TOKEN)

    for helper in ("get_user", "get_properties", "get_reservations", "get_calendar"):
        assert getattr(type(client), helper) is getattr(HospitableApiClient, helper)


async def test_write_client_adds_no_second_session_or_auth_path(
    write_client_factory: Callable[[httpx.AsyncClient, str], Any],
    mock_httpx_client: httpx.AsyncClient,
) -> None:
    """The write client shares the caller's session and auth machinery."""
    from custom_components.hospitable.api.client import HospitableApiClient

    client = write_client_factory(mock_httpx_client, SYNTHETIC_TOKEN)

    assert client._http is mock_httpx_client
    assert type(client)._raise_for_status is HospitableApiClient._raise_for_status
    assert not any(
        isinstance(value, httpx.AsyncClient) and value is not mock_httpx_client
        for value in vars(client).values()
    )


@pytest.mark.parametrize(
    ("status", "fixture", "exception_name"),
    [
        (401, "error_401.json", "HospitableAuthError"),
        (403, "error_403_scope.json", "HospitableScopeError"),
        (403, "error_403_other.json", "HospitableForbiddenError"),
        (500, "error_500.json", "HospitableConnectionError"),
    ],
)
async def test_post_classifies_errors_exactly_as_get(
    status: int,
    fixture: str,
    exception_name: str,
    write_client_factory: Callable[[httpx.AsyncClient, str], Any],
    mock_httpx_client: httpx.AsyncClient,
    respx_router: respx.Router,
) -> None:
    """``_post`` reuses ``_raise_for_status`` and ``classify_403``."""
    from custom_components.hospitable.api import exceptions
    from custom_components.hospitable.api.const import BASE_URL
    from tests.helpers import load_fixture

    url = f"{BASE_URL}/reservations/res-example-accepted/messages"
    respx_router.post(url).mock(
        return_value=httpx.Response(status, json=load_fixture(fixture))
    )
    client = write_client_factory(mock_httpx_client, SYNTHETIC_TOKEN)

    with pytest.raises(getattr(exceptions, exception_name)):
        await client._post(
            "/reservations/res-example-accepted/messages", json={"body": "x"}
        )


async def test_post_maps_transport_failure_to_connection_error(
    write_client_factory: Callable[[httpx.AsyncClient, str], Any],
    mock_httpx_client: httpx.AsyncClient,
    respx_router: respx.Router,
) -> None:
    """A transport failure on ``_post`` becomes a connection error."""
    from custom_components.hospitable.api.const import BASE_URL
    from custom_components.hospitable.api.exceptions import HospitableConnectionError

    url = f"{BASE_URL}/reservations/res-example-accepted/messages"
    respx_router.post(url).mock(side_effect=httpx.ConnectError("boom"))
    client = write_client_factory(mock_httpx_client, SYNTHETIC_TOKEN)

    with pytest.raises(HospitableConnectionError):
        await client._post(
            "/reservations/res-example-accepted/messages", json={"body": "x"}
        )


def test_write_client_module_is_not_reachable_from_the_api_package() -> None:
    """Importing the api package does not pull in the write client.

    Write isolation is a module-path property (D-01). If importing
    ``custom_components.hospitable.api`` re-exported the write client,
    every existing importer would gain a POST-capable symbol for free
    and the static scan in gate 3 would have nothing to catch.
    """
    api = importlib.import_module("custom_components.hospitable.api")

    assert not hasattr(api, "HospitableWriteClient")
