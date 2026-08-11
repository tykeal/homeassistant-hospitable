# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase tests for per-property timezone override resolution.

Covers T094 (FR-074): a per-property IANA override changes day-boundary
and date-relative presentation only; ``effective_timezone`` and
``timezone_source`` report the zone in use and its origin; an invalid
IANA name is rejected; and the D-11 guard holds at the sensor layer,
where no sensor reads any upstream fixed-offset ``timezone`` value.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from custom_components.hospitable.api.models import HospitableProperty
from tests.helpers import load_fixture


def _property() -> HospitableProperty:
    """Build a property carrying the upstream ``timezone: -0700`` field."""
    return HospitableProperty.from_api(load_fixture("properties_page1.json")["data"][0])


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T094 resolve_property_timezone not implemented",
)
async def test_no_override_reports_instance_source(hass: Any) -> None:
    """With no override the instance timezone and ``instance`` source apply."""
    from custom_components.hospitable.services.timezones import (  # type: ignore[attr-defined]
        resolve_property_timezone,
    )

    effective, source = await resolve_property_timezone(hass, None)
    assert effective == str(hass.config.time_zone)
    assert source == "instance"


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T094 resolve_property_timezone not implemented",
)
async def test_override_reports_override_source(hass: Any) -> None:
    """A valid override changes the zone and reports the ``override`` source."""
    from custom_components.hospitable.services.timezones import (  # type: ignore[attr-defined]
        resolve_property_timezone,
    )

    effective, source = await resolve_property_timezone(hass, "America/New_York")
    assert effective == "America/New_York"
    assert source == "override"


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T094 resolve_property_timezone not implemented",
)
async def test_invalid_iana_override_rejected(hass: Any) -> None:
    """A non-IANA override (a fixed offset) is rejected with ``ValueError``."""
    from custom_components.hospitable.services.timezones import (  # type: ignore[attr-defined]
        resolve_property_timezone,
    )

    with pytest.raises(ValueError):
        await resolve_property_timezone(hass, "-0700")


@pytest.mark.xfail(
    raises=ImportError,
    strict=True,
    reason="TDD red phase: T094 sensor/property.py not implemented",
)
def test_sensor_layer_never_reads_upstream_timezone() -> None:
    """The property_info sensor never surfaces the upstream fixed offset."""
    from custom_components.hospitable.sensor.property import (  # type: ignore
        HospitablePropertyInfoSensor,
    )

    property_model = _property()
    # D-11: the sanitized model deliberately drops the upstream timezone.
    assert not hasattr(property_model, "timezone")

    properties_coordinator = SimpleNamespace(
        data={property_model.property_id: property_model},
        consecutive_failures=0,
        monitored_property_ids={property_model.property_id},
    )
    sensor = HospitablePropertyInfoSensor(
        cast(Any, properties_coordinator),
        account_namespace="acct",
        property_id=property_model.property_id,
        property_name=property_model.name,
        effective_timezone="America/Los_Angeles",
        timezone_source="instance",
    )
    attributes = sensor.extra_state_attributes
    assert attributes["effective_timezone"] == "America/Los_Angeles"
    assert "-0700" not in repr(attributes)
