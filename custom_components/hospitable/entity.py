# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Entity and device identifier helpers for Hospitable properties."""

from __future__ import annotations

import re

from custom_components.hospitable.const import DOMAIN


def _slugify(value: str) -> str:
    """Return a Home Assistant style slug."""
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", value.casefold())).strip("_")


def build_unique_id(account_namespace: str, property_id: str, entity_key: str) -> str:
    """Build the frozen unique identifier for a property entity."""
    return f"{account_namespace}_{property_id}_{entity_key}"


def build_suggested_object_id(property_name: str, entity_key: str) -> str:
    """Build the default entity object identifier."""
    return f"hospitable_{_slugify(property_name)}_{entity_key}"


def build_device_identifier(
    account_namespace: str, property_id: str
) -> tuple[str, str]:
    """Build the device registry identifier tuple."""
    return (DOMAIN, f"{account_namespace}_{property_id}")
