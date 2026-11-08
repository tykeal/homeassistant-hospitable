# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Warn ahead of Personal Access Token expiry (spec 001 OQ-007).

Hospitable Personal Access Tokens expire one year after issue and
cannot be refreshed, so until now the integration only noticed when
every call started failing with 401. A token is, empirically, a JWT
whose payload carries an ``exp`` claim. That format is undocumented, so
reading it is best-effort: an unreadable token simply raises no warning.

Every token here is SYNTHETIC, built from a JSON payload in this file.
The ``sub`` and ``jti`` claims carry recognisable markers so the
privacy tests can prove they never leak into logs, issue text or
diagnostics.
"""

from __future__ import annotations

import base64
import importlib
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2 as httpx
import pytest
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant.common import MockConfigEntry, async_fire_time_changed

from custom_components.hospitable.api.const import BASE_URL
from custom_components.hospitable.const import (
    CONF_ACCOUNT_NAMESPACE,
    CONF_NAMESPACE_SOURCE,
    CONF_SELECTED_PROPERTIES,
    CONF_TOKEN,
    DOMAIN,
)
from tests.helpers import load_fixture

_MODULE = "custom_components.hospitable.token_expiry"
_ACCOUNT = "acct-example-0001"
_TITLE = "Hospitable Test"
_NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
_SUB_MARKER = "sub-claim-marker-7f3a"
_JTI_MARKER = "jti-claim-marker-9c1e"


def _segment(value: Any) -> str:
    """Return the unpadded base64url encoding of a JSON value."""
    raw = json.dumps(value).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _raw_segment(raw: bytes) -> str:
    """Return the unpadded base64url encoding of raw bytes."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def make_token(expires: datetime | None, **claims: Any) -> str:
    """Build a synthetic JWT-shaped token expiring at ``expires``.

    The signature segment is junk: the integration never verifies it.
    """
    payload: dict[str, Any] = {
        "aud": "synthetic-audience",
        "iat": int((_NOW - timedelta(days=300)).timestamp()),
        "nbf": int((_NOW - timedelta(days=300)).timestamp()),
        "jti": _JTI_MARKER,
        "sub": _SUB_MARKER,
        "scopes": ["synthetic:read"],
    }
    if expires is not None:
        payload["exp"] = int(expires.timestamp())
    payload.update(claims)
    header = _segment({"alg": "RS256", "typ": "JWT"})
    return f"{header}.{_segment(payload)}.c3ludGhldGljLXNpZ25hdHVyZQ"


def _issue_id(entry: MockConfigEntry) -> str:
    """Return the per-entry token expiry issue id."""
    return f"token_expiring_{entry.entry_id}"


def _issue(hass: Any, entry: MockConfigEntry) -> ir.IssueEntry | None:
    """Return the token expiry issue for ``entry``, if raised."""
    return ir.async_get(hass).async_get_issue(DOMAIN, _issue_id(entry))


def _mock_api(respx_router: Any) -> None:
    """Serve the account, one property and one reservation page."""
    respx_router.get(f"{BASE_URL}/user").mock(
        return_value=httpx.Response(200, json=load_fixture("user.json"))
    )
    respx_router.get(f"{BASE_URL}/properties").mock(
        return_value=httpx.Response(200, json=load_fixture("properties_single.json"))
    )
    respx_router.get(f"{BASE_URL}/reservations").mock(
        return_value=httpx.Response(200, json=load_fixture("reservations_page1.json"))
    )


def _entry(hass: Any, token: str) -> MockConfigEntry:
    """Add an entry holding ``token`` to Home Assistant."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=_TITLE,
        data={
            CONF_TOKEN: token,
            CONF_ACCOUNT_NAMESPACE: _ACCOUNT,
            CONF_NAMESPACE_SOURCE: "account",
        },
        options={CONF_SELECTED_PROPERTIES: ["prop-example-001"]},
        unique_id=_ACCOUNT,
    )
    entry.add_to_hass(hass)
    return entry


async def _setup(hass: Any, respx_router: Any, token: str) -> MockConfigEntry:
    """Set up a loaded entry holding ``token``."""
    _mock_api(respx_router)
    entry = _entry(hass, token)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


# Imported by name rather than statically, matching the existing red
# phases: a static import of a not-yet-existing module needs a
# ``type: ignore`` whose error code differs between the whole-tree and
# the file-scoped mypy runs. ``import_module`` raises the same
# ``ModuleNotFoundError`` the markers pin and needs no suppression.


def test_expiry_is_read_from_the_exp_claim() -> None:
    """A JWT-shaped token yields its ``exp`` claim as an aware UTC time."""
    module = importlib.import_module(_MODULE)
    expires = datetime(2027, 3, 1, 8, 30, tzinfo=UTC)

    result = module.token_expiry(make_token(expires))

    assert result == expires
    assert result.tzinfo is not None
    assert result.utcoffset() == timedelta(0)


def test_expiry_accepts_padded_payload_segments() -> None:
    """Padding on the payload segment is tolerated, not required."""
    module = importlib.import_module(_MODULE)
    expires = datetime(2027, 3, 1, tzinfo=UTC)
    header, payload, signature = make_token(expires).split(".")
    padded = payload + "=" * (-len(payload) % 4)

    assert module.token_expiry(f"{header}.{padded}.{signature}") == expires


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("", id="empty"),
        pytest.param("hp_test_synthetic_token_000000000000000000000000", id="opaque"),
        pytest.param("one.two", id="two-segments"),
        pytest.param("a.b.c.d", id="four-segments"),
        pytest.param("head.!!!not-base64!!!.sig", id="bad-base64"),
        pytest.param(
            "{}.{}!!!!.{}".format(*make_token(_NOW).split(".")),
            id="valid-payload-with-stray-characters",
        ),
        pytest.param(f"h.{_raw_segment(b'not json')}.s", id="not-json"),
        pytest.param(f"h.{_raw_segment(b'\xff\xfe')}.s", id="not-utf8"),
        pytest.param(f"h.{_segment([1, 2])}.s", id="payload-not-object"),
        pytest.param(make_token(None), id="missing-exp"),
        pytest.param(make_token(None, exp="1800000000"), id="exp-string"),
        pytest.param(make_token(None, exp=True), id="exp-bool"),
        pytest.param(make_token(None, exp=None), id="exp-null"),
        pytest.param(make_token(None, exp=10**20), id="exp-absurd"),
        pytest.param(make_token(None, exp=-1), id="exp-negative"),
    ],
)
def test_unreadable_tokens_yield_no_expiry(
    token: str, caplog: pytest.LogCaptureFixture
) -> None:
    """Any token that is not a readable JWT is silently ``None``.

    The format is undocumented, so a token Hospitable reshapes must
    degrade to "no warning", never to an exception during setup.
    """
    module = importlib.import_module(_MODULE)
    caplog.set_level(logging.DEBUG)

    assert module.token_expiry(token) is None
    for part in (token, *token.split(".")):
        if len(part) > 3:
            assert part not in caplog.text


async def test_issue_raised_inside_the_lead_window(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """A token expiring within the lead time raises a fixable warning."""
    module = importlib.import_module(_MODULE)
    freezer.move_to(_NOW)
    expires = _NOW + module.LEAD_TIME - timedelta(days=20)

    entry = await _setup(hass, respx_router, make_token(expires))

    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert issue.is_fixable
    assert issue.translation_key == "token_expiring"
    assert issue.translation_placeholders == {
        "expiry": expires.date().isoformat(),
        "title": _TITLE,
    }


async def test_issue_is_an_error_once_the_token_has_expired(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """A token already past ``exp`` raises the issue as an error."""
    importlib.import_module(_MODULE)
    freezer.move_to(_NOW)
    expires = _NOW - timedelta(days=1)

    entry = await _setup(hass, respx_router, make_token(expires))

    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.ERROR
    assert issue.translation_placeholders == {
        "expiry": expires.date().isoformat(),
        "title": _TITLE,
    }


async def test_no_issue_outside_the_lead_window(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """A token with more than the lead time left raises nothing."""
    module = importlib.import_module(_MODULE)
    freezer.move_to(_NOW)
    expires = _NOW + module.LEAD_TIME + timedelta(days=1)

    entry = await _setup(hass, respx_router, make_token(expires))

    assert _issue(hass, entry) is None


async def test_unreadable_token_clears_a_stale_issue(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """A token with no readable expiry leaves no issue behind."""
    importlib.import_module(_MODULE)
    freezer.move_to(_NOW)
    _mock_api(respx_router)
    entry = _entry(hass, "hp_test_synthetic_token_000000000000000000000000")
    ir.async_create_issue(
        hass,
        DOMAIN,
        _issue_id(entry),
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="token_expiring",
        translation_placeholders={"expiry": "2026-11-18", "title": _TITLE},
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert _issue(hass, entry) is None


async def test_timer_raises_then_escalates_the_issue(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """A running instance warns at the lead time and errors at expiry."""
    module = importlib.import_module(_MODULE)
    freezer.move_to(_NOW)
    expires = _NOW + module.LEAD_TIME + timedelta(days=10)
    entry = await _setup(hass, respx_router, make_token(expires))
    assert _issue(hass, entry) is None

    freezer.move_to(expires - module.LEAD_TIME - timedelta(minutes=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert _issue(hass, entry) is None

    freezer.move_to(expires - module.LEAD_TIME + timedelta(seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING

    freezer.move_to(expires + timedelta(seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.ERROR


async def test_unload_cancels_the_timer(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """An unloaded entry's timer no longer fires."""
    module = importlib.import_module(_MODULE)
    freezer.move_to(_NOW)
    expires = _NOW + module.LEAD_TIME + timedelta(days=10)
    entry = await _setup(hass, respx_router, make_token(expires))

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    freezer.move_to(expires - module.LEAD_TIME + timedelta(seconds=1))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()

    assert _issue(hass, entry) is None


async def test_repair_flow_starts_reauth_and_fresh_token_clears_issue(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """Fixing the issue opens reauth; a fresh token removes the issue.

    The repair flow must ABORT rather than finish: Home Assistant
    deletes an issue when its fix flow completes, and the issue has to
    survive until a new token has actually been stored.
    """
    module = importlib.import_module(_MODULE)
    freezer.move_to(_NOW)
    expiring = make_token(_NOW + timedelta(days=5))
    entry = await _setup(hass, respx_router, expiring)
    assert _issue(hass, entry) is not None
    assert await async_setup_component(hass, "repairs", {})
    manager = repairs_flow_manager(hass)
    assert manager is not None

    result = await manager.async_init(DOMAIN, context={"issue_id": _issue_id(entry)})
    assert result["type"] == "form"
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"] == {
        "expiry": (_NOW + timedelta(days=5)).date().isoformat(),
        "title": _TITLE,
    }
    result = await manager.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_started"
    assert _issue(hass, entry) is not None

    reauth = [
        flow
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN)
        if flow["context"]["source"] == "reauth"
    ]
    assert len(reauth) == 1
    assert reauth[0]["context"]["entry_id"] == entry.entry_id

    fresh = make_token(_NOW + module.LEAD_TIME + timedelta(days=335))
    done = await hass.config_entries.flow.async_configure(
        reauth[0]["flow_id"], {CONF_TOKEN: fresh}
    )
    await hass.async_block_till_done()
    assert done["type"] == "abort"
    assert done["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == fresh
    assert _issue(hass, entry) is None


async def test_repair_flow_aborts_for_a_missing_entry(hass: Any) -> None:
    """A fix flow for an entry that no longer exists aborts cleanly."""
    importlib.import_module(_MODULE)
    # Home Assistant resolves the repairs platform only for a LOADED
    # integration, so load it without any entry.
    assert await async_setup_component(hass, DOMAIN, {})
    assert await async_setup_component(hass, "repairs", {})
    ir.async_create_issue(
        hass,
        DOMAIN,
        "token_expiring_missing",
        data={"entry_id": "missing"},
        is_fixable=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="token_expiring",
        translation_placeholders={"expiry": "2026-11-18", "title": _TITLE},
    )
    manager = repairs_flow_manager(hass)
    assert manager is not None

    result = await manager.async_init(
        DOMAIN, context={"issue_id": "token_expiring_missing"}
    )

    assert result["type"] == "abort"
    assert result["reason"] == "entry_not_found"


async def test_issue_removed_with_the_entry(
    hass: Any, respx_router: Any, freezer: Any
) -> None:
    """Deleting the entry deletes its issue.

    Two independent layers: the issue is linked to the entry, which
    Home Assistant's own removal cleanup honours, and
    ``async_remove_entry`` deletes it explicitly. Each is asserted on
    its own, since either alone would pass the end-to-end removal.
    """
    importlib.import_module(_MODULE)
    from custom_components.hospitable import async_remove_entry

    freezer.move_to(_NOW)
    entry = await _setup(hass, respx_router, make_token(_NOW + timedelta(days=5)))
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.config_entry_id == entry.entry_id

    await async_remove_entry(hass, entry)
    assert _issue(hass, entry) is None

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _issue(hass, entry) is not None
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert _issue(hass, entry) is None


async def test_token_and_claims_never_leak(
    hass: Any,
    respx_router: Any,
    freezer: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Neither the token nor any identifying claim reaches logs or UI."""
    importlib.import_module(_MODULE)
    from custom_components.hospitable.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    caplog.set_level(logging.DEBUG)
    freezer.move_to(_NOW)
    expires = _NOW + timedelta(days=5)
    token = make_token(expires)
    entry = await _setup(hass, respx_router, token)
    issue = _issue(hass, entry)
    assert issue is not None
    dump = await async_get_config_entry_diagnostics(hass, entry)

    surfaces = {
        "logs": caplog.text,
        "issue": json.dumps(issue.to_json()),
        "diagnostics": json.dumps(dump, default=str),
    }
    for name, text in surfaces.items():
        for secret in (token, *token.split(".")[:2], _SUB_MARKER, _JTI_MARKER):
            assert secret not in text, f"{secret!r} leaked into {name}"
    assert dump["token_expires"] == expires.date().isoformat()


def test_issue_strings_explain_the_renewal() -> None:
    """The issue text tells the user exactly how to renew the token."""
    importlib.import_module(_MODULE)
    from pathlib import Path

    root = Path("custom_components/hospitable")
    strings = json.loads((root / "strings.json").read_text(encoding="utf-8"))
    english = json.loads((root / "translations/en.json").read_text(encoding="utf-8"))
    issue = strings["issues"]["token_expiring"]

    assert english["issues"]["token_expiring"] == issue
    description = issue["fix_flow"]["step"]["confirm"]["description"]
    for needle in ("{expiry}", "{title}", "my.hospitable.com", "Access tokens"):
        assert needle in description
    abort = issue["fix_flow"]["abort"]
    assert set(abort) == {"reauth_started", "entry_not_found"}
