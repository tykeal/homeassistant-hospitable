# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Availability pricing tests (T137, FR-060).

Monetary values are integer minor currency units in the domain model and
are converted to a display float exactly once, in the sensor layer, via
``sensor.helpers.minor_units_to_float``. No float division happens before
that single conversion point, and the currency code travels with the
amount rather than being assumed.
"""

from __future__ import annotations

from tests.helpers import load_fixture


def test_model_holds_integer_minor_units() -> None:
    """The calendar day model holds an int minor-unit amount, never a float."""
    from custom_components.hospitable.api.models import HospitablePropertyCalendar

    payload = load_fixture("calendar_prop1.json")["data"]
    calendar = HospitablePropertyCalendar.from_api("prop-example-001", payload)

    available_day = calendar.days[0]
    assert available_day.price_minor_units == 6000
    assert isinstance(available_day.price_minor_units, int)
    assert not isinstance(available_day.price_minor_units, float)
    assert available_day.currency == "USD"

    # A null price degrades to ``None`` without inventing a zero.
    null_price_day = calendar.days[2]
    assert null_price_day.price_minor_units is None
    assert null_price_day.currency is None


def test_single_conversion_preserves_odd_minor_units() -> None:
    """A non-round minor-unit value converts exactly, proving no early math.

    6001 minor units must render as 60.01. Any float arithmetic performed
    before the single ``minor_units_to_float`` conversion point would risk
    accumulating rounding error and losing the trailing cent.
    """
    from custom_components.hospitable.api.models import HospitablePropertyCalendar
    from custom_components.hospitable.sensor.helpers import minor_units_to_float

    payload = load_fixture("calendar_prop1.json")["data"]
    calendar = HospitablePropertyCalendar.from_api("prop-example-001", payload)

    odd_day = calendar.days[1]
    assert odd_day.price_minor_units == 6001
    assert isinstance(odd_day.price_minor_units, int)
    assert minor_units_to_float(odd_day.price_minor_units, odd_day.currency) == 60.01
