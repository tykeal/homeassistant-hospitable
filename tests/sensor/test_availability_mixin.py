# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase three-strike availability mixin tests (T074)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest


def _entity(data: object, consecutive_failures: int) -> Any:
    """Build a Hospitable entity over a fake coordinator."""
    from custom_components.hospitable.entity import (  # type: ignore
        HospitableEntity,
    )

    coordinator = SimpleNamespace(data=data, consecutive_failures=consecutive_failures)
    return HospitableEntity(coordinator)


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T074 availability mixin not implemented",
)
def test_available_after_one_failure() -> None:
    """One consecutive failure keeps the entity available."""
    assert _entity(["state"], 1).available is True


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T074 availability mixin not implemented",
)
def test_available_after_two_failures() -> None:
    """Two consecutive failures keep the entity available."""
    assert _entity(["state"], 2).available is True


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T074 availability mixin not implemented",
)
def test_unavailable_on_third_failure() -> None:
    """The third consecutive failure makes the entity unavailable."""
    assert _entity(["state"], 3).available is False


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T074 availability mixin not implemented",
)
def test_unavailable_when_no_data_ever() -> None:
    """An entity with no coordinator data is unavailable."""
    assert _entity(None, 0).available is False
