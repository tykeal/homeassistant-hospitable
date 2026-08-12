# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Self-tests for the shared spec 002 test helpers (T014, T016-T018).

The write-isolation gates, the localisation parity assertions, and the
delivery-language audit all rest on these helpers. A helper that silently
returned an empty result would make every test built on it vacuous, so
each helper is proved here against known input.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


def test_ast_scan_reports_imports_and_attributes(tmp_path: Path) -> None:
    """The AST scanner reports imported modules, names, and attributes."""
    from tests.helpers.ast_isolation import scan_module

    source = tmp_path / "sample.py"
    source.write_text(
        "import os.path\n"
        "from custom_components.hospitable.actions import helpers\n"
        "def go(client):\n"
        "    return client._post('/x')\n",
        encoding="utf-8",
    )
    facts = scan_module(source)

    assert "os.path" in facts.imported_modules
    assert "helpers" in facts.imported_names
    assert "_post" in facts.attribute_names
    assert facts.references("_post")
    assert facts.imports_from("custom_components.hospitable.actions")


def test_ast_scan_does_not_report_absent_names(tmp_path: Path) -> None:
    """The AST scanner reports nothing for a module that names nothing."""
    from tests.helpers.ast_isolation import scan_module

    source = tmp_path / "clean.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    facts = scan_module(source)

    assert not facts.references("_post")
    assert not facts.imports_from("custom_components.hospitable.actions")


def test_ast_scan_reads_annotated_attribute_assignments(tmp_path: Path) -> None:
    """Annotated ``self.<attr>`` assignments are reported by annotation."""
    from tests.helpers.ast_isolation import annotated_assignment_types

    source = tmp_path / "annotated.py"
    source.write_text(
        "class Thing:\n"
        "    def __init__(self, client):\n"
        "        self._client: HospitableApiClient = client\n",
        encoding="utf-8",
    )

    assert annotated_assignment_types(source, "_client") == {"HospitableApiClient"}


def test_ast_scan_reads_return_annotations(tmp_path: Path) -> None:
    """Return annotations are reported for a named function."""
    from tests.helpers.ast_isolation import returned_annotations

    source = tmp_path / "returns.py"
    source.write_text(
        "class Thing:\n"
        "    @property\n"
        "    def client(self) -> HospitableApiClient:\n"
        "        return self._client\n",
        encoding="utf-8",
    )

    assert returned_annotations(source, "client") == {"HospitableApiClient"}


@pytest.mark.parametrize(
    "text",
    [
        "The message was sent to the guest.",
        "Your message has been delivered.",
        "Delivery confirmed by the channel.",
    ],
)
def test_delivery_language_helper_rejects_delivery_claims(text: str) -> None:
    """Delivery claims are detected in user-facing text."""
    from tests.helpers.language import assert_no_delivery_language

    with pytest.raises(AssertionError):
        assert_no_delivery_language(text)


@pytest.mark.parametrize(
    "text",
    [
        "The message was accepted for delivery.",
        "Send a message to the guest for a reservation.",
        "Correlation handle sent_reference_id, when upstream returns one.",
    ],
)
def test_delivery_language_helper_accepts_acceptance_phrasing(text: str) -> None:
    """Acceptance phrasing and the correlation identifier are permitted."""
    from tests.helpers.language import assert_no_delivery_language

    assert_no_delivery_language(text)


def test_token_key_helper_matches_sha256_and_hides_the_token() -> None:
    """The token key is the SHA-256 digest and never the raw token."""
    from tests.helpers.tokens import token_key

    token = "hp_test_synthetic_token_000000000000000000000000"
    key = token_key(token)

    assert key == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert token not in key


def test_localisation_helper_reads_declared_services(tmp_path: Path) -> None:
    """The strings loader reports service names and their field names."""
    from tests.helpers.localisation import strings_declarations, strings_text

    path = tmp_path / "strings.json"
    path.write_text(
        '{"services": {"send_message": {"name": "Send message",'
        ' "description": "Queue a guest message.",'
        ' "fields": {"body": {"name": "Body", "description": "Text."}}}}}',
        encoding="utf-8",
    )

    assert strings_declarations(path) == {"send_message": {"body"}}
    assert "Send message" in strings_text(path)
    assert "Text." in strings_text(path)


def test_localisation_helper_tolerates_a_missing_file(tmp_path: Path) -> None:
    """A missing strings file yields no declarations rather than raising."""
    from tests.helpers.localisation import strings_declarations

    assert strings_declarations(tmp_path / "absent.json") == {}
