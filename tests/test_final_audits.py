# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Localisation and acceptance-language audits (T159, T160).

Two audits over the user-facing surface, both driven off what the
integration ACTUALLY presents rather than off a list somebody typed.
A list-driven audit can only check the strings its author remembered,
which is the same weakness the D-01 gates had.

**T159, localisation.** Every option the flow presents must carry a
label in BOTH `strings.json` and `translations/en.json`. The option
KEYS come from the flow's own schema, so adding an option without
localising it fails here.

**T160, acceptance language.** A 202 from the send endpoint means
ACCEPTED FOR DELIVERY, not DELIVERED. Delivery is asynchronous and
this integration never observes it, so any user-facing text saying a
message was sent or delivered would be an assertion about something
nobody checked.

The docstring half of T160 is scoped to the ``actions`` package, which
is what T160 names, and the scope is stated here rather than left
implicit. A tree-wide regex produces only false positives: eight
matches across ``api/`` and ``diagnostics.py``, every one of them
either an HTTP REQUEST being sent ("the request could not be sent",
"the dates are always sent") or a negation ("nothing here claims the
message was sent or delivered"). Exempting those individually would
build exactly the denylist-shaped control this project keeps getting
burned by, so the audit is scoped to the surface where a delivery
claim would actually mislead a user instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.helpers.language import find_delivery_claims

INTEGRATION_ROOT = Path("custom_components/hospitable")
STRINGS = INTEGRATION_ROOT / "strings.json"
EN = INTEGRATION_ROOT / "translations" / "en.json"
LOCALISATION_FILES = (STRINGS, EN)

# The options spec 002 introduces. Each is non-obvious enough that a
# LABEL alone leaves the installer guessing -- a bounded numeric whose
# bound is discoverable only by tripping it, or a privacy or cost
# trade-off. These must carry a DESCRIPTION too (FR-007).
SPEC_002_OPTIONS = (
    "guest_contact_details",
    "awaiting_host_reply",
    "task_interval_minutes",
    "task_window_days",
)

ACTIONS_PACKAGE = INTEGRATION_ROOT / "actions"


def _init_step(path: Path) -> dict[str, Any]:
    """Return the options flow's init step from a localisation file.

    Args:
        path: The localisation file to read.

    Returns:
        The ``options.step.init`` mapping.
    """
    loaded = json.loads(path.read_text())
    step: dict[str, Any] = loaded["options"]["step"]["init"]
    return step


def _presented_option_keys() -> set[str]:
    """Return every option key the options flow actually presents.

    Read off the flow's own schema rather than a literal list, so an
    option added without localisation fails this audit instead of
    slipping through because nobody updated a constant.

    Returns:
        The option keys in the flow schema.
    """
    from custom_components.hospitable.options_flow import (
        DEFAULT_OPTIONS,
        HospitableOptionsFlow,
    )

    flow = HospitableOptionsFlow.__new__(HospitableOptionsFlow)
    schema = HospitableOptionsFlow._build_schema(
        flow,
        available={"prop-example-001": "Example Beach House"},
        options=dict(DEFAULT_OPTIONS),
        selection=["prop-example-001"],
        overrides={},
    )
    return {str(marker) for marker in schema.schema}


# Per-property timezone overrides are generated one field per property
# at runtime, so their keys cannot exist in a static translation file.
# Home Assistant labels them from the property name instead. The
# exemption is asserted to cover ONLY this family below, rather than
# being a silent filter that future dynamic keys could hide behind.
DYNAMIC_KEY_PREFIX = "timezone_override_"


def _static_option_keys() -> set[str]:
    """Return the presented option keys that a translation file can hold.

    Returns:
        Every presented key except the per-property dynamic family.
    """
    return {
        key
        for key in _presented_option_keys()
        if not key.startswith(DYNAMIC_KEY_PREFIX)
    }


def test_only_the_timezone_family_is_dynamically_keyed() -> None:
    """The dynamic-key exemption covers exactly one known family.

    An unexamined filter is how an audit quietly stops covering things.
    Asserting which keys it removes keeps the exemption honest.
    """
    presented = _presented_option_keys()
    excluded = presented - _static_option_keys()

    assert excluded == {f"{DYNAMIC_KEY_PREFIX}prop-example-001"}, (
        f"the dynamic-key exemption removed {sorted(excluded)}; every "
        "other option must be statically localised"
    )


# --- T159: localisation parity -----------------------------------------


def test_the_schema_probe_finds_the_real_options() -> None:
    """The flow probe returns real keys, so the audits below can bite.

    An empty schema would make every parity assertion vacuous.
    """
    presented = _presented_option_keys()

    assert len(presented) >= 8, f"the flow presented only {sorted(presented)}"
    for expected in SPEC_002_OPTIONS:
        assert expected in presented, (
            f"{expected} is not presented by the options flow at all"
        )


@pytest.mark.parametrize("path", LOCALISATION_FILES, ids=lambda path: path.name)
def test_every_presented_option_has_a_label(path: Path) -> None:
    """Every option the flow presents is labelled in both files (FR-007).

    Both files, because Home Assistant reads `translations/en.json` at
    runtime while `strings.json` is the source of truth for
    translators. A key present in only one is localised for exactly one
    audience.
    """
    labelled = set(_init_step(path).get("data", {}))
    missing = _static_option_keys() - labelled

    assert not missing, (
        f"{path} labels no string for {sorted(missing)}; the installer "
        "would see a raw key name in the options dialog"
    )


def test_the_two_localisation_files_agree() -> None:
    """`strings.json` and `translations/en.json` carry the same keys.

    Drift between them is invisible at runtime -- Home Assistant reads
    only the translation -- so it surfaces as a translator seeing a
    string that no longer exists, or missing one that does.
    """
    strings = _init_step(STRINGS)
    english = _init_step(EN)

    assert set(strings.get("data", {})) == set(english.get("data", {}))
    assert set(strings.get("data_description", {})) == set(
        english.get("data_description", {})
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RED PHASE (Principle XII): task_interval_minutes ships with a "
        "label and no description while enforcing a 5-minute floor. "
        "Marker removed in the fix commit."
    ),
)
@pytest.mark.parametrize("path", LOCALISATION_FILES, ids=lambda path: path.name)
def test_every_spec_002_option_is_described(path: Path) -> None:
    """The spec 002 options carry descriptions, not just labels (FR-007).

    Scoped to the options spec 002 introduces rather than to all ten,
    deliberately. Widening it to the spec 001 options would be scope
    creep dressed up as an audit, and would fail on text this feature
    never touched.

    ``task_interval_minutes`` is the reason this test exists. It had a
    label and no description while enforcing a five-minute floor that
    an installer could only discover by entering four and reading the
    resulting error.
    """
    described = set(_init_step(path).get("data_description", {}))
    missing = [option for option in SPEC_002_OPTIONS if option not in described]

    assert not missing, (
        f"{path} describes {sorted(missing)} with a label only. Each of "
        "these carries a cost, a privacy trade-off, or a bound that is "
        "not visible from its name."
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RED PHASE (Principle XII): task_interval_minutes ships with a "
        "label and no description while enforcing a 5-minute floor. "
        "Marker removed in the fix commit."
    ),
)
def test_the_task_interval_description_states_its_floor() -> None:
    """The interval description names the bound it silently enforces.

    A description that omitted the floor would satisfy the parity test
    above while leaving the installer exactly as stuck.
    """
    from custom_components.hospitable.const import MIN_TASK_INTERVAL

    for path in LOCALISATION_FILES:
        description = _init_step(path)["data_description"]["task_interval_minutes"]
        assert str(MIN_TASK_INTERVAL) in description, (
            f"{path} does not state the {MIN_TASK_INTERVAL}-minute minimum, "
            "which is otherwise discoverable only by tripping the error"
        )


# --- T160: a 202 is acceptance, not delivery ---------------------------


def _iter_strings(payload: Any) -> list[str]:
    """Return every string anywhere inside a JSON payload.

    Args:
        payload: Any decoded JSON value.

    Returns:
        Every string at any depth, keys included.
    """
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            found.append(str(key))
            found.extend(_iter_strings(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(_iter_strings(item))
    elif isinstance(payload, str):
        found.append(payload)
    return found


@pytest.mark.parametrize(
    "path",
    (STRINGS, EN, INTEGRATION_ROOT / "services.yaml"),
    ids=lambda path: path.name,
)
def test_no_user_facing_file_claims_delivery(path: Path) -> None:
    """No shipped user-facing string says sent or delivered (FR-045).

    Swept over the whole file rather than over named keys, so a claim
    added to a key nobody thought to check still fails.
    """
    text = path.read_text()
    if path.suffix == ".json":
        candidates = _iter_strings(json.loads(text))
    else:
        candidates = text.splitlines()

    claims = {
        candidate: find_delivery_claims(candidate)
        for candidate in candidates
        if find_delivery_claims(candidate)
    }
    assert not claims, (
        f"{path} claims delivery: {claims}. A 202 means ACCEPTED FOR "
        "DELIVERY; delivery itself is asynchronous and never observed."
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "RED PHASE (Principle XII): the send_message module docstring "
        "carries a NEGATED meta-statement using the words it forbids. "
        "Reworded in the fix commit rather than exempted, so this audit "
        "needs zero allowances."
    ),
)
def test_no_action_docstring_claims_delivery() -> None:
    """No docstring in the actions package claims delivery (FR-045).

    Scoped to ``actions`` on purpose; see this module's docstring for
    why a tree-wide sweep produces only false positives. Asserted with
    ZERO exemptions, which is the property that makes it meaningful: if
    this ever needs an allowance, the text should change instead.
    """
    import ast

    offenders: dict[str, list[str]] = {}
    modules = sorted(ACTIONS_PACKAGE.rglob("*.py"))
    assert len(modules) >= 5, f"only {len(modules)} action modules were scanned"

    for module in modules:
        tree = ast.parse(module.read_text())
        for node in ast.walk(tree):
            if not isinstance(
                node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
            ):
                continue
            docstring = ast.get_docstring(node)
            if docstring and find_delivery_claims(docstring):
                name = getattr(node, "name", "<module>")
                offenders[f"{module}:{name}"] = find_delivery_claims(docstring)

    assert not offenders, f"delivery claims in action docstrings: {offenders}"


def test_the_send_service_description_says_accepted() -> None:
    """The send service positively states acceptance, not just silence.

    Every test above is negative: they prove no text claims delivery.
    Silence would satisfy all of them. This asserts the distinction is
    actually COMMUNICATED, because a user who is told nothing will
    assume the message was sent.
    """
    # Read from strings.json, not services.yaml: services.yaml carries
    # only field STRUCTURE, while the user-visible names and
    # descriptions are localised. Auditing the wrong file would have
    # been a scope error of exactly the kind this project keeps hitting
    # -- checking a surface the user never reads.
    strings = json.loads(STRINGS.read_text())
    rendered = json.dumps(strings["services"]["send_message"]).lower()

    assert "accept" in rendered, (
        "the send service never uses the word 'accepted'; saying nothing "
        "leaves the user to assume delivery, which is the exact "
        "misunderstanding FR-045 exists to prevent"
    )
