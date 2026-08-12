# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for service localisation parity (FR-007).

Every registered service needs a ``services.yaml`` declaration AND
``strings.json`` plus ``translations/en.json`` entries. The Hostaway
reference ships ``services.yaml`` only; that is an anti-pattern this
integration explicitly does not copy, because without the translation
files the Home Assistant UI renders raw field keys.
"""

from __future__ import annotations

EXPECTED_SERVICES = {"send_message"}
EXPECTED_FIELDS = {
    "send_message": {
        "config_entry_id",
        "entity_id",
        "reservation_uuid",
        "body",
        "images",
        "sender_id",
    }
}


def test_services_yaml_declares_every_service_and_field() -> None:
    """``services.yaml`` declares each service with all of its fields."""
    from tests.helpers.localisation import services_yaml_declarations

    declared = services_yaml_declarations()

    assert set(declared) >= EXPECTED_SERVICES
    for service, fields in EXPECTED_FIELDS.items():
        assert fields == set(declared[service]), service


def test_strings_and_translations_match_services_yaml_exactly() -> None:
    """Both translation files cover exactly what ``services.yaml`` declares."""
    from tests.helpers.localisation import (
        STRINGS_JSON,
        TRANSLATIONS_EN_JSON,
        services_yaml_declarations,
        strings_declarations,
    )

    declared = services_yaml_declarations()
    assert set(declared) >= EXPECTED_SERVICES, "services.yaml declares nothing to match"

    for path in (STRINGS_JSON, TRANSLATIONS_EN_JSON):
        translated = strings_declarations(path)
        assert set(translated) == set(declared), path
        for service, fields in declared.items():
            assert set(translated[service]) == set(fields), f"{path}:{service}"


def test_every_service_string_has_a_name_and_description() -> None:
    """No service or field ships with empty user-facing text."""
    from tests.helpers.localisation import (
        STRINGS_JSON,
        TRANSLATIONS_EN_JSON,
        strings_text,
    )

    for path in (STRINGS_JSON, TRANSLATIONS_EN_JSON):
        collected = strings_text(path)
        assert collected, f"{path} declares no service text at all"
        for text in collected:
            assert text.strip(), f"{path}: blank service string"


def test_service_text_never_claims_delivery() -> None:
    """User-facing service text says accepted, never sent or delivered.

    A 202 is an acceptance for asynchronous delivery. Text promising
    delivery would misrepresent what the integration can actually know.
    """
    from tests.helpers.language import find_delivery_claims
    from tests.helpers.localisation import (
        STRINGS_JSON,
        TRANSLATIONS_EN_JSON,
        strings_text,
    )

    for path in (STRINGS_JSON, TRANSLATIONS_EN_JSON):
        collected = strings_text(path)
        assert collected, f"{path} declares no service text at all"
        for text in collected:
            assert not find_delivery_claims(text), f"{path}: {text}"
