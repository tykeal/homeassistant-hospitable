# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Write-isolation gates 1 to 3 for spec 002 (T022-T024, FR-001).

Spec 001 made writes structurally impossible: the client had no write
method. Spec 002 must permit a POST from a service handler, so that
guarantee drops to TEST-ENFORCED. research.md D-01 compensates with four
independent gates, three of which live here and the fourth of which is
the narrowed ``tests/test_no_writes.py``:

1. Typing: the coordinator's client attribute is annotated as the base
   GET-only client, which has no ``_post``, so ``client._post(...)`` is
   a mypy error rather than a runtime surprise.
2. Runtime: no coordinator instance is a ``HospitableWriteClient``.
3. Static: no polling-lifecycle module imports the write client, imports
   from the ``actions`` package, or references ``_post``.
4. Lifecycle: zero non-GET requests during the polling lifecycle.

Observed discrepancy, reported not silently reconciled: D-01 gate 2 is
written against a public ``coordinator.client``, but coordinators store
the client privately as ``self._client``. These tests require a public
read-only accessor so the gate can be written as D-01 specifies. That is
a design decision made here deliberately, not a silent fix.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import respx
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.actions.conftest import (
    ACCOUNT_NAMESPACE,
    SYNTHETIC_TOKEN,
    mock_polling_endpoints,
)

INTEGRATION_ROOT = Path("custom_components/hospitable")
COORDINATOR_MODULE = INTEGRATION_ROOT / "coordinator.py"
CONFIG_FLOW_MODULE = INTEGRATION_ROOT / "config_flow.py"
SENSOR_PACKAGE = INTEGRATION_ROOT / "sensor"
BASE_CLIENT_NAME = "HospitableApiClient"


def test_gate_1_coordinators_annotate_the_base_client_type() -> None:
    """Coordinators type their client as the GET-only base client.

    Asserting the annotation AND that the annotated class has no
    ``_post`` is what makes this equivalent to "mypy rejects ``_post`` at
    the call site": the attribute's static type simply has no such
    member, and mypy runs over this tree in CI on every commit.
    """
    from custom_components.hospitable.api.client import HospitableApiClient
    from tests.helpers.ast_isolation import (
        annotated_assignment_types,
        returned_annotations,
    )

    assert not hasattr(HospitableApiClient, "_post")
    assert annotated_assignment_types(COORDINATOR_MODULE, "_client") == {
        BASE_CLIENT_NAME
    }, "every coordinator must annotate self._client as the base client"
    assert returned_annotations(COORDINATOR_MODULE, "client") == {BASE_CLIENT_NAME}, (
        "the public client accessor must be annotated as the base client"
    )


async def test_gate_2_no_coordinator_holds_a_write_client(
    hass: Any, respx_router: respx.Router
) -> None:
    """No coordinator instance is constructed with a write client."""
    from custom_components.hospitable import const
    from custom_components.hospitable.api.const import BASE_URL

    mock_polling_endpoints(respx_router, BASE_URL)
    entry = MockConfigEntry(
        domain=const.DOMAIN,
        data={
            const.CONF_TOKEN: SYNTHETIC_TOKEN,
            const.CONF_ACCOUNT_NAMESPACE: ACCOUNT_NAMESPACE,
            const.CONF_NAMESPACE_SOURCE: "account",
        },
        options={
            const.CONF_SELECTED_PROPERTIES: ["prop-example-001", "prop-example-002"],
            const.CONF_LOOKAHEAD_DAYS: 30,
        },
        unique_id=ACCOUNT_NAMESPACE,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinators = entry.runtime_data["coordinators"]
    assert set(coordinators) == {"properties", "reservations", "calendar"}
    for name, coordinator in coordinators.items():
        assert hasattr(coordinator, "client"), (
            f"coordinator {name} exposes no public client accessor"
        )

    from custom_components.hospitable.api.client import HospitableApiClient
    from custom_components.hospitable.api.write_client import (
        HospitableWriteClient,
    )

    for name, coordinator in coordinators.items():
        assert isinstance(coordinator.client, HospitableApiClient), name
        assert not isinstance(coordinator.client, HospitableWriteClient), name


def test_gate_3_polling_modules_never_name_write_symbols() -> None:
    """No polling-lifecycle module reaches for a write-capable symbol.

    The existence assertions come first on purpose. A scan that finds no
    violation because the write client and the ``actions`` package do not
    exist yet proves nothing; the gate is only meaningful once there is
    something to isolate.
    """
    from tests.helpers.ast_isolation import scan_paths

    actions_package = INTEGRATION_ROOT / "actions"
    assert actions_package.is_dir(), "the actions package must exist to be isolated"
    assert (INTEGRATION_ROOT / "api/write_client.py").is_file(), (
        "the write client must exist to be isolated"
    )

    scanned = scan_paths([COORDINATOR_MODULE, CONFIG_FLOW_MODULE, SENSOR_PACKAGE])
    assert scanned, "the static scan matched no modules"
    for path, facts in scanned.items():
        assert not facts.references("HospitableWriteClient"), path
        assert not facts.references("_post"), path
        assert not facts.imports_from("custom_components.hospitable.actions"), path
        assert not facts.imports_from(
            "custom_components.hospitable.api.write_client"
        ), path


def test_gate_3_scan_covers_every_polling_module() -> None:
    """The gate 3 scan really reaches the modules it claims to cover.

    Guards against the scan silently matching nothing, which would make
    gate 3 vacuous regardless of what the modules contain.
    """
    from tests.helpers.ast_isolation import scan_paths

    scanned = scan_paths([COORDINATOR_MODULE, CONFIG_FLOW_MODULE, SENSOR_PACKAGE])
    covered = {path.as_posix() for path in scanned}

    assert COORDINATOR_MODULE.as_posix() in covered
    assert CONFIG_FLOW_MODULE.as_posix() in covered
    assert len([name for name in covered if "/sensor/" in name]) >= 4
