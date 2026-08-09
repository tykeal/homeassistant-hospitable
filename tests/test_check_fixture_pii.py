# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for the fixture PII guard."""

from __future__ import annotations

import pytest


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T016 fixture PII guard",
)
def test_flags_non_documentation_email() -> None:
    """Flag email addresses outside documentation domains."""
    import scripts.check_fixture_pii as pii  # type: ignore[import-not-found]

    assert pii.scan_text("tests/fixtures/bad.json", '{"email":"person@invalid.test"}')


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T016 fixture PII guard",
)
def test_flags_owner_identity_strings() -> None:
    """Flag owner identity strings in fixtures."""
    import scripts.check_fixture_pii as pii  # type: ignore[import-not-found, unused-ignore]

    assert pii.scan_text("tests/fixtures/bad.json", "tykeal bardicgrove")


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T016 fixture PII guard",
)
def test_flags_bearer_token_literals() -> None:
    """Flag bearer-token-shaped literals in fixtures."""
    import scripts.check_fixture_pii as pii  # type: ignore[import-not-found, unused-ignore]

    hits = pii.scan_text("tests/fixtures/bad.json", "Bearer abcdefghijklmnop")
    assert [hit.rule for hit in hits] == ["bearer-token"]


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T016 fixture PII guard",
)
def test_flags_coordinates_outside_synthetic_box() -> None:
    """Flag latitude or longitude outside the synthetic coordinate box."""
    import scripts.check_fixture_pii as pii  # type: ignore[import-not-found, unused-ignore]

    text = '{"latitude": 47.6062, "longitude": -122.3321}'
    assert pii.scan_text("tests/fixtures/bad.json", text)


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T016 fixture PII guard",
)
def test_flags_address_or_postcode_outside_allowlist() -> None:
    """Flag street addresses and postcodes outside the allowlist."""
    import scripts.check_fixture_pii as pii  # type: ignore[import-not-found, unused-ignore]

    text = '{"street":"Real Street", "postcode":"98101"}'
    assert pii.scan_text("tests/fixtures/bad.json", text)


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T016 fixture PII guard",
)
def test_flags_json_fixtures_outside_fixture_tree() -> None:
    """Flag JSON fixtures outside tests/fixtures."""
    import scripts.check_fixture_pii as pii  # type: ignore[import-not-found, unused-ignore]

    assert pii.scan_paths(["tests/api/not_a_fixture.json"])


@pytest.mark.xfail(
    raises=ModuleNotFoundError,
    strict=True,
    reason="TDD red phase: T016 fixture PII guard",
)
def test_output_never_echoes_matched_value() -> None:
    """Report file, line, and rule without echoing the matched value."""
    import scripts.check_fixture_pii as pii  # type: ignore[import-not-found, unused-ignore]

    [hit] = pii.scan_text("tests/fixtures/bad.json", '{"email":"person@invalid.test"}')
    output = pii.format_hit(hit)
    assert "tests/fixtures/bad.json" in output
    assert "email-domain" in output
    assert "person@invalid.test" not in output
