# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""The diagnostics DOWNLOAD, as opposed to the redactor (T153).

**Principle XII status: GREEN.** Every test here failed in the red
commit that introduced them, marked ``xfail(strict=True)``; the
markers came off in the commit that added the entry point.

**The defect these tests exist to pin.** ``diagnostics.py`` implements
``redact_diagnostics`` and every existing test in
``tests/test_diagnostics.py`` calls that pure function directly with a
hand-built payload. Not one of them proves Home Assistant can download
anything. It cannot: Home Assistant resolves a diagnostics platform by
looking up ``async_get_config_entry_diagnostics`` on the integration's
``diagnostics`` module, and no such function exists, so the platform
registers with ``config_entry_diagnostics=None``.

The consequences are exactly the recurring shape this project keeps
hitting — a control that looks complete but is scoped to a surface it
never reaches:

* spec 001 FR-063 requires a diagnostics download. There is none.
* spec 002 FR-042 requires guest fields to be shown redacted IN THAT
  DOWNLOAD. The redactor is correct and unreachable.
* SC-003 claims "a full diagnostics download finds zero occurrences" of
  guest data. That is true only because there is no download.
* ``redact_diagnostics`` is dead code in production.

CI could never catch this. Every test asserted the redactor, and the
redactor was never the broken part.
"""

from __future__ import annotations

import json
from typing import Any

from homeassistant.setup import async_setup_component

from tests.helpers.audit_entry import (
    GUEST_SECRETS,
    MESSAGE_BODY,
    TOKEN,
    setup_audit_entry,
)

REDACTED = "**REDACTED**"


async def test_the_integration_exposes_a_diagnostics_entry_point() -> None:
    """The module exports the name Home Assistant actually looks up.

    Asserted against the module rather than against a call, so the
    failure names the missing symbol instead of an AttributeError deep
    inside Home Assistant.
    """
    from custom_components.hospitable import diagnostics

    assert hasattr(diagnostics, "async_get_config_entry_diagnostics"), (
        "Home Assistant resolves a diagnostics platform by this exact "
        "name; without it the download does not exist and FR-063 is unmet"
    )


async def test_home_assistant_registers_the_platform_with_a_handler(
    hass: Any, respx_router: Any
) -> None:
    """Home Assistant really wires the handler, not merely the module.

    The module's mere existence is enough for Home Assistant to register
    a diagnostics platform, so a registration check alone would pass
    today while the handler was ``None``. The handler itself is asserted
    for that reason.
    """
    from homeassistant.components.diagnostics import _DIAGNOSTICS_DATA

    await setup_audit_entry(hass, respx_router, guest_contact=True)
    assert await async_setup_component(hass, "diagnostics", {})
    await hass.async_block_till_done()

    platform = hass.data[_DIAGNOSTICS_DATA].platforms.get("hospitable")
    assert platform is not None, "no diagnostics platform registered at all"
    assert platform.config_entry_diagnostics is not None, (
        "the platform registered with a null handler, so the download "
        "affordance exists in the UI and is backed by nothing"
    )


async def test_the_download_is_useful_for_troubleshooting(
    hass: Any, respx_router: Any
) -> None:
    """The dump carries enough to troubleshoot with (FR-063).

    A download that redacted everything would satisfy the privacy half
    of the requirement and fail the other half.
    """
    from custom_components.hospitable.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = await setup_audit_entry(hass, respx_router, guest_contact=True)
    dump = await async_get_config_entry_diagnostics(hass, entry)

    assert dump["namespace_source"] == "account"
    assert dump["options"]["guest_contact_details"] is True, (
        "the opt-in setting is a boolean SETTING, not guest data, and is "
        "what explains which attributes an entity is publishing"
    )
    assert set(dump["coordinators"]) == {
        "properties",
        "reservations",
        "calendar",
        "tasks",
    }
    assert dump["counts"]["reservations"] >= 1
    for name, section in dump["coordinators"].items():
        assert "last_update_success" in section, name


async def test_the_download_shows_guest_fields_as_redacted(
    hass: Any, respx_router: Any
) -> None:
    """Guest keys are present with redacted values (FR-042).

    Presence with a redaction marker is what lets a troubleshooter tell
    "the API never sent it" from "we hid it". Omission cannot.
    """
    from custom_components.hospitable.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = await setup_audit_entry(hass, respx_router, guest_contact=True)
    dump = await async_get_config_entry_diagnostics(hass, entry)

    reservations = dump["coordinators"]["reservations"]["items"]
    with_guest = [item for item in reservations if item["guest"] is not None]
    assert with_guest, (
        "no reservation in the dump carried a guest object, so a clean "
        "dump would prove nothing about redaction"
    )
    for item in with_guest:
        for field, value in item["guest"].items():
            assert value == REDACTED, f"{field} was not redacted"
    without_guest = [item for item in reservations if item["guest"] is None]
    assert without_guest, (
        "the null-guest branch was never exercised; that a guest is "
        "ABSENT is not private and must stay distinguishable (FR-040)"
    )


async def test_no_guest_value_or_token_survives_the_download(
    hass: Any, respx_router: Any
) -> None:
    """The rendered download leaks no guest value and no token (SC-003).

    This is the assertion SC-003 has always claimed and never made,
    because until now there was nothing to render.
    """
    from custom_components.hospitable.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = await setup_audit_entry(hass, respx_router, guest_contact=True)
    rendered = json.dumps(
        await async_get_config_entry_diagnostics(hass, entry), default=str
    )

    for secret in (*GUEST_SECRETS, MESSAGE_BODY, TOKEN):
        assert secret not in rendered, f"{secret!r} survived the download"
