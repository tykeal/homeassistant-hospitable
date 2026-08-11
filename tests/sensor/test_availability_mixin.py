# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase three-strike availability mixin tests (T074)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast


def _entity(data: object, consecutive_failures: int) -> Any:
    """Build a Hospitable entity over a fake coordinator."""
    from custom_components.hospitable.entity import (
        HospitableEntity,
    )

    coordinator = SimpleNamespace(data=data, consecutive_failures=consecutive_failures)
    return HospitableEntity(cast(Any, coordinator))


def test_available_after_one_failure() -> None:
    """One consecutive failure keeps the entity available."""
    assert _entity(["state"], 1).available is True


def test_available_after_two_failures() -> None:
    """Two consecutive failures keep the entity available."""
    assert _entity(["state"], 2).available is True


def test_unavailable_on_third_failure() -> None:
    """The third consecutive failure makes the entity unavailable."""
    assert _entity(["state"], 3).available is False


def test_unavailable_when_no_data_ever() -> None:
    """An entity with no coordinator data is unavailable."""
    assert _entity(None, 0).available is False
