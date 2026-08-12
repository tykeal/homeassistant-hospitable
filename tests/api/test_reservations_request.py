# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Reservation include tests (T087, T088).

``include=guest`` is SINGULAR. Plural ``guests`` returns HTTP 200 and is
silently ignored upstream, which is why spec 001 wrongly recorded the
include as unsupported. A 200 never proves a request was honoured, so
the client must ASSERT the key arrived (spec 001 FR-075).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from tests.helpers import load_fixture

# The null-guest test reaches ``reservation.guest``, which does not exist
# yet, so its red-phase failure is an AttributeError on the model rather
# than an assertion about the include.


def test_reservation_params_stack_guest_and_properties_in_one_include() -> None:
    """The poll sends ``include=guest,properties`` as ONE parameter (FR-039).

    Multi-include stacking is comma-separated within a single
    ``include`` parameter, not a repeated parameter, and it costs no
    extra request.
    """
    from custom_components.hospitable.api.reservations import (
        build_reservation_params,
    )

    params = build_reservation_params(["p1"], date(2025, 1, 1), date(2025, 1, 2))

    assert params["include"] == "guest,properties"
    assert isinstance(params["include"], str), "include is one parameter, not a list"
    assert "guests" not in str(params["include"]).split(","), (
        "plural 'guests' is a silently-ignored upstream no-op"
    )


async def test_the_polled_request_carries_the_guest_include_on_the_wire(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """The reservation request actually puts the guest include on the wire."""
    from urllib.parse import parse_qs

    from custom_components.hospitable.api.const import BASE_URL

    client = api_client_factory(mock_httpx_client, synthetic_token)
    route = respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(
            200, json=load_fixture("reservation_with_guest.json")
        )
    )

    await client.get_reservations(
        ["prop-example-001"], date(2025, 6, 14), date(2025, 6, 30)
    )

    query = parse_qs(route.calls.last.request.url.query.decode())
    assert query["include"] == ["guest,properties"]


async def test_a_silently_ignored_guest_include_is_detected_not_assumed(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """A 200 without the ``guest`` key raises rather than passing silently.

    An unrecognised include NAME returns HTTP 200 with no added keys
    (spec 001 FR-075). Assuming the include was honoured is exactly the
    mistake that made spec 001 record ``include=guest`` as unsupported.
    """
    from custom_components.hospitable.api.const import BASE_URL
    from custom_components.hospitable.api.exceptions import (
        HospitableIncludeMissingError,
    )

    payload = load_fixture("reservation_with_guest.json")
    for item in payload["data"]:
        item.pop("guest", None)

    client = api_client_factory(mock_httpx_client, synthetic_token)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=payload)
    )

    raised: Exception | None = None
    try:
        await client.get_reservations(
            ["prop-example-001"], date(2025, 6, 14), date(2025, 6, 30)
        )
    except HospitableIncludeMissingError as exc:
        raised = exc

    assert raised is not None, (
        "a 200 lacking the guest key must raise, not be assumed honoured"
    )


async def test_a_null_guest_is_honoured_and_never_treated_as_missing(
    api_client_factory: Any,
    mock_httpx_client: Any,
    respx_router: Any,
    synthetic_token: str,
) -> None:
    """A present-but-``null`` guest is valid data, not a missing include.

    FR-040 draws the line at key PRESENCE: ``"guest": null`` means the
    include was honoured and there simply is no guest.
    """
    from custom_components.hospitable.api.const import BASE_URL

    client = api_client_factory(mock_httpx_client, synthetic_token)
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(
            200, json=load_fixture("reservation_with_guest.json")
        )
    )

    reservations = await client.get_reservations(
        ["prop-example-001", "prop-example-002"], date(2025, 6, 14), date(2025, 6, 30)
    )

    by_id = {reservation.reservation_id: reservation for reservation in reservations}
    assert by_id["res-example-guest-null"].guest is None
    assert by_id["res-example-guest-full"].guest is not None
