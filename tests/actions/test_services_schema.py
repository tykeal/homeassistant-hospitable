# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Validate services.yaml target blocks against hassfest rules.

Catches target-level schema violations (like forbidden device keys)
locally instead of relying on the CI-only hassfest validator.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import voluptuous as vol
from homeassistant.helpers import selector
from homeassistant.util.yaml import load_yaml_dict

SERVICES_YAML = (
    Path(__file__).resolve().parents[2]
    / "custom_components"
    / "hospitable"
    / "services.yaml"
)


def _raise_on_target_device_filter(
    value: dict[str, object],
) -> dict[str, object]:
    """Reject any device key under target (mirrors hassfest)."""
    if "device" in value:
        raise vol.Invalid(
            "Services do not support device filters on target, "
            "use a device selector instead"
        )
    return value


_TARGET_SCHEMA = vol.All(
    selector.TargetSelector.CONFIG_SCHEMA,
    _raise_on_target_device_filter,
)


def _load_services() -> dict[str, object]:
    """Load and return parsed services.yaml."""
    return load_yaml_dict(str(SERVICES_YAML))


def test_no_device_filter_under_target() -> None:
    """No service uses a device filter under target (hassfest rule)."""
    data = _load_services()
    for svc_name, svc_def in data.items():
        if svc_def is None:
            continue
        if not isinstance(svc_def, dict):
            pytest.fail(f"Service '{svc_name}' definition is not a mapping")
        target = svc_def.get("target")
        if target is None:
            continue
        try:
            _TARGET_SCHEMA(target)
        except vol.Invalid as exc:
            pytest.fail(f"Service '{svc_name}' has invalid target: {exc}")
