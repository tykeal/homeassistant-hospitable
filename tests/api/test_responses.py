# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Red-phase response validation tests."""

from __future__ import annotations

import pytest

from tests.helpers import load_fixture


def test_response_validators_assert_honored_requests() -> None:
    """Assert envelope and include post-conditions."""
    from custom_components.hospitable.api.exceptions import (
        HospitableIncludeMissingError,
    )
    from custom_components.hospitable.api.responses import (
        assert_include,
        validate_list_envelope,
    )

    payload = load_fixture("reservations_include_missing.json")
    validate_list_envelope(payload, expected_page=1)
    with pytest.raises(HospitableIncludeMissingError):
        assert_include(payload["data"], "properties", endpoint="/reservations")
