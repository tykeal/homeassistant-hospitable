# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase privacy tests."""

from __future__ import annotations

from pathlib import Path

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

    fixtures = sorted(Path("tests/fixtures").glob("*.json"))
    assert fixtures, "no fixtures were discovered to audit"
    hits = pii.scan_paths([str(path) for path in fixtures])
    assert not hits, [pii.format_hit(hit) for hit in hits]


def test_spec_002_fixtures_are_covered_by_the_audit() -> None:
    """The spec 002 fixtures exist and are inside the audited tree."""
    import scripts.check_fixture_pii as pii

    for name in _SPEC_002_FIXTURES:
        path = Path("tests/fixtures") / name
        assert path.exists(), f"missing spec 002 fixture: {name}"
        assert not pii.scan_paths([str(path)])
