# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""VS-7 — the entity-surface PII audit by ALLOWLIST (T153).

**Principle XII status: CHARACTERIZATION.** Every assertion describes
behaviour US3 to US5 already shipped, so this file lands green in one
commit rather than as a red/green pair.

**Scope, stated because scope is where this project's defects live.**
T153a audits the SERVICE RESPONSE surface. This file audits the four
surfaces that one does not reach:

1. entity ATTRIBUTES, enumerated exhaustively against an allowlist;
2. log records at DEBUG and above;
3. the diagnostics download;
4. the recorder, via ``_unrecorded_attributes``.

FR-046 exists because a control scoped to one of these does not reach
the others. Naming all four here is the point.

Everything runs with EVERY option ON — the most permissive
configuration the integration can be in. Auditing at defaults would
audit the safe case.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from tests.helpers.audit_entry import (
    GUEST_SECRETS,
    MESSAGE_BODY,
    setup_audit_entry,
)
from tests.helpers.surface import entity_attributes

# Every attribute this integration is permitted to publish, grouped by
# the entity that owns it. Compared as an EXACT set per entity: a new
# attribute fails here and has to be classified, which a denylist of
# known-bad names could never do.
ALLOWED_ATTRIBUTES: dict[str, frozenset[str]] = {
    "reservation_status": frozenset(
        {
            "reservation_id",
            "arrival_date",
            "departure_date",
            "nights",
            "scheduled_checkin",
            "scheduled_checkout",
            "guests_total",
            "guests_adults",
            "guests_children",
            "guests_infants",
            "guests_pets",
            "booking_channel",
            "channel_confirmation",
            "booking_date",
            "stay_type",
            "status_sub_category",
            "upcoming_reservations",
            # Guest identity released by default (FR-039a).
            "guest_first_name",
            "guest_last_name",
            "guest_location",
            "guest_language",
            # Guest CONTACT ROUTES, only behind the opt-in (FR-039c).
            "guest_email",
            "guest_phone_numbers",
        }
    ),
    "next_arrival": frozenset(),
    "next_departure": frozenset(),
    "upcoming_reservations": frozenset(),
    "property_info": frozenset(
        {
            "address",
            "checkin_time",
            "checkout_time",
            "effective_timezone",
            "listings",
            "listings_available",
            "max_guests",
            "timezone_source",
        }
    ),
    "availability": frozenset(
        {
            "closed_for_checkin",
            "closed_for_checkout",
            "currency",
            "forward_window",
            "min_stay",
            "nightly_rate",
        }
    ),
    "last_message": frozenset(),
    # No body, no sender identity, no message count. ``MessagePresence``
    # carries none of them, so this cannot grow one by accident.
    "awaiting_host_reply": frozenset({"last_guest_message_at"}),
    "next_task": frozenset(
        {
            "assignment_status",
            "assignment_updated_at",
            "duration_hours",
            "end_date",
            "progress_status",
            "reservation_id",
            "service_id",
            "service_type",
            "start_date",
            "task_id",
            "task_type",
            "teammate_id",
            "timezone",
        }
    ),
    "task_count": frozenset({"completed_count", "in_progress_count", "pending_count"}),
}


def _entity_kind(entity_id: str) -> str:
    """Return which allowlist group an entity id belongs to.

    Args:
        entity_id: A registered entity id.

    Returns:
        The matching allowlist key.

    Raises:
        AssertionError: The entity matches no declared group, which
            means a new entity shipped unaudited.
    """
    # Longest first, so ``upcoming_reservations`` is not swallowed by a
    # shorter key that is a suffix of it.
    for kind in sorted(ALLOWED_ATTRIBUTES, key=len, reverse=True):
        if entity_id.endswith(f"_{kind}"):
            return kind
    raise AssertionError(
        f"{entity_id} belongs to no declared attribute group, so it shipped "
        "without being audited. Add it to ALLOWED_ATTRIBUTES."
    )


@pytest.mark.parametrize("guest_contact", [False, True])
async def test_every_entity_attribute_is_allowlisted(
    hass: Any, respx_router: Any, guest_contact: bool
) -> None:
    """No entity publishes an attribute nobody has classified (T153).

    The counterpart of the service-response allowlist, on the surface
    that one does not reach (FR-046).
    """
    await setup_audit_entry(hass, respx_router, guest_contact=guest_contact)
    published = entity_attributes(hass)
    assert published, "no entities were created, so this audit is vacuous"
    for entity_id, attributes in published.items():
        permitted = ALLOWED_ATTRIBUTES[_entity_kind(entity_id)]
        unexpected = attributes - permitted
        assert not unexpected, (
            f"{entity_id} publishes unclassified attributes "
            f"{sorted(unexpected)}. Classify each one before releasing it."
        )


@pytest.mark.parametrize("guest_contact", [True, False])
async def test_guest_contact_attributes_track_the_option(
    hass: Any, respx_router: Any, guest_contact: bool
) -> None:
    """Contact attributes appear only with the opt-in on (FR-039c).

    Asserted in both directions so the OFF case is a control working
    rather than an empty guest object.

    Parametrized rather than looped on purpose. Looping both settings
    inside one test set up a second entry alongside the first, and the
    ``next()`` below then matched whichever ``_reservation_status``
    entity the state machine happened to yield first -- which, after
    unloading the first entry, was a stale one with no attributes at
    all. The OFF assertion passed for entirely the wrong reason.
    """
    contact = {"guest_email", "guest_phone_numbers"}
    await setup_audit_entry(hass, respx_router, guest_contact=guest_contact)

    targets = {
        state.entity_id: state.attributes
        for state in hass.states.async_all()
        if state.entity_id.endswith("_reservation_status")
    }
    assert len(targets) == 2, (
        f"expected one reservation-status entity per property, got "
        f"{sorted(targets)}; a different count means the fixture changed "
        "and this audit is no longer covering what it claims"
    )

    # Keyed on VALUE, not on key presence. The null-guest reservation
    # still publishes every guest_* KEY with a None value, which is
    # deliberate: FR-040 holds that a guest being ABSENT is not private,
    # and omitting the keys would hide it. An earlier draft of this test
    # keyed on presence and so could not tell the populated entity from
    # the empty one at all.
    populated = [
        attributes
        for attributes in targets.values()
        if attributes.get("guest_first_name") is not None
    ]
    assert len(populated) == 1, (
        "expected exactly one entity to carry a populated guest -- the "
        "fixture gives one reservation a full guest and one a null "
        "guest. Without that, the assertions below prove nothing."
    )
    assert populated[0]["guest_last_name"] is not None

    published_contact = {key for key in contact if key in populated[0]}
    assert bool(published_contact) is guest_contact, (
        f"guest contact attributes with the option {guest_contact}: "
        f"{sorted(published_contact)}"
    )
    if guest_contact:
        assert populated[0]["guest_email"] is not None
        assert populated[0]["guest_phone_numbers"]
    else:
        for entity_id, attributes in targets.items():
            leaked = contact & set(attributes)
            assert not leaked, (
                f"{entity_id} published {sorted(leaked)} with the "
                "guest-contact opt-in OFF"
            )


async def test_no_guest_or_message_value_reaches_a_log_record(
    hass: Any, respx_router: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """A full setup at DEBUG logs no guest value and no body (FR-041).

    The attribute assertion first is what stops this being a tautology:
    it proves guest data really flowed onto an entity, so a clean log
    is a control working rather than an empty pipeline.
    """
    caplog.set_level(logging.DEBUG)
    await setup_audit_entry(hass, respx_router, guest_contact=True)

    published = entity_attributes(hass)
    target = next(
        entity_id
        for entity_id in published
        if entity_id.endswith("_reservation_status")
    )
    state = hass.states.get(target)
    assert state is not None
    assert state.attributes.get("guest_first_name"), (
        "no guest data reached the entity, so a clean log proves nothing"
    )

    logged = "\n".join(record.getMessage() for record in caplog.records)
    for secret in (*GUEST_SECRETS, MESSAGE_BODY):
        assert secret not in logged, f"guest value {secret!r} reached a log record"


async def test_no_guest_or_message_value_reaches_diagnostics(
    hass: Any, respx_router: Any
) -> None:
    """The diagnostics download carries no guest value (FR-042).

    The diagnostics SURFACE, including the missing-entry-point defect
    this audit uncovered, is covered in full by
    ``tests/test_diagnostics_platform.py``. It is named here too so
    that this file's four-surface claim is not a claim about three.
    """
    from custom_components.hospitable.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = await setup_audit_entry(hass, respx_router, guest_contact=True)
    dump = json.dumps(
        await async_get_config_entry_diagnostics(hass, entry), default=str
    )
    for secret in (*GUEST_SECRETS, MESSAGE_BODY):
        assert secret not in dump, f"guest value {secret!r} reached diagnostics"


async def test_every_guest_attribute_is_excluded_from_the_recorder(
    hass: Any, respx_router: Any
) -> None:
    """No guest attribute is recorder-eligible (FR-039e, FR-043).

    Driven off the PUBLISHED attribute set rather than a literal list,
    so a guest attribute added later is covered without editing this
    test. Entity state memory is one surface; the recorder database and
    the backups taken from it are another (FR-046).
    """
    from custom_components.hospitable.sensor.reservation import (
        HospitableReservationSensor,
    )

    await setup_audit_entry(hass, respx_router, guest_contact=True)
    published = next(
        attributes
        for entity_id, attributes in entity_attributes(hass).items()
        if entity_id.endswith("_reservation_status")
    )
    guest_attributes = {name for name in published if name.startswith("guest_")}
    assert guest_attributes, "no guest attributes were published to audit"
    unrecorded = HospitableReservationSensor._unrecorded_attributes
    assert guest_attributes <= unrecorded, (
        f"guest attributes reach the recorder: {sorted(guest_attributes - unrecorded)}"
    )


async def test_the_message_timestamp_attribute_is_excluded_too(
    hass: Any, respx_router: Any
) -> None:
    """The guest-message timestamp is unrecorded (FR-043).

    A conversation timestamp is not identity, but it is a behavioural
    record of a named stay and has no value as long-term history.
    """
    from custom_components.hospitable.sensor.messages import (
        HospitableAwaitingHostReplySensor,
    )

    await setup_audit_entry(hass, respx_router, guest_contact=False)
    published = entity_attributes(hass)
    awaiting = next(
        attributes
        for entity_id, attributes in published.items()
        if entity_id.endswith("_awaiting_host_reply")
    )
    assert awaiting == {"last_guest_message_at"}
    assert awaiting <= HospitableAwaitingHostReplySensor._unrecorded_attributes


async def test_the_audit_reached_every_property(hass: Any, respx_router: Any) -> None:
    """Both properties are audited, not just the first.

    A per-property fan-out that silently covered one property would
    make every assertion above narrower than it reads.
    """
    await setup_audit_entry(hass, respx_router, guest_contact=True)
    audited = set(entity_attributes(hass))
    for kind in ALLOWED_ATTRIBUTES:
        matching = {name for name in audited if name.endswith(f"_{kind}")}
        assert len(matching) >= 2, (
            f"only {len(matching)} {kind} entities were audited; the "
            "two-property fan-out is not being covered"
        )
    # Named entity slugs, not a count. A count of two proves only that
    # two entities exist; if the fan-out produced two entities for the
    # SAME property the count would still pass. The reviewer was right
    # that the previous line here was vacuous -- it ended in
    # "or audited", which short-circuits truthy and could never fail.
    slugs = {"example_beach_house", "example_mountain_cabin"}
    for slug in slugs:
        assert any(slug in name for name in audited), (
            f"no entity for {slug} was audited; the fan-out covered "
            "fewer properties than the per-kind counts imply"
        )
