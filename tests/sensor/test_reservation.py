# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase reservation sensor state tests (T072)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any

from custom_components.hospitable.api.models import HospitableReservation
from tests.helpers import load_fixture

NINE_OPTIONS = {
    "no_reservation",
    "awaiting_checkin",
    "occupied",
    "checked_out",
    "pending_request",
    "checkpoint",
    "cancelled",
    "not_accepted",
    "unknown",
}


def _module() -> Any:
    """Import the not-yet-implemented reservation sensor module."""
    import custom_components.hospitable.sensor.reservation as reservation

    return reservation


def _reservation(fixture: str) -> HospitableReservation:
    """Build a reservation model from a fixture's first item."""
    return HospitableReservation.from_api(load_fixture(fixture)["data"][0])


def test_exactly_one_sensor_per_property() -> None:
    """The builder yields exactly one reservation sensor per property."""
    module = _module()
    coordinator = SimpleNamespace(data=[], consecutive_failures=0)
    sensors = module.build_reservation_sensors(
        coordinator,
        "acct",
        {"prop-example-001": "One", "prop-example-002": "Two"},
    )
    assert len(sensors) == 2
    unique_ids = {sensor.unique_id for sensor in sensors}
    assert unique_ids == {
        "acct_prop-example-001_reservation_status",
        "acct_prop-example-002_reservation_status",
    }


def test_options_are_the_nine_without_unavailable() -> None:
    """The enum options are exactly the nine states and never unavailable."""
    module = _module()
    assert set(module.RESERVATION_STATUS_OPTIONS) == NINE_OPTIONS
    assert len(module.RESERVATION_STATUS_OPTIONS) == 9
    assert "unavailable" not in module.RESERVATION_STATUS_OPTIONS

    coordinator = SimpleNamespace(data=[], consecutive_failures=0)
    sensor = module.HospitableReservationSensor(
        coordinator,
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )
    assert set(sensor.options) == NINE_OPTIONS


def test_state_is_always_one_of_nine_options() -> None:
    """Every computed state is a member of the enum option set."""
    module = _module()
    coordinator = SimpleNamespace(
        data=[_reservation("reservation_accepted.json")], consecutive_failures=0
    )
    sensor = module.HospitableReservationSensor(
        coordinator,
        account_namespace="acct",
        property_id="prop-example-001",
        property_name="Example",
    )
    now = datetime.fromisoformat("2025-06-15T12:00:00-07:00")
    state = sensor._compute_state(now)
    assert state == "occupied"
    assert state in NINE_OPTIONS


# --- US3 guest identity on the reservation entity (T089 to T093) ---------
#
# Each "must be absent" test ALSO asserts that other guest data IS
# present. Without that, an absence test would pass even if guest data
# never reached the entity, asserting nothing.


GUEST_ATTRIBUTES = (
    "guest_first_name",
    "guest_last_name",
    "guest_location",
    "guest_language",
)
GUEST_CONTACT_ATTRIBUTES = ("guest_email", "guest_phone_numbers")
PROFILE_PICTURE_URLS = (
    "https://example.com/guest-avatar.png",
    "https://example.com/guest-avatar-2.png",
)


def _guest_reservation(index: int) -> HospitableReservation:
    """Build a reservation from the guest fixture at ``index``."""
    payload = load_fixture("reservation_with_guest.json")["data"][index]
    return HospitableReservation.from_api(payload)


def _guest_sensor(
    reservations: list[HospitableReservation],
    *,
    property_id: str = "prop-example-001",
    guest_contact: bool = False,
) -> Any:
    """Build a reservation sensor over the given reservations.

    The opt-in is expressed the way the real integration expresses it,
    through the coordinator's config entry options, so this helper
    cannot pass through a door the production wiring does not have.
    """
    from custom_components.hospitable.const import CONF_GUEST_CONTACT_DETAILS

    module = _module()
    coordinator = SimpleNamespace(
        data=reservations,
        consecutive_failures=0,
        config_entry=SimpleNamespace(
            options={CONF_GUEST_CONTACT_DETAILS: guest_contact}
        ),
    )
    return module.HospitableReservationSensor(
        coordinator,
        account_namespace="acct",
        property_id=property_id,
        property_name="Example",
    )


def test_guest_identity_attributes_are_exposed_by_default() -> None:
    """The four default guest attributes land on the entity (FR-039a)."""
    attributes = _guest_sensor([_guest_reservation(0)]).extra_state_attributes

    for name in GUEST_ATTRIBUTES:
        assert name in attributes, f"{name} is not exposed at all"
    assert attributes["guest_first_name"] == "Example"
    assert attributes["guest_last_name"] == "Guest"
    assert attributes["guest_location"] == "Example City, Example Region"
    assert attributes["guest_language"] == "en"


def test_a_missing_surname_degrades_gracefully() -> None:
    """A guest with no surname keeps its first name (FR-039b)."""
    attributes = _guest_sensor([_guest_reservation(1)]).extra_state_attributes

    for name in GUEST_ATTRIBUTES:
        assert name in attributes, f"{name} is not exposed at all"
    assert attributes["guest_first_name"] == "Anonymous"
    assert attributes["guest_last_name"] is None
    assert attributes["guest_language"] == "fr"


def test_a_null_guest_reports_no_identity_at_all() -> None:
    """A null guest yields no identity values (FR-040).

    The attribute KEYS stay present carrying ``None``, matching
    ``contracts/entities.md`` and the existing no-reservation branch, so
    a template referencing them never raises. What must never happen is
    a VALUE appearing.
    """
    attributes = _guest_sensor(
        [_guest_reservation(2)], property_id="prop-example-002"
    ).extra_state_attributes

    for name in GUEST_ATTRIBUTES:
        assert name in attributes, f"{name} key must remain stable"
        assert attributes[name] is None, f"{name} must carry no identity"


def test_no_reservation_reports_no_guest_identity() -> None:
    """With no reservation selected the guest attributes are all None."""
    attributes = _guest_sensor([]).extra_state_attributes

    for name in GUEST_ATTRIBUTES:
        assert name in attributes
        assert attributes[name] is None


def test_guest_contact_details_are_absent_by_default() -> None:
    """Email and phone are NOT created unless opted in (FR-039c, FR-038b).

    The first assertion is load-bearing: it proves guest data reached
    the entity, so the absence below is the OPT-IN doing its work rather
    than there being nothing to expose.
    """
    attributes = _guest_sensor([_guest_reservation(0)]).extra_state_attributes

    assert attributes.get("guest_first_name") == "Example"
    for name in GUEST_CONTACT_ATTRIBUTES:
        assert name not in attributes, f"{name} must not exist by default"
    rendered = repr(attributes)
    assert "guest@example.com" not in rendered
    assert "+15550101001" not in rendered


def test_guest_contact_details_appear_only_when_opted_in() -> None:
    """The opt-in adds email and phone attributes (FR-039c)."""
    attributes = _guest_sensor(
        [_guest_reservation(0)], guest_contact=True
    ).extra_state_attributes

    assert attributes.get("guest_email") == "guest@example.com"
    assert attributes.get("guest_phone_numbers") == ["+15550101001"]


def test_profile_picture_is_never_an_entity_attribute() -> None:
    """``profile_picture`` cannot appear under ANY option (FR-039d).

    Both option states, both guests that have a picture, key AND value.
    The ``guest_first_name`` assertion keeps this honest: it proves the
    guest object with the picture in it genuinely reached the entity.
    """
    for guest_contact in (False, True):
        for index in (0, 1):
            attributes = _guest_sensor(
                [_guest_reservation(index)], guest_contact=guest_contact
            ).extra_state_attributes
            assert attributes.get("guest_first_name") is not None
            rendered = repr(attributes)
            assert "profile_picture" not in rendered
            assert "guest_profile_picture" not in attributes
            for url in PROFILE_PICTURE_URLS:
                assert url not in rendered
            assert "avatar" not in rendered


def test_every_guest_attribute_is_unrecorded() -> None:
    """No guest attribute may reach the recorder database (FR-039e).

    ``_unrecorded_attributes`` is a CLASS attribute, so it must name the
    opt-in fields too: the class cannot know whether the option is on.
    """
    module = _module()
    unrecorded = module.HospitableReservationSensor._unrecorded_attributes

    for name in (*GUEST_ATTRIBUTES, *GUEST_CONTACT_ATTRIBUTES):
        assert name in unrecorded, f"{name} would be written to the recorder"


def test_the_reservation_uuid_is_exposed_for_service_targeting() -> None:
    """The reservation UUID is readable from an entity attribute (FR-044).

    NOT a red-phase test. The shipped attribute is ``reservation_id``
    and it already carries the UUID, so this is a characterization test
    guarding that guarantee rather than new behaviour.
    ``contracts/entities.md`` names the attribute ``reservation_uuid``;
    the code is followed instead, rather than shipping one value under
    two keys.
    """
    attributes = _guest_sensor([_guest_reservation(0)]).extra_state_attributes

    assert attributes["reservation_id"] == "res-example-guest-full"
