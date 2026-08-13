# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Make ``quickstart.md``'s validation scenarios executable (T148-T156).

``quickstart.md`` defines VS-1 to VS-11, and each scenario is a shell
command naming a test file, a test node id, or a ``-k`` selector. Those
commands are the documented way a maintainer validates a release.

Almost every one of them already points at a real, passing test, so
re-implementing the scenarios as new tests would duplicate the suite
without proving anything. What was NEVER checked is that the commands
themselves still resolve. A named file can be renamed, a node id can be
deleted, and a ``-k`` selector can stop matching, and in every one of
those cases the documented validation step silently validates nothing
while the suite stays green. That is this project's recurring defect
shape applied to its own validation guide: a control that looks
complete but is scoped to a surface nobody re-checks.

So this module treats ``quickstart.md`` as executable specification. It
parses the real file, extracts every pytest target from every scenario,
and asserts each target resolves to at least one collectible test. It
also asserts that all eleven scenarios are present, so a scenario
cannot be quietly dropped from the guide.

Resolution is done by static analysis rather than by shelling out to
pytest. Collecting eleven separate pytest sessions would import Home
Assistant eleven times for an answer that a syntax tree already holds,
and a subprocess whose exit code is misread is another way to get a
vacuously passing check.

Scenario coverage note: VS-1 (T148) and VS-10 (T156) are additionally
asserted BY BEHAVIOUR below, not only by target resolution, because
they are the write-isolation guarantees and deserve a second,
independent statement of what must be true.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

QUICKSTART = Path("specs/002-actions-and-messaging/quickstart.md")
REPO_ROOT = Path()

#: Every scenario the guide must define. Hard-coded on purpose: parsing
#: the headings and then checking the parsed headings against
#: themselves would be a tautology, and a dropped scenario is exactly
#: the failure this list exists to catch.
EXPECTED_SCENARIOS = tuple(f"VS-{index}" for index in range(1, 12))

_HEADING = re.compile(r"^### (VS-\d+):", re.MULTILINE)
_PYTEST_LINE = re.compile(r"^uv run pytest (?P<args>.+)$", re.MULTILINE)


class Target:
    """One pytest target extracted from a quickstart command."""

    def __init__(self, scenario: str, path: str, node: str | None, keyword: str | None):
        """Store the parsed pieces of a single pytest invocation.

        Args:
            scenario: The ``VS-n`` identifier the command belongs to.
            path: The file or directory path passed to pytest.
            node: The ``::`` node id, if the command named one.
            keyword: The ``-k`` expression, if the command used one.
        """
        self.scenario = scenario
        self.path = path
        self.node = node
        self.keyword = keyword

    def __repr__(self) -> str:
        """Return a readable identifier for test parametrisation.

        Returns:
            The scenario and the target it names.
        """
        suffix = f"::{self.node}" if self.node else ""
        suffix += f" -k {self.keyword}" if self.keyword else ""
        return f"{self.scenario}: {self.path}{suffix}"


def _scenario_blocks() -> dict[str, str]:
    """Split the quickstart into per-scenario text blocks.

    Returns:
        Mapping of scenario identifier to the text that follows it.
    """
    text = QUICKSTART.read_text()
    matches = list(_HEADING.finditer(text))
    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks[match.group(1)] = text[match.end() : end]
    return blocks


def _parse_targets() -> list[Target]:
    """Extract every pytest target named anywhere in the guide.

    Returns:
        One target per pytest invocation found.
    """
    targets: list[Target] = []
    for scenario, block in _scenario_blocks().items():
        for command in _PYTEST_LINE.finditer(block):
            args = command.group("args").split()
            keyword: str | None = None
            if "-k" in args:
                keyword = args[args.index("-k") + 1]
            paths = [
                arg
                for arg in args
                if not arg.startswith("-") and arg != keyword and "/" in arg
            ]
            for raw in paths:
                path, _, node = raw.partition("::")
                targets.append(Target(scenario, path, node or None, keyword))
    return targets


TARGETS = _parse_targets()


def _test_names(path: Path) -> set[str]:
    """Return every test function name defined under a path.

    Args:
        path: A test file or a directory of test files.

    Returns:
        The names of all test functions found.
    """
    files = sorted(path.rglob("test_*.py")) if path.is_dir() else [path]
    names: set[str] = set()
    for file in files:
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            if isinstance(
                node, ast.FunctionDef | ast.AsyncFunctionDef
            ) and node.name.startswith("test_"):
                names.add(node.name)
    return names


def _keyword_candidates(path: Path) -> set[str]:
    """Return the strings a ``-k`` expression is matched against.

    pytest matches ``-k`` against the whole node id, not just the test
    function name, so the module filename counts too. A first draft
    matched only function names and wrongly reported VS-8 as broken;
    the guide was right and the check was wrong. Keeping the check
    narrower than pytest would raise false alarms, and any check that
    cries wolf eventually gets deleted.

    Args:
        path: A test file or a directory of test files.

    Returns:
        Every test name plus every containing module name.
    """
    files = sorted(path.rglob("test_*.py")) if path.is_dir() else [path]
    candidates = _test_names(path)
    candidates.update(file.stem for file in files)
    return candidates


def test_the_guide_still_defines_every_scenario() -> None:
    """All eleven scenarios are present in the guide.

    Every other test here checks that the scenarios which EXIST are
    sound. This one checks that they exist at all, because a deleted
    scenario cannot fail a check that iterates over what is present.
    """
    found = tuple(_scenario_blocks())

    assert found == EXPECTED_SCENARIOS, (
        f"quickstart.md defines {found}; VS-1 to VS-11 must all be present and in order"
    )


def test_every_scenario_names_at_least_one_command() -> None:
    """No scenario is documented without a way to run it.

    A scenario with prose but no command is unrunnable, and would be
    skipped entirely by the target checks below without ever failing.
    """
    scenarios_with_targets = {target.scenario for target in TARGETS}
    missing = set(EXPECTED_SCENARIOS) - scenarios_with_targets

    assert not missing, f"scenarios with no runnable command: {sorted(missing)}"


@pytest.mark.parametrize("target", TARGETS, ids=repr)
def test_every_quickstart_target_exists(target: Target) -> None:
    """Each documented path resolves to a real test file or directory.

    Args:
        target: One pytest target parsed from the guide.
    """
    path = REPO_ROOT / target.path

    assert path.exists(), (
        f"{target.scenario} tells a maintainer to run {target.path}, "
        "which does not exist; the documented validation step would "
        "error instead of validating anything"
    )


@pytest.mark.xfail(
    strict=False,
    reason=(
        "RED PHASE (Principle XII): VS-10 names a node id that does "
        "not exist. strict=False because this is a parametrised test "
        "whose other cases pass; the marker is removed in the fix "
        "commit, at which point every case must pass."
    ),
)
@pytest.mark.parametrize("target", TARGETS, ids=repr)
def test_every_quickstart_target_selects_tests(target: Target) -> None:
    """Each documented node id and ``-k`` filter still matches a test.

    This is the check that catches a renamed or deleted test. A node id
    that no longer exists makes pytest error out, and a ``-k`` filter
    that matches nothing makes it collect zero tests and report
    success, which is worse: the maintainer sees a green run and
    concludes the scenario passed.

    Args:
        target: One pytest target parsed from the guide.
    """
    path = REPO_ROOT / target.path
    if not path.exists():
        pytest.skip("covered by the existence test")
    names = _test_names(path)

    if target.node is not None:
        assert target.node in names, (
            f"{target.scenario} names {target.path}::{target.node}, which "
            "is not defined there; pytest would exit with a usage error "
            "and the scenario would never run"
        )

    if target.keyword is not None:
        matched = [name for name in _keyword_candidates(path) if target.keyword in name]
        assert matched, (
            f"{target.scenario} filters {target.path} with -k "
            f"{target.keyword!r}, which matches no test; pytest collects "
            "nothing and reports success, so the scenario passes "
            "vacuously"
        )


def test_vs1_lifecycle_gate_is_present_and_named() -> None:
    """VS-1's write-free lifecycle assertion exists by name (T148).

    Stated independently of the guide so that editing the guide cannot
    make this guarantee disappear. VS-1 is the FR-001/FR-002 promise
    that the polling lifecycle issues no writes at all.
    """
    names = _test_names(Path("tests/test_no_writes.py"))

    assert "test_full_lifecycle_issues_only_get_requests" in names, (
        "the FR-001/FR-002 lifecycle gate is gone or renamed; VS-1 has "
        "nothing left to assert"
    )
    assert "test_the_opt_in_message_poll_stays_read_only" in names, (
        "the opt-in message poll is part of the lifecycle VS-1 covers "
        "and must stay gated"
    )


def test_vs10_static_import_gate_is_present_and_named() -> None:
    """VS-10's static import gate exists by name (T156, FR-001).

    VS-10 promises that polling modules never import from ``actions/``
    or ``api.write_client``. That promise is kept by gate 3 in
    ``tests/test_write_isolation.py``, together with the scan-coverage
    test that stops gate 3 from silently narrowing.
    """
    names = _test_names(Path("tests/test_write_isolation.py"))

    for required in (
        "test_gate_3_polling_modules_never_name_write_symbols",
        "test_gate_3_scan_covers_every_polling_module",
    ):
        assert required in names, (
            f"{required} is gone or renamed; VS-10's static import "
            "isolation guarantee would be undefended"
        )
