# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""End-to-end guest identity tests over a real entry setup (US3).

Nothing here is a unit test: a real ``hass``, a real ``MockConfigEntry``,
the real entity registry, and ``respx``-mocked endpoints drive the whole
platform. If the include, the model, the platform forward, the option
gate, or ``_unrecorded_attributes`` were broken, these would fail.

No request is ever made to the live host: every route is mocked.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState

from tests.helpers.guest_entry import (
    PROFILE_PICTURE,
    mock_endpoints,
    reservation_entity_id,
    setup_guest_entry,
)

_RED_E2E = "TDD red phase: US3 guest attributes do not reach the entity"


@pytest.mark.xfail(raises=AssertionError, strict=True, reason=_RED_E2E)
async def test_guest_attributes_land_on_a_real_entity(
    hass: Any, respx_router: Any
) -> None:
    """A real setup puts the four default guest attributes on the state."""
    route = mock_endpoints(respx_router)
    await setup_guest_entry(hass, guest_contact=False)

    query = route.calls.last.request.url.params
    assert query.get("include") == "guest,properties"

    state = hass.states.get(reservation_entity_id(hass, "prop-example-001"))
    assert state is not None
    assert state.attributes["guest_first_name"] == "Example"
    assert state.attributes["guest_last_name"] == "Guest"
    assert state.attributes["guest_location"] == "Example City, Example Region"
    assert state.attributes["guest_language"] == "en"


@pytest.mark.xfail(raises=AssertionError, strict=True, reason=_RED_E2E)
async def test_a_null_guest_entity_reports_no_identity(
    hass: Any, respx_router: Any
) -> None:
    """The property whose stay has a null guest exposes no identity."""
    mock_endpoints(respx_router)
    await setup_guest_entry(hass, guest_contact=False)

    state = hass.states.get(reservation_entity_id(hass, "prop-example-002"))
    assert state is not None
    assert "guest_first_name" in state.attributes
    assert state.attributes["guest_first_name"] is None
    assert state.attributes["guest_last_name"] is None


@pytest.mark.xfail(raises=AssertionError, strict=True, reason=_RED_E2E)
async def test_contact_details_are_absent_by_default_on_a_real_entity(
    hass: Any, respx_router: Any
) -> None:
    """Contact attributes are absent by default (FR-039c, FR-038b).

    The ``guest_first_name`` assertion proves guest data reached the
    entity, so the absence below is the gate working rather than an
    empty payload.
    """
    mock_endpoints(respx_router)
    await setup_guest_entry(hass, guest_contact=False)

    state = hass.states.get(reservation_entity_id(hass, "prop-example-001"))
    assert state is not None
    assert state.attributes.get("guest_first_name") == "Example"
    assert "guest_email" not in state.attributes
    assert "guest_phone_numbers" not in state.attributes


@pytest.mark.xfail(raises=AssertionError, strict=True, reason=_RED_E2E)
async def test_opting_in_exposes_contact_details_on_a_real_entity(
    hass: Any, respx_router: Any
) -> None:
    """With the option enabled the contact attributes appear."""
    mock_endpoints(respx_router)
    await setup_guest_entry(hass, guest_contact=True)

    state = hass.states.get(reservation_entity_id(hass, "prop-example-001"))
    assert state is not None
    assert state.attributes.get("guest_email") == "guest@example.com"
    assert state.attributes.get("guest_phone_numbers") == ["+15550101001"]


@pytest.mark.xfail(raises=AssertionError, strict=True, reason=_RED_E2E)
async def test_profile_picture_never_reaches_a_real_entity_state(
    hass: Any, respx_router: Any
) -> None:
    """``profile_picture`` is absent from real entity state (FR-039d).

    Checked with the opt-in ON — the most permissive configuration —
    and across EVERY entity the integration creates rather than only the
    reservation sensor, because a control scoped to one surface does not
    protect another (FR-046).
    """
    mock_endpoints(respx_router)
    entry = await setup_guest_entry(hass, guest_contact=True)

    reservation_state = hass.states.get(reservation_entity_id(hass, "prop-example-001"))
    assert reservation_state is not None
    assert reservation_state.attributes.get("guest_first_name") == "Example"

    states = hass.states.async_all()
    assert len(states) > 1, "no entity state was inspected"
    for state in states:
        rendered = repr(state.attributes)
        assert "profile_picture" not in rendered
        assert PROFILE_PICTURE not in rendered
        assert "avatar" not in rendered

    assert entry.state is ConfigEntryState.LOADED


@pytest.mark.xfail(raises=AssertionError, strict=True, reason=_RED_E2E)
async def test_guest_attributes_are_unrecorded_on_the_real_state_object(
    hass: Any, respx_router: Any
) -> None:
    """Home Assistant itself reports the guest attributes as unrecorded.

    ``State.state_info["unrecorded_attributes"]`` is the value the
    recorder consults, so asserting it proves the declaration is honoured
    by the framework rather than merely present as a class attribute.
    """
    mock_endpoints(respx_router)
    await setup_guest_entry(hass, guest_contact=True)

    state = hass.states.get(reservation_entity_id(hass, "prop-example-001"))
    assert state is not None
    state_info = state.state_info
    assert state_info is not None
    unrecorded = state_info["unrecorded_attributes"]

    for name in (
        "guest_first_name",
        "guest_last_name",
        "guest_location",
        "guest_language",
        "guest_email",
        "guest_phone_numbers",
    ):
        assert name in unrecorded, f"{name} would be written to the recorder"

    # The operational identifier is deliberately NOT unrecorded: it is
    # not personal data and automations need its history.
    assert "reservation_id" not in unrecorded
