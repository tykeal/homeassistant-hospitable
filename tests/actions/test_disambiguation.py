# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for multi-entry disambiguation (T029).

FR-008/FR-029: with exactly one loaded entry the ``config_entry_id``
field is optional; with two or more it becomes required, and an unknown
or unloaded id is a user-fixable error.

Observed discrepancy, reported not silently reconciled: the Hostaway
reference resolves entries through ``hass.data[DOMAIN]``. This
integration keeps per-entry state on ``entry.runtime_data``, so
resolution must enumerate loaded config entries for the domain instead.
Copying the Hostaway helper verbatim would resolve nothing here.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import pytest

from tests.actions.conftest import SECOND_ACCOUNT_NAMESPACE, SECOND_TOKEN


async def test_single_entry_resolves_without_an_explicit_id(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """One loaded entry is selected automatically."""
    from custom_components.hospitable.actions.helpers import (
        resolve_config_entry,
    )

    entry = await loaded_config_entry_factory(hass)

    assert resolve_config_entry(hass, None) is entry


async def test_two_entries_require_an_explicit_id(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """Two loaded entries make ``config_entry_id`` mandatory."""
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.hospitable.actions.helpers import (
        resolve_config_entry,
    )

    first = await loaded_config_entry_factory(hass)
    second = await loaded_config_entry_factory(
        hass, token=SECOND_TOKEN, account=SECOND_ACCOUNT_NAMESPACE
    )

    with pytest.raises(ServiceValidationError):
        resolve_config_entry(hass, None)

    assert resolve_config_entry(hass, first.entry_id) is first
    assert resolve_config_entry(hass, second.entry_id) is second


async def test_unknown_entry_id_is_rejected(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """An id that matches no Hospitable entry is a validation error."""
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.hospitable.actions.helpers import (
        resolve_config_entry,
    )

    await loaded_config_entry_factory(hass)

    with pytest.raises(ServiceValidationError):
        resolve_config_entry(hass, "not-a-real-entry-id")


async def test_unloaded_entry_id_is_rejected(
    hass: Any,
    loaded_config_entry_factory: Callable[..., Coroutine[Any, Any, Any]],
) -> None:
    """An entry that exists but is not loaded cannot serve a call.

    An unloaded entry has no ``runtime_data``, so accepting it would
    fail later with an opaque ``AttributeError`` instead of a message
    the user can act on.
    """
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.hospitable.actions.helpers import (
        resolve_config_entry,
    )

    first = await loaded_config_entry_factory(hass)
    await loaded_config_entry_factory(
        hass, token=SECOND_TOKEN, account=SECOND_ACCOUNT_NAMESPACE
    )
    assert await hass.config_entries.async_unload(first.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        resolve_config_entry(hass, first.entry_id)


async def test_no_loaded_entry_is_rejected(hass: Any) -> None:
    """With nothing loaded there is no account to act on."""
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.hospitable.actions.helpers import (
        resolve_config_entry,
    )

    with pytest.raises(ServiceValidationError):
        resolve_config_entry(hass, None)
