# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Write-capable Hospitable API client, isolated in its own module.

Spec 001 made writes structurally impossible because no client could
issue one. Spec 002 needs a POST for messaging, so the capability lives
in a SEPARATE module and a SEPARATE class that nothing on the polling
path imports (research.md D-01). Importing this module is the visible,
greppable, statically checkable act that grants write access.

The subclass adds ``_post`` and nothing else: the session, auth headers,
timeout, ``_raise_for_status``, and ``classify_403`` are all inherited,
so a POST is classified exactly as a GET is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from custom_components.hospitable.api.auth import build_auth_headers
from custom_components.hospitable.api.client import HospitableApiClient
from custom_components.hospitable.api.exceptions import (
    HospitableConnectionError,
    HospitableRequestValidationError,
)
from custom_components.hospitable.api.responses import parse_error_envelope

# 400 and 422 are user-fixable request problems carrying a Laravel
# envelope; every other status is classified by the inherited logic.
VALIDATION_STATUSES = frozenset({400, 422})


@dataclass(frozen=True, slots=True)
class WriteResult:
    """The outcome of one write request."""

    status_code: int
    data: dict[str, Any]
    headers: dict[str, str]


class HospitableWriteClient(HospitableApiClient):
    """Hospitable client that can also issue write requests."""

    async def _post(self, path: str, *, json: dict[str, Any]) -> WriteResult:
        """Issue one authenticated POST request.

        Args:
            path: API path, relative to the base URL.
            json: JSON request body.

        Returns:
            The status code, parsed body, and response headers. Headers
            are returned because the messages endpoint reports the
            authoritative rate-limit state there.

        Raises:
            HospitableConnectionError: The request could not be sent.
            HospitableRequestValidationError: Upstream returned 400/422.
        """
        try:
            response = await self._http.post(
                f"{self._base_url}{path}",
                json=json,
                headers=await build_auth_headers(self._token_provider),
            )
        except httpx.RequestError as exc:
            raise HospitableConnectionError(
                "Could not reach the Hospitable API", endpoint=path
            ) from exc
        if response.status_code in VALIDATION_STATUSES:
            envelope = parse_error_envelope(_decode(response))
            raise HospitableRequestValidationError(
                envelope.reason_phrase or "Hospitable rejected the request",
                field_messages=envelope.field_messages(),
                status=response.status_code,
                endpoint=path,
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._raise_for_status(exc.response, path)
        return WriteResult(
            status_code=response.status_code,
            data=_decode(response),
            headers={key.lower(): value for key, value in response.headers.items()},
        )


def _decode(response: httpx.Response) -> dict[str, Any]:
    """Decode a JSON body, tolerating an empty or non-object one.

    Args:
        response: Response to decode.

    Returns:
        The decoded object, or an empty mapping. A 202 acceptance may
        legitimately carry no body at all (OQ-001 is unverified), so an
        undecodable body is not treated as a failure here.
    """
    try:
        parsed = response.json()
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
