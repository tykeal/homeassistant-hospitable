# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Async GET-only client for Hospitable Public API requests."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

import httpx

from custom_components.hospitable.api.auth import TokenProvider, build_auth_headers
from custom_components.hospitable.api.calendar import build_calendar_params
from custom_components.hospitable.api.const import (
    BASE_URL,
    CALENDAR_PATH,
    PER_PAGE_MAX,
    PROPERTIES_PATH,
    RESERVATION_PATH,
    RESERVATIONS_PATH,
    TASKS_PATH,
    USER_PATH,
)
from custom_components.hospitable.api.exceptions import (
    HospitableAuthError,
    HospitableConnectionError,
    HospitableForbiddenError,
    HospitableNotFoundError,
    HospitableRateLimitError,
    HospitableRequestValidationError,
    HospitableResponseError,
    HospitableScopeError,
)
from custom_components.hospitable.api.models import (
    HospitableAccount,
    HospitableProperty,
    HospitablePropertyCalendar,
    HospitableReservation,
    HospitableTask,
    TaskVocabularies,
)
from custom_components.hospitable.api.properties import build_properties_params
from custom_components.hospitable.api.reservations import (
    RESERVATION_INCLUDES,
    build_reservation_params,
    chunk_property_ids,
)
from custom_components.hospitable.api.responses import (
    assert_include,
    parse_error_envelope,
    resolve_last_page,
    validate_list_envelope,
)
from custom_components.hospitable.api.retry import parse_retry_after
from custom_components.hospitable.api.tasks import build_tasks_params

QueryValue = str | int | float | bool | None | list[str]


def classify_403(
    body: dict[str, Any] | None,
) -> type[HospitableScopeError] | type[HospitableForbiddenError]:
    """Classify a 403 body into scope or ordinary forbidden errors."""
    if body:
        reason = str(
            body.get("reason_phrase") or body.get("message") or body.get("error") or ""
        )
        if "scope" in reason.casefold():
            return HospitableScopeError
    return HospitableForbiddenError


class HospitableApiClient:
    """Small async Hospitable client with a GET-only public surface."""

    def __init__(
        self,
        token_provider: TokenProvider,
        http_client: httpx.AsyncClient,
        *,
        base_url: str = BASE_URL,
    ) -> None:
        """Initialize the client with a token provider and HTTP client."""
        self._token_provider = token_provider
        self._http = http_client
        self._base_url = base_url.rstrip("/")
        self.last_trace_id: str | None = None

    async def _get(
        self, path: str, *, params: Mapping[str, QueryValue] | None = None
    ) -> dict[str, Any]:
        """Issue one authenticated GET request and return JSON."""
        body, _ = await self._get_with_response(path, params=params)
        return body

    async def _get_with_response(
        self, path: str, *, params: Mapping[str, QueryValue] | None = None
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Issue one authenticated GET request, returning body and headers.

        ``_get`` discards the response, so callers cannot see the
        ``x-ratelimit-*`` headers the messages endpoint returns. This
        variant surfaces them without changing the existing signature.

        Args:
            path: API path, relative to the base URL.
            params: Query parameters.

        Returns:
            The parsed body and the lower-cased response headers.

        Raises:
            HospitableConnectionError: The request could not be sent.
            HospitableResponseError: The body was not valid JSON.
        """
        try:
            response = await self._http.get(
                f"{self._base_url}{path}",
                params=params,
                headers=await build_auth_headers(self._token_provider),
            )
        except httpx.RequestError as exc:
            raise HospitableConnectionError(
                "Could not reach the Hospitable API", endpoint=path
            ) from exc
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._raise_for_status(exc.response, path)
        try:
            data = response.json()
        except ValueError as exc:
            raise HospitableResponseError(
                "Hospitable returned a malformed response", endpoint=path
            ) from exc
        headers = {key.lower(): value for key, value in response.headers.items()}
        self.last_trace_id = headers.get("x-hospitable-trace")
        if not isinstance(data, dict):
            return {}, headers
        return data, headers

    def _raise_for_status(self, response: httpx.Response, path: str) -> None:
        """Translate HTTP failures into typed Hospitable errors."""
        body: dict[str, Any] | None
        try:
            parsed = response.json()
        except ValueError:
            parsed = None
        body = parsed if isinstance(parsed, dict) else None
        trace_id = response.headers.get("x-hospitable-trace")
        if response.status_code == 401:
            raise HospitableAuthError(
                "Hospitable token was rejected",
                status=401,
                endpoint=path,
                trace_id=trace_id,
            )
        if response.status_code == 403:
            error_type = classify_403(body)
            raise error_type(
                "Hospitable request is forbidden",
                status=403,
                endpoint=path,
                trace_id=trace_id,
            )
        if response.status_code == 404:
            raise HospitableNotFoundError(
                "Hospitable resource was not found",
                status=404,
                endpoint=path,
                trace_id=trace_id,
            )
        if response.status_code == 400:
            # A 400 carries the SAME Laravel envelope the message-send
            # 422 does, so the shared parser serves both rather than a
            # second, divergent one appearing (FR-045).
            envelope = parse_error_envelope(body)
            raise HospitableRequestValidationError(
                envelope.reason_phrase or "Hospitable rejected the request",
                field_messages=envelope.field_messages(),
                status=400,
                endpoint=path,
                trace_id=trace_id,
            )
        if response.status_code == 429:
            retry_after = parse_retry_after(response.headers.get("Retry-After"))
            raise HospitableRateLimitError(
                "Hospitable rate limit reached",
                retry_after=retry_after,
                endpoint=path,
                trace_id=trace_id,
            )
        raise HospitableConnectionError(
            "Hospitable API request failed",
            status=response.status_code,
            endpoint=path,
            trace_id=trace_id,
        )

    async def get_reservation(
        self,
        reservation_uuid: str,
        *,
        include: str | None = None,
        require: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        """Return one reservation's raw payload.

        The raw payload is returned rather than a model for two
        reasons: the send path needs only the upstream ``platform``
        value, and the lookup path must return upstream fields a model
        deliberately drops. Building a model would also fail on payloads
        lacking the includes the LIST endpoint requests.

        ``include`` is SINGULAR ``guest``; plural ``guests`` is a
        silently-ignored no-op upstream. Because unrecognised include
        NAMES are ignored rather than rejected, callers that need an
        include MUST verify the key arrived rather than assume it
        (FR-075) — see ``assert_include``.

        Args:
            reservation_uuid: Reservation UUID to fetch.
            include: Comma-separated include list, when one is wanted.
            require: Include keys that MUST be present in the response.
                Deliberately narrower than ``include``: only the
                CONFIRMED-BY-TEST includes belong here, so an include
                whose behaviour on this endpoint was never observed
                cannot turn a working lookup into an error.

        Returns:
            The ``data`` object, or an empty mapping when absent.

        Raises:
            HospitableIncludeMissingError: A required include key is
                absent from the response.
        """
        path = RESERVATION_PATH.format(uuid=reservation_uuid)
        payload = await self._get(
            path, params={"include": include} if include else None
        )
        data = payload.get("data")
        item = data if isinstance(data, dict) else {}
        for key in require:
            assert_include([item], key, endpoint=path)
        return item

    async def get_property_payloads(self) -> list[dict[str, Any]]:
        """Return every property's RAW payload, across all pages.

        The model drops fields a property-info service caller needs,
        notably the per-listing ``co_hosts`` array FR-013 depends on, so
        the raw items are surfaced alongside the model accessor rather
        than reconstructed from it.

        Returns:
            Every raw property object.
        """
        page = 1
        payloads: list[dict[str, Any]] = []
        while True:
            payload = await self._get(
                PROPERTIES_PATH,
                params=build_properties_params(page=page, per_page=PER_PAGE_MAX),
            )
            items = validate_list_envelope(payload, expected_page=page)
            assert_include(items, "listings", endpoint=PROPERTIES_PATH)
            payloads.extend(items)
            if page >= resolve_last_page(payload, page):
                break
            page += 1
        return payloads

    async def get_reservation_payloads(
        self,
        property_ids: list[str],
        start: date,
        end: date,
        *,
        include: str = "properties",
    ) -> list[dict[str, Any]]:
        """Return raw reservation payloads for a window.

        Each requested include is verified as honoured, because an
        unrecognised include name is silently ignored upstream rather
        than rejected (FR-075).

        Args:
            property_ids: Properties to query.
            start: Window start date.
            end: Window end date.
            include: Comma-separated include list.

        Returns:
            Every raw reservation object in the window.
        """
        wanted = [part.strip() for part in include.split(",") if part.strip()]
        payloads: list[dict[str, Any]] = []
        for batch in chunk_property_ids(property_ids):
            page = 1
            while True:
                params = build_reservation_params(batch, start, end)
                params["include"] = include
                params["page"] = page
                payload = await self._get(RESERVATIONS_PATH, params=params)
                items = validate_list_envelope(payload, expected_page=page)
                for key in wanted:
                    assert_include(items, key, endpoint=RESERVATIONS_PATH)
                payloads.extend(items)
                if page >= resolve_last_page(payload, page):
                    break
                page += 1
        return payloads

    async def get_user(self) -> HospitableAccount:
        """Return the authenticated account identifier."""
        return HospitableAccount.from_api(await self._get(USER_PATH))

    async def get_properties(self) -> dict[str, HospitableProperty]:
        """Return all properties keyed by immutable property identifier."""
        page = 1
        properties: dict[str, HospitableProperty] = {}
        while True:
            payload = await self._get(
                PROPERTIES_PATH,
                params=build_properties_params(page=page, per_page=PER_PAGE_MAX),
            )
            items = validate_list_envelope(payload, expected_page=page)
            assert_include(items, "listings", endpoint=PROPERTIES_PATH)
            for item in items:
                model = HospitableProperty.from_api(item)
                properties[model.property_id] = model
            if page >= resolve_last_page(payload, page):
                break
            page += 1
        return properties

    async def get_reservations(
        self, property_ids: list[str], start: date, end: date
    ) -> list[HospitableReservation]:
        """Return reservations for properties, locally enforcing the date window."""
        reservations: list[HospitableReservation] = []
        for batch in chunk_property_ids(property_ids):
            page = 1
            while True:
                params = build_reservation_params(batch, start, end)
                params["page"] = page
                payload = await self._get(RESERVATIONS_PATH, params=params)
                items = validate_list_envelope(payload, expected_page=page)
                # Each include is verified rather than assumed: an
                # unrecognised include NAME returns HTTP 200 with no
                # added keys (spec 001 FR-075), so a 200 alone never
                # proves the request was honoured. A present-but-null
                # ``guest`` IS honoured and is valid data (FR-040).
                for key in RESERVATION_INCLUDES:
                    assert_include(items, key, endpoint=RESERVATIONS_PATH)
                for item in items:
                    model = HospitableReservation.from_api(item)
                    if (
                        model.property_id in batch
                        and start <= model.arrival_date <= end
                    ):
                        reservations.append(model)
                if page >= resolve_last_page(payload, page):
                    break
                page += 1
        return reservations

    async def get_tasks(
        self, property_id: str, start: date, end: date
    ) -> list[HospitableTask]:
        """Return one property's tasks in a window, across all pages.

        Exactly ONE property is named per call. ``properties[]`` is
        mandatory upstream, and the caller fans out one call per
        property so a single property's failure can be isolated
        (FR-030).

        Pagination is real on this endpoint, unlike the messages
        endpoint which silently ignores ``page``. Each response's own
        ``meta.last_page`` is followed, so a property with more pages
        than another is not truncated (FR-031).

        Args:
            property_id: The single property to fetch tasks for.
            start: Window start date, which is today.
            end: Window end date, today plus the configured window.

        Returns:
            Every task in the window, in upstream order.
        """
        page = 1
        tasks: list[HospitableTask] = []
        while True:
            payload = await self._get(
                TASKS_PATH,
                params=build_tasks_params(property_id, start, end, page=page),
            )
            items = validate_list_envelope(payload, expected_page=page)
            # Vocabularies come from THIS response, never a hardcoded
            # table, so labels match the account's own configuration.
            vocabularies = TaskVocabularies.from_meta(payload.get("meta"))
            tasks.extend(HospitableTask.from_api(item, vocabularies) for item in items)
            if page >= resolve_last_page(payload, page):
                break
            page += 1
        return tasks

    async def get_calendar(
        self, property_id: str, start: date, end: date
    ) -> HospitablePropertyCalendar:
        """Return one property's aggregate forward calendar.

        The response ``data`` is an object, not a list, so the list
        envelope parser is intentionally not applied. ``listing_id`` is
        never sent, and the cosmetic response ``listing_id``/``provider``
        are ignored: parsing keys off the requested property id, which is
        already the aggregate across every sales channel (FR-058, FR-075).
        """
        payload = await self._get(
            CALENDAR_PATH.format(id=property_id),
            params=build_calendar_params(start, end),
        )
        data = payload.get("data")
        if not isinstance(data, dict):
            data = {}
        return HospitablePropertyCalendar.from_api(property_id, data)
