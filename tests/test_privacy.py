# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase privacy tests."""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers import FIXTURES

# ``scan_paths`` enforces a ``tests/fixtures/`` prefix on the path string
# it is handed, matching how pre-commit invokes it, so discovery uses the
# CWD-independent ``FIXTURES`` path but scanning passes a repo-relative one.
_REPO_ROOT = FIXTURES.parent.parent

# Fixtures whose synthetic nature is asserted by name, so a new fixture
# added by a later phase cannot be silently omitted from the audit
# (T015, FR-024, FR-041).
_SPEC_002_FIXTURES = (
    "messages_thread.json",
    "messages_empty.json",
    "tasks_page1.json",
    "tasks_page2.json",
    "reservation_with_guest.json",
    "send_message_202_full.json",
    "send_message_202_empty.json",
    "error_envelope_400.json",
    "error_envelope_422.json",
    "error_envelope_429.json",
)


def test_privacy_audit_helpers(synthetic_token: str) -> None:
    """Assert lifecycle privacy audit has no leaks and no channels call."""
    from custom_components.hospitable.api.redaction import (
        contains_private_data,
        redact,
    )

    assert not contains_private_data(
        redact({"token": synthetic_token, "email": "guest@example.com"}),
        [synthetic_token, "guest@example.com"],
    )


def test_every_fixture_passes_the_synthetic_data_audit() -> None:
    """Every JSON fixture in the tree passes the PII scanner."""
    import scripts.check_fixture_pii as pii

    fixtures = sorted(FIXTURES.glob("*.json"))
    assert fixtures, "no fixtures were discovered to audit"
    hits = pii.scan_paths([str(path.relative_to(_REPO_ROOT)) for path in fixtures])
    assert not hits, [pii.format_hit(hit) for hit in hits]


def test_spec_002_fixtures_are_covered_by_the_audit() -> None:
    """The spec 002 fixtures exist and are inside the audited tree."""
    import scripts.check_fixture_pii as pii

    for name in _SPEC_002_FIXTURES:
        path = FIXTURES / name
        assert path.exists(), f"missing spec 002 fixture: {name}"
        assert not pii.scan_paths([str(path.relative_to(_REPO_ROOT))])


# --- US3 guest fields never reach the logs (T094, FR-041) ---------------

_RED_LOGS = "TDD red phase: T094 guest data does not flow through the poll yet"


@pytest.mark.xfail(raises=AssertionError, strict=True, reason=_RED_LOGS)
async def test_no_guest_field_appears_in_any_log_record(
    hass: Any, respx_router: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """A full poll cycle logs no guest field at any level (FR-041).

    Run with the guest-contact opt-in ON, the most permissive setting.
    The ``guest_first_name`` assertion is what stops this being a
    tautology: it proves guest data really flowed through the poll and
    onto the entity, so a clean log is a clean log rather than an empty
    pipeline. Real captured output is asserted, not a mock.
    """
    from tests.helpers.guest_entry import (
        GUEST_SECRETS,
        mock_endpoints,
        reservation_entity_id,
        setup_guest_entry,
    )

    caplog.set_level(0)
    mock_endpoints(respx_router)
    entry = await setup_guest_entry(hass, guest_contact=True)

    coordinator = entry.runtime_data["coordinators"]["reservations"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(reservation_entity_id(hass, "prop-example-001"))
    assert state is not None
    assert state.attributes.get("guest_first_name") == "Example", (
        "guest data never reached the entity, so this log check proves nothing"
    )

    captured = "\n".join(record.getMessage() for record in caplog.records)
    captured += "\n" + caplog.text
    assert captured.strip(), "no log output was captured at all"
    for secret in GUEST_SECRETS:
        assert secret not in captured, f"{secret} leaked into the logs"
