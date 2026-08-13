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
    # Exact rather than a subset: a NEW coordinator cannot join the
    # lifecycle without being named here and therefore proved to hold
    # the GET-only client by the assertions below.
    assert set(coordinators) == {"properties", "reservations", "calendar", "tasks"}
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


# --- US4 extension of gates 1 to 3 (T130, FR-001) -----------------------
#
# These ADD to the gates above; nothing existing is relaxed. US4
# introduces a new coordinator module and a new sensor module, and a
# gate that silently stopped covering them would be worse than no gate:
# it would still report green while the newest code went unchecked.

TASKS_COORDINATOR_MODULE = INTEGRATION_ROOT / "coordinator_tasks.py"
OPTIONS_FLOW_MODULE = INTEGRATION_ROOT / "options_flow.py"
TASKS_SENSOR_MODULE = SENSOR_PACKAGE / "tasks.py"

US4_POLLING_MODULES = [
    COORDINATOR_MODULE,
    TASKS_COORDINATOR_MODULE,
    CONFIG_FLOW_MODULE,
    OPTIONS_FLOW_MODULE,
    SENSOR_PACKAGE,
]


def test_gate_1_covers_the_tasks_coordinator_module() -> None:
    """The tasks coordinator annotates the GET-only base client too.

    The tasks coordinator lives in its own module, so the gate 1 scan
    over ``coordinator.py`` alone would not see it. Scanning it here
    keeps "every coordinator types its client as the base client" true
    of every coordinator rather than of most of them.
    """
    from tests.helpers.ast_isolation import annotated_assignment_types

    assert TASKS_COORDINATOR_MODULE.is_file(), (
        "the tasks coordinator module must exist to be isolated"
    )
    assert annotated_assignment_types(TASKS_COORDINATOR_MODULE, "_client") == {
        BASE_CLIENT_NAME
    }, "the tasks coordinator must annotate self._client as the base client"


def test_gate_3_covers_the_us4_modules() -> None:
    """No US4 polling module reaches for a write-capable symbol.

    The existence assertions come first for the same reason as the gate
    above: a scan that passes because the file is absent proves nothing.
    """
    from tests.helpers.ast_isolation import scan_paths

    for module in (
        TASKS_COORDINATOR_MODULE,
        OPTIONS_FLOW_MODULE,
        TASKS_SENSOR_MODULE,
    ):
        assert module.is_file(), f"{module} must exist to be isolated"

    scanned = scan_paths(US4_POLLING_MODULES)
    covered = {path.as_posix() for path in scanned}
    assert TASKS_COORDINATOR_MODULE.as_posix() in covered
    assert OPTIONS_FLOW_MODULE.as_posix() in covered
    assert TASKS_SENSOR_MODULE.as_posix() in covered

    for path, facts in scanned.items():
        assert not facts.references("HospitableWriteClient"), path
        assert not facts.references("_post"), path
        assert not facts.imports_from("custom_components.hospitable.actions"), path
        assert not facts.imports_from(
            "custom_components.hospitable.api.write_client"
        ), path


# --- US5 extension of gates 1 to 3 (T146, FR-001) -----------------------
#
# These ADD to the gates above; nothing existing is relaxed. US5 adds a
# message-presence module and a message sensor module, and the calendar
# coordinator moved into its own module to keep ``coordinator.py`` within
# the file-size budget.
#
# That move is exactly why this block exists. Gate 1 scans
# ``coordinator.py`` for ``_client`` annotations and compares the result
# as a SET, so relocating a coordinator out of that file does not fail
# the gate — it silently stops covering it, and the gate keeps reporting
# green over code nobody is checking any more. A gate that quietly
# narrows is worse than one that breaks loudly.

MESSAGES_COORDINATOR_MODULE = INTEGRATION_ROOT / "coordinator_messages.py"
CALENDAR_COORDINATOR_MODULE = INTEGRATION_ROOT / "coordinator_calendar.py"
MESSAGES_SENSOR_MODULE = SENSOR_PACKAGE / "messages.py"
RATE_LIMIT_MODULE = INTEGRATION_ROOT / "rate_limit.py"

US5_POLLING_MODULES = [
    *US4_POLLING_MODULES,
    MESSAGES_COORDINATOR_MODULE,
    CALENDAR_COORDINATOR_MODULE,
    RATE_LIMIT_MODULE,
]


def test_gate_1_covers_the_relocated_and_new_coordinator_modules() -> None:
    """Every out-of-file coordinator still types the GET-only client.

    Both modules are asserted to exist first: an annotation scan over a
    missing file returns an empty set, and an empty set would sail past
    a subset check while proving nothing at all.
    """
    from tests.helpers.ast_isolation import annotated_assignment_types

    for module in (MESSAGES_COORDINATOR_MODULE, CALENDAR_COORDINATOR_MODULE):
        assert module.is_file(), f"{module} must exist to be isolated"
        assert annotated_assignment_types(module, "_client") == {BASE_CLIENT_NAME}, (
            f"{module} must annotate self._client as the base client"
        )


def test_gate_3_covers_the_us5_modules() -> None:
    """No US5 polling module reaches for a write-capable symbol."""
    from tests.helpers.ast_isolation import scan_paths

    for module in (
        MESSAGES_COORDINATOR_MODULE,
        CALENDAR_COORDINATOR_MODULE,
        MESSAGES_SENSOR_MODULE,
        RATE_LIMIT_MODULE,
    ):
        assert module.is_file(), f"{module} must exist to be isolated"

    scanned = scan_paths(US5_POLLING_MODULES)
    covered = {path.as_posix() for path in scanned}
    for module in (
        MESSAGES_COORDINATOR_MODULE,
        CALENDAR_COORDINATOR_MODULE,
        MESSAGES_SENSOR_MODULE,
        RATE_LIMIT_MODULE,
    ):
        assert module.as_posix() in covered, f"the scan did not reach {module}"

    for path, facts in scanned.items():
        assert not facts.references("HospitableWriteClient"), path
        assert not facts.references("_post"), path
        assert not facts.imports_from("custom_components.hospitable.actions"), path
        assert not facts.imports_from(
            "custom_components.hospitable.api.write_client"
        ), path


def test_the_message_poll_cannot_reach_the_send_helper() -> None:
    """The message poll names no send symbol at all (T146, FR-001).

    ``api/messages.py`` holds BOTH the read helper this module uses and
    ``async_send_message``. Gate 3 would not catch importing the wrong
    one: it is the same module, not the ``actions`` package, and it is
    reached through the GET-only client's typing rather than the write
    client's. So the send helper is named here explicitly.
    """
    from tests.helpers.ast_isolation import scan_paths

    scanned = scan_paths([MESSAGES_COORDINATOR_MODULE, MESSAGES_SENSOR_MODULE])
    assert len(scanned) == 2, "the scan did not reach both message modules"
    for path, facts in scanned.items():
        assert not facts.references("async_send_message"), path
        assert not facts.references("MessageAcceptance"), path
