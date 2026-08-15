# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Regression guards for VERSION constant types and consistency."""

from __future__ import annotations


def test_display_version_is_str() -> None:
    """VERSION must be a display string, never a schema integer."""
    from custom_components.hospitable.const import VERSION

    assert isinstance(VERSION, str), f"VERSION must be str, got {type(VERSION)}"


def test_config_entry_version_is_int() -> None:
    """CONFIG_ENTRY_VERSION must be an integer schema version."""
    from custom_components.hospitable.const import CONFIG_ENTRY_VERSION

    assert isinstance(CONFIG_ENTRY_VERSION, int)


def test_config_entry_minor_version_is_int() -> None:
    """CONFIG_ENTRY_MINOR_VERSION must be an integer schema version."""
    from custom_components.hospitable.const import CONFIG_ENTRY_MINOR_VERSION

    assert isinstance(CONFIG_ENTRY_MINOR_VERSION, int)


def test_config_flow_uses_schema_constants() -> None:
    """ConfigFlow class attributes must match const schema versions."""
    from custom_components.hospitable.config_flow import HospitableConfigFlow
    from custom_components.hospitable.const import (
        CONFIG_ENTRY_MINOR_VERSION,
        CONFIG_ENTRY_VERSION,
    )

    assert HospitableConfigFlow.VERSION == CONFIG_ENTRY_VERSION
    assert HospitableConfigFlow.MINOR_VERSION == CONFIG_ENTRY_MINOR_VERSION


def test_sed_target_line_exists_in_const() -> None:
    """Guard: const.py must have a line matching the release sed pattern."""
    from pathlib import Path

    const_path = Path(__file__).resolve().parents[1] / (
        "custom_components/hospitable/const.py"
    )
    text = const_path.read_text()
    matching = [ln for ln in text.splitlines() if ln.startswith("VERSION = ")]
    assert len(matching) == 1, f"Expected 1 sed target, got {matching}"
