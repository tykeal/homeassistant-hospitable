# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Localisation parity helpers for service text (T016, FR-007).

Every service name, description, and field label must appear in
``services.yaml`` AND in ``strings.json`` AND in
``translations/en.json``. Relying on ``services.yaml`` alone is the
anti-pattern this project explicitly does not copy, so these helpers give
tests one source of truth for what each file declares.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from homeassistant.util.yaml import load_yaml_dict

INTEGRATION_ROOT = Path("custom_components/hospitable")
SERVICES_YAML = INTEGRATION_ROOT / "services.yaml"
STRINGS_JSON = INTEGRATION_ROOT / "strings.json"
TRANSLATIONS_EN_JSON = INTEGRATION_ROOT / "translations/en.json"


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON document, returning an empty mapping when absent.

    Args:
        path: Document to load.

    Returns:
        Parsed mapping, or an empty mapping if the file does not exist.
    """
    if not path.exists():
        return {}
    parsed = json.loads(path.read_text(encoding="utf-8"))
    return parsed if isinstance(parsed, dict) else {}


def services_yaml_declarations() -> dict[str, set[str]]:
    """Return service names and field names declared in services.yaml.

    Returns:
        Field-name sets keyed by service name. Empty when the file is
        absent, which is itself a parity failure the caller asserts on.
    """
    if not SERVICES_YAML.exists():
        return {}
    parsed = load_yaml_dict(SERVICES_YAML)
    declarations: dict[str, set[str]] = {}
    for name, definition in parsed.items():
        fields = definition.get("fields") if isinstance(definition, dict) else None
        declarations[str(name)] = set(fields) if isinstance(fields, dict) else set()
    return declarations


def strings_declarations(path: Path) -> dict[str, set[str]]:
    """Return service names and field names declared in a strings file.

    Args:
        path: ``strings.json`` or a translation file.

    Returns:
        Field-name sets keyed by service name.
    """
    services = _load_json(path).get("services")
    if not isinstance(services, dict):
        return {}
    declarations: dict[str, set[str]] = {}
    for name, definition in services.items():
        fields = definition.get("fields") if isinstance(definition, dict) else None
        declarations[str(name)] = set(fields) if isinstance(fields, dict) else set()
    return declarations


def strings_text(path: Path) -> list[str]:
    """Return every service name and description string in a file.

    Args:
        path: ``strings.json`` or a translation file.

    Returns:
        Every user-facing service string, for auditing.
    """
    services = _load_json(path).get("services")
    if not isinstance(services, dict):
        return []
    collected: list[str] = []
    for definition in services.values():
        if not isinstance(definition, dict):
            continue
        for key in ("name", "description"):
            value = definition.get(key)
            if isinstance(value, str):
                collected.append(value)
        fields = definition.get("fields")
        if not isinstance(fields, dict):
            continue
        for field in fields.values():
            if not isinstance(field, dict):
                continue
            for key in ("name", "description"):
                value = field.get(key)
                if isinstance(value, str):
                    collected.append(value)
    return collected
