# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Guest identity model tests (T085, T086).

Guest data is tolerated exactly as it arrives upstream: a surname is
genuinely absent on one live reservation in twenty-nine, and a whole
``guest`` object can be null. ``profile_picture`` is never parsed at
all.
"""

from __future__ import annotations

from typing import Any

from tests.helpers import load_fixture


def _guest_payload(index: int) -> Any:
    """Return one fixture reservation's raw ``guest`` value.

    Args:
        index: Position of the reservation in the fixture.

    Returns:
        The raw guest object, or ``None`` for the null-guest fixture.
    """
    return load_fixture("reservation_with_guest.json")["data"][index]["guest"]


def test_guest_model_parses_the_four_default_fields() -> None:
    """The guest model parses first name, surname, location, and language."""
    from custom_components.hospitable.api import models

    guest = models.HospitableGuest.from_api(_guest_payload(0))

    assert guest is not None
    assert guest.first_name == "Example"
    assert guest.last_name == "Guest"
    assert guest.location == "Example City, Example Region"
    assert guest.language == "en"


def test_guest_model_parses_the_opt_in_contact_fields() -> None:
    """The guest model parses email and phone numbers for the opt-in surface."""
    from custom_components.hospitable.api import models

    guest = models.HospitableGuest.from_api(_guest_payload(0))

    assert guest is not None
    assert guest.email == "guest@example.com"
    assert guest.phone_numbers == ["+15550101001"]
    assert guest.guest_id == "guest-example-0001"


def test_guest_model_never_carries_a_profile_picture() -> None:
    """``profile_picture`` is not parsed into the model at all (FR-039d).

    Never reading the value is stronger than reading it and remembering
    not to expose it: an attribute that does not exist cannot leak onto
    any surface.
    """
    from custom_components.hospitable.api import models

    guest = models.HospitableGuest.from_api(_guest_payload(0))

    assert guest is not None
    assert not hasattr(guest, "profile_picture")
    assert "example.com/guest-avatar.png" not in repr(guest)


def test_guest_without_a_surname_parses_with_the_surname_absent() -> None:
    """A guest object with no ``last_name`` key parses (FR-039b).

    This is not hypothetical: one live reservation in twenty-nine had no
    surname.
    """
    from custom_components.hospitable.api import models

    guest = models.HospitableGuest.from_api(_guest_payload(1))

    assert guest is not None
    assert guest.first_name == "Anonymous"
    assert guest.last_name is None
    assert guest.language == "fr"


def test_null_guest_yields_no_guest_data_rather_than_an_error() -> None:
    """A ``null`` guest parses to no guest at all, never raising (FR-040)."""
    from custom_components.hospitable.api import models

    assert _guest_payload(2) is None
    assert models.HospitableGuest.from_api(None) is None
    assert models.HospitableGuest.from_api(_guest_payload(2)) is None


def test_reservation_model_carries_the_guest_beside_the_guest_counts() -> None:
    """The reservation gains singular ``guest`` without disturbing ``guests``.

    ``HospitableReservation.guests`` is the NUMERIC occupancy breakdown
    and keeps that meaning; the new singular ``guest`` is identity.
    """
    from custom_components.hospitable.api import models

    payload = load_fixture("reservation_with_guest.json")["data"][0]
    reservation = models.HospitableReservation.from_api(payload)

    assert reservation.guest is not None
    assert reservation.guest.first_name == "Example"
    assert reservation.guests.total == 3
    assert reservation.guests.adults == 2


def test_reservation_without_a_guest_key_parses_with_no_guest() -> None:
    """A reservation payload lacking ``guest`` entirely still parses (FR-040)."""
    from custom_components.hospitable.api import models

    payload = dict(load_fixture("reservation_accepted.json")["data"][0])
    payload.pop("guest", None)
    reservation = models.HospitableReservation.from_api(payload)

    assert reservation.guest is None
