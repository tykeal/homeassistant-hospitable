# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Make the D-01 gates impossible to narrow silently (T161, FR-001).

**The hazard this file closes.** Gates 1 and 3 in
``tests/test_write_isolation.py`` are driven off hand-maintained lists
of module paths (``US4_POLLING_MODULES``, ``US5_POLLING_MODULES``).
That is a real weakness and it has already fired once: when US5
extracted ``coordinator_calendar.py`` out of ``coordinator.py``, gate 1
compared a SET of modules that did not yet name the new file. The gate
stayed GREEN while covering strictly less than it had the day before.
It was caught by hand, and only because someone went looking.

A list-driven gate can only ever assert something about the files
somebody remembered to list. It cannot notice the file they forgot,
and the file they forgot is the one that needs the gate.

So these tests enumerate the polling surface from the FILESYSTEM and
assert the hand-maintained lists have not fallen behind it. Adding or
relocating a coordinator now fails here until its module is listed.
Nothing in the existing gates is relaxed, renamed or skipped; this
only adds a floor beneath them.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_write_isolation import (
    BASE_CLIENT_NAME,
    INTEGRATION_ROOT,
    US5_POLLING_MODULES,
)

# The write path, which is the one part of the integration that is
# SUPPOSED to hold a write-capable client. Everything else is polling.
ACTIONS_PACKAGE = INTEGRATION_ROOT / "actions"
WRITE_CLIENT_MODULE = INTEGRATION_ROOT / "api" / "write_client.py"
# A genuinely MIXED module: it holds the message READ helper the poll
# uses and the message SEND helper the service uses. The write path is
# therefore not separable by directory alone, which is worth stating
# plainly rather than discovering later. The risk that the poll reaches
# the send helper is covered head-on by
# ``test_the_message_poll_cannot_reach_the_send_helper`` (T146).
MESSAGES_API_MODULE = INTEGRATION_ROOT / "api" / "messages.py"

# The composition root. It is the ONE module that must legitimately
# reach both halves of the integration: it sets up the polling
# coordinators and registers the services. Excluding it is therefore
# correct, but an unexamined exclusion is how coverage gets lost, so
# the exemption is itself asserted to be unique below.
COMPOSITION_ROOT = INTEGRATION_ROOT / "__init__.py"


def _is_write_path(path: Path) -> bool:
    """Return whether a module is part of the write path.

    Args:
        path: A module path inside the integration.

    Returns:
        True when the module is the write client, the mixed messages
        helper, or lives in the actions package.
    """
    return (
        path in {WRITE_CLIENT_MODULE, MESSAGES_API_MODULE}
        or ACTIONS_PACKAGE in path.parents
    )


def discovered_polling_modules() -> set[Path]:
    """Return every integration module outside the write path.

    Returns:
        Every ``.py`` file under the integration root except the write
        client and the actions package, discovered by walking the tree
        rather than by consulting a list.
    """
    return {
        path
        for path in INTEGRATION_ROOT.rglob("*.py")
        if not _is_write_path(path) and "__pycache__" not in path.parts
    }


def test_the_discovery_walk_actually_finds_the_integration() -> None:
    """The walk reaches real modules, so the tests below are not vacuous.

    A discovery walk that matched nothing would make every assertion
    driven off it pass trivially. That is the same class of silent
    narrowing this file exists to prevent, so the walk itself is
    checked before anything is concluded from it.
    """
    discovered = discovered_polling_modules()

    assert len(discovered) >= 20, (
        f"the walk found only {len(discovered)} modules, which is far "
        "too few for this integration; the root or the filter is wrong"
    )
    assert INTEGRATION_ROOT / "coordinator.py" in discovered
    assert WRITE_CLIENT_MODULE not in discovered, "the write client is not polling code"
    assert not any(ACTIONS_PACKAGE in path.parents for path in discovered), (
        "the actions package is the write path and must not be swept in"
    )
    list_props = ACTIONS_PACKAGE / "list_properties.py"
    assert list_props not in discovered, (
        "list_properties.py is an action module and must not appear "
        "in the polling surface; it reads from coordinator cache only"
    )


def test_every_client_holding_module_is_listed_by_gate_1() -> None:
    """No module may hold a client without gate 1 knowing about it.

    THIS is the assertion that makes a future silent narrowing
    impossible. Gate 1 asserts that every module IT KNOWS ABOUT
    annotates ``self._client`` as the GET-only base client. It cannot
    speak for a module nobody added to its list, and when US5 split
    ``coordinator_calendar.py`` out, that was exactly the gap.

    Discovering client holders from the tree and requiring the list to
    cover all of them turns "someone forgot" from a silent loss of
    coverage into a test failure.
    """
    from tests.helpers.ast_isolation import annotated_assignment_types

    holders = {
        path
        for path in discovered_polling_modules()
        if annotated_assignment_types(path, "_client")
    }
    assert holders, (
        "no module was found holding a _client at all, so this test "
        "would pass no matter how badly gate 1 had narrowed"
    )

    listed = set(US5_POLLING_MODULES)
    unlisted = {
        path
        for path in holders
        if path not in listed and not any(parent in listed for parent in path.parents)
    }
    assert not unlisted, (
        f"these modules hold a client but no D-01 gate list names them: "
        f"{sorted(str(path) for path in unlisted)}. Add them to "
        "US5_POLLING_MODULES in tests/test_write_isolation.py, or gate 1 "
        "will keep passing while covering less than it claims."
    )


def test_every_discovered_client_is_the_get_only_client() -> None:
    """Every client holder anywhere types it as the GET-only client.

    Stated over the DISCOVERED set rather than a list, so it holds for
    modules that do not exist yet.
    """
    from tests.helpers.ast_isolation import annotated_assignment_types

    checked = 0
    for path in sorted(discovered_polling_modules()):
        annotations = annotated_assignment_types(path, "_client")
        if not annotations:
            continue
        checked += 1
        assert annotations == {BASE_CLIENT_NAME}, (
            f"{path} annotates self._client as {sorted(annotations)}; "
            f"polling code must hold only {BASE_CLIENT_NAME}, which has "
            "no _post at all"
        )
    assert checked >= 4, f"only {checked} client holders were checked"


def test_no_discovered_polling_module_reaches_the_write_path() -> None:
    """Gate 3, restated over the whole tree instead of a list.

    Gate 3 in ``test_write_isolation.py`` scans the modules it lists.
    This scans everything that is not the write path, so a new polling
    module importing ``actions`` or the write client fails immediately
    rather than whenever someone remembers to list it.
    """
    from tests.helpers.ast_isolation import scan_paths

    modules = discovered_polling_modules() - {COMPOSITION_ROOT}
    scanned = scan_paths(sorted(modules))
    assert len(scanned) >= 20, f"the scan reached only {len(scanned)} modules"

    for path, facts in scanned.items():
        assert not facts.references("HospitableWriteClient"), path
        assert not facts.references("_post"), path
        assert not facts.imports_from("custom_components.hospitable.actions"), path
        assert not facts.imports_from(
            "custom_components.hospitable.api.write_client"
        ), path


def test_the_integration_root_holds_exactly_one_write_client() -> None:
    """Only ``api/write_client.py`` may define a write-capable client.

    A second write client elsewhere would satisfy every gate above --
    they all name ``HospitableWriteClient`` specifically -- while
    reintroducing precisely the risk D-01 exists to remove.
    """
    definitions = {
        path
        for path in INTEGRATION_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
        and "    async def _post(" in path.read_text()
    }

    assert definitions == {WRITE_CLIENT_MODULE}, (
        f"expected exactly one module to define _post, found "
        f"{sorted(str(path) for path in definitions)}"
    )


def test_only_the_composition_root_is_exempt_from_gate_3() -> None:
    """Exactly one module may import the actions package.

    ``__init__.py`` is excluded from the scan above because it sets up
    the coordinators AND registers the services, so it must see both
    halves. That exemption is only safe while it is unique: a second
    module reaching into ``actions`` would be polling code touching the
    write path, which is the whole thing D-01 forbids.

    Asserting uniqueness here means the exemption cannot quietly become
    a loophole that new code slips through.
    """
    from tests.helpers.ast_isolation import scan_paths

    scanned = scan_paths(sorted(discovered_polling_modules()))
    importers = {
        path
        for path, facts in scanned.items()
        if facts.imports_from("custom_components.hospitable.actions")
    }

    assert importers == {COMPOSITION_ROOT}, (
        f"expected only the composition root to import the actions "
        f"package, found {sorted(str(path) for path in importers)}"
    )


def test_the_write_surface_is_exactly_two_consumers() -> None:
    """Pin WHICH modules may CONSUME write-capable symbols at all.

    Every gate above asks whether polling code reaches the write path.
    None of them asks how big the write path is. That matters, because
    the way this integration would lose write isolation is not a
    coordinator importing ``HospitableWriteClient`` -- three separate
    gates would catch that -- but a fourth module quietly acquiring the
    ability to POST and then being treated as a read helper, exactly as
    ``api/messages.py`` already legitimately is.

    Enumerated from the tree and asserted for EQUALITY, so growing the
    write surface is a decision someone has to make deliberately here.
    """
    from tests.helpers.ast_isolation import scan_paths

    everything = [
        path
        for path in sorted(INTEGRATION_ROOT.rglob("*.py"))
        if "__pycache__" not in path.parts
    ]
    scanned = scan_paths(everything)
    writers = {
        path
        for path, facts in scanned.items()
        if facts.references("HospitableWriteClient")
        or facts.imports_from("custom_components.hospitable.api.write_client")
    }

    # ``write_client.py`` DEFINES the class rather than referencing it,
    # so it is not a consumer and does not appear here. That it is the
    # sole definer is asserted by
    # ``test_the_integration_root_holds_exactly_one_write_client``.
    assert writers == {
        MESSAGES_API_MODULE,
        ACTIONS_PACKAGE / "send_message.py",
    }, (
        f"the write surface changed: {sorted(str(path) for path in writers)}. "
        "Adding a module here is a D-01 decision, not an implementation "
        "detail; update this assertion only with that decision made."
    )
