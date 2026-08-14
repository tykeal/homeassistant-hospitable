# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Documentation must stay true (T164 to T167, T171).

Phase 9 is documentation work, and documentation is the part of a
project that rots without anything failing. Three specific rots are
guarded here, each because it actually happened or nearly did.

1. **The FR traceability table silently omitted five requirements.**
   T171 asks for every FR to be traceable. The audit found FR-011a,
   FR-046, FR-047, FR-047a and FR-048 absent from the table in
   ``tasks.md`` while present in ``spec.md``. Four of them were
   thoroughly tested and merely uncited; FR-011a was uncited AND
   unnamed by any task. Comparing the two documents by hand once fixes
   today; comparing them in a test fixes it permanently.

2. **The README described the integration as read-only.** That was
   true before spec 002 and became false the moment ``send_message``
   shipped. Nothing failed, because no test reads prose.

3. **Acceptance language.** A 202 from the send endpoint means
   ACCEPTED FOR DELIVERY. User-facing documentation that says a message
   was "sent" or "delivered" is a factual claim the integration cannot
   support, and the README is user-facing.

These are deliberately checks on FACTS that can be verified against the
source, not on wording. A test that pinned prose would be changed
every time the prose improved, and would then stop meaning anything.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
README = REPO_ROOT / "README.md"
SPEC = REPO_ROOT / "specs/002-actions-and-messaging/spec.md"
TASKS = REPO_ROOT / "specs/002-actions-and-messaging/tasks.md"
SPEC_003 = REPO_ROOT / "specs/003-property-discovery/spec.md"
TASKS_003 = REPO_ROOT / "specs/003-property-discovery/tasks.md"

USER_FACING_DOCS = (README,)

#: Words that would assert delivery. ``sent`` is matched as a whole
#: word so that "consent" and similar do not trip it.
DELIVERY_CLAIMS = ("delivered", "was sent", "has been sent")


def _fr_ids(text: str) -> set[str]:
    """Return every functional requirement id defined in a spec.

    Args:
        text: The spec document text.

    Returns:
        The set of ``FR-nnn`` identifiers defined with a bold heading.
    """
    return set(re.findall(r"\*\*(FR-\d+[a-z]?)\*\*:", text))


def _traced_fr_ids(text: str) -> set[str]:
    """Return every requirement id given a row in the traceability table.

    Args:
        text: The tasks document text.

    Returns:
        The set of identifiers appearing as a table row key.
    """
    return set(re.findall(r"^\| (FR-\d+[a-z]?) \|", text, re.MULTILINE))


@pytest.mark.parametrize(
    ("spec_path", "tasks_path"),
    [
        pytest.param(SPEC, TASKS, id="spec-002"),
        pytest.param(SPEC_003, TASKS_003, id="spec-003"),
    ],
)
def test_every_requirement_is_traceable(
    spec_path: Path,
    tasks_path: Path,
) -> None:
    """No FR in the spec is missing from the traceability table.

    This is the check that found the five omissions. It compares the
    two documents rather than trusting either, so adding a requirement
    without tracing it fails immediately instead of at the next audit.
    """
    defined = _fr_ids(spec_path.read_text())
    traced = _traced_fr_ids(tasks_path.read_text())

    assert defined, "no requirements were parsed from spec.md at all"
    untraced = sorted(defined - traced)
    assert not untraced, (
        f"{untraced} are specified but appear in no traceability row; a "
        "requirement nobody traced is a requirement nobody verified"
    )


@pytest.mark.parametrize(
    ("spec_path", "tasks_path"),
    [
        pytest.param(SPEC, TASKS, id="spec-002"),
        pytest.param(SPEC_003, TASKS_003, id="spec-003"),
    ],
)
def test_the_table_invents_no_requirements(
    spec_path: Path,
    tasks_path: Path,
) -> None:
    """The table traces only requirements that really exist.

    The reverse direction matters too: a row for a deleted requirement
    makes the table look more complete than it is.
    """
    defined = _fr_ids(spec_path.read_text())
    traced = _traced_fr_ids(tasks_path.read_text())

    invented = sorted(traced - defined)
    assert not invented, f"{invented} are traced but are not defined in spec.md"


def test_the_readme_no_longer_calls_the_integration_read_only() -> None:
    """The README does not describe the integration as read-only.

    It said so until spec 002 shipped a write service, and no test
    noticed. The claim is checked against the actual service table
    rather than against wording alone.
    """
    from custom_components.hospitable.actions import SERVICE_DEFINITIONS

    writes = [
        definition.name
        for definition in SERVICE_DEFINITIONS
        if definition.name == "send_message"
    ]
    assert writes, (
        "send_message is not registered; if the write service really "
        "was removed, this test and the README both need revisiting"
    )

    readme = README.read_text()

    # A single exact phrase is a denylist of one: the README could
    # reword the same false claim and still pass. Reject a family of
    # phrasings, AND require the write capability to be stated
    # positively, so silence is a failure rather than a pass.
    for phrasing in (
        "read-only Home Assistant custom integration",
        "read-only integration",
        "integration is read-only",
        "this integration is read only",
        "does not write",
        "makes no write",
        "never writes to Hospitable",
    ):
        assert phrasing.lower() not in readme.lower(), (
            f"the README says {phrasing!r} while {writes} is registered "
            "and issues a POST"
        )

    for name in writes:
        assert f"`hospitable.{name}`" in readme, (
            f"{name} issues the only non-GET request and must be named in the README"
        )
    assert "POST" in readme, (
        "the README never mentions that a POST is issued at all; "
        "dropping the read-only claim is not the same as disclosing "
        "the write"
    )


def test_the_readme_has_no_inline_code_span_broken_by_a_wrap() -> None:
    """No backtick span in the README straddles a line break.

    Wrapping inside a code span both renders wrongly and silently
    misstates whatever it names, as it did for a rate-limit header
    here. Markdownlint does not catch it.
    """
    readme = README.read_text()

    offenders = [
        line
        for line in readme.splitlines()
        if line.count("`") % 2 and not line.lstrip().startswith("```")
    ]
    assert not offenders, (
        f"unbalanced backticks, so a code span wraps across lines: {offenders}"
    )


@pytest.mark.parametrize("path", USER_FACING_DOCS, ids=lambda path: path.name)
def test_user_facing_docs_never_claim_delivery(path: Path) -> None:
    """No user-facing document claims a message was delivered.

    A 202 means accepted for asynchronous delivery. Claiming delivery
    would be an assertion the integration has no evidence for, and
    documentation is exactly where a user would believe it.

    Args:
        path: A user-facing document.
    """
    text = path.read_text().lower()

    found = [claim for claim in DELIVERY_CLAIMS if claim in text]
    assert not found, (
        f"{path.name} contains {found}; a 202 is an acceptance for "
        "asynchronous delivery and never a confirmation of receipt"
    )


@pytest.mark.parametrize("path", USER_FACING_DOCS, ids=lambda path: path.name)
def test_user_facing_docs_state_the_acceptance_distinction(path: Path) -> None:
    """Saying nothing is not enough; the distinction must be drawn.

    The test above is negative and silence satisfies it. A user told
    nothing will assume the message was delivered, so the document has
    to say what a 202 does and does not mean.

    Args:
        path: A user-facing document.
    """
    text = path.read_text().lower()

    assert "accept" in text, f"{path.name} never explains what acceptance means"
    assert "202" in text, (
        f"{path.name} never names the 202 status a user will see "
        "referenced in the response"
    )


def test_the_documented_rate_limits_match_the_code() -> None:
    """The README's rate-limit numbers are the code's numbers.

    Documented limits drift from enforced limits silently, and a user
    plans their automations around the documented ones.
    """
    from custom_components.hospitable import rate_limit

    readme = README.read_text()

    assert f"{rate_limit.RESERVATION_LIMIT} requests per " in readme, (
        "the README does not state the enforced per-reservation limit"
    )
    assert f"{rate_limit.RESERVATION_WINDOW_SECONDS} seconds" in readme
    assert f"{rate_limit.TOKEN_LIMIT} requests per " in readme, (
        "the README does not state the enforced per-token limit"
    )


def test_the_readme_separates_the_two_evidence_tiers() -> None:
    """The two rate limits are not presented as equally certain.

    2 per 60 seconds per reservation is CONFIRMED-BY-TEST; 50 per 5
    minutes per token is DOCUMENTED-ONLY and has never been observed.
    Flattening them into one confident statement is a regression this
    project has explicitly decided to prevent.
    """
    # Scoped to the rate-limit TABLE, not to the document. A first
    # draft searched the whole README and a mutation relabelling the
    # per-token row as CONFIRMED-BY-TEST still passed, because the
    # Evidence tiers section further down also contains both strings.
    # Same scope error this project keeps hitting, caught by mutation.
    readme = README.read_text()
    rows = [
        line
        for line in readme.splitlines()
        if line.startswith("|")
        and ("Per **reservation**" in line or "Per **token**" in line)
    ]
    assert len(rows) == 2, f"expected two rate-limit rows, found {len(rows)}"
    by_scope = {
        ("reservation" if "reservation" in row else "token"): row for row in rows
    }

    assert "CONFIRMED-BY-TEST" in by_scope["reservation"], (
        "the per-reservation limit was proven by a live read-only probe "
        "and should be labelled as confirmed"
    )
    assert "DOCUMENTED-ONLY" in by_scope["token"], (
        "the per-token limit has never been observed; labelling it as "
        "confirmed would flatten two different evidence tiers"
    )
    assert "CONFIRMED-BY-TEST" not in by_scope["token"]
    assert "never been observed" in readme, (
        "the README states a tier label but never says plainly that the "
        "per-token limit has not been observed"
    )


def test_the_open_questions_are_recorded_as_open() -> None:
    """OQ-001 and OQ-007 are documented as genuinely open.

    OQ-005 was closed after a real end-to-end message send on
    2026-08-13/14. The two remaining questions cannot be resolved
    without further live testing. Recording them as open is the
    honest outcome; quietly omitting them would read as resolution.

    This control also verifies that OQ-005 is recorded as closed,
    so the evidence of its resolution cannot silently vanish.
    """
    readme = README.read_text()

    # Extract the Open questions section so cross-section mentions
    # of an OQ identifier cannot mask a closure declaration here.
    oq_match = re.search(
        r"^## Open questions\n(.+?)(?=\n## |\Z)",
        readme,
        re.MULTILINE | re.DOTALL,
    )
    assert oq_match, "the README has no '## Open questions' section"
    oq_section = oq_match.group(1)

    # --- still-open questions: must appear AND not be declared closed --
    open_questions = ("OQ-001", "OQ-007")
    for question in open_questions:
        assert question in oq_section, (
            f"{question} is not recorded in the Open questions section"
        )
        # Within this section every line mentioning the identifier
        # must NOT be a closure declaration. A single "is closed"
        # line would mean the question was resolved.
        section_mentions = [
            line for line in oq_section.splitlines() if question in line
        ]
        assert not any("is closed" in ln.lower() for ln in section_mentions), (
            f"{question} is declared closed in the Open questions "
            "section; if it really was resolved, update this test"
        )

    assert "cannot be closed" in readme.lower() or "unresolvable" in readme.lower(), (
        "the README lists the open questions but never says they "
        "cannot be closed without further live testing"
    )

    # --- OQ-005: must be recorded as closed so evidence is preserved --
    assert "OQ-005" in oq_section, (
        "OQ-005 is no longer recorded in the Open questions section; "
        "its closure evidence has silently vanished"
    )
    oq005_lines = [line for line in oq_section.splitlines() if "OQ-005" in line]
    assert any("is closed" in line.lower() for line in oq005_lines), (
        "OQ-005 appears in the README but is not marked closed; "
        "the manual send on 2026-08-13/14 confirmed it"
    )


def test_every_registered_service_is_documented() -> None:
    """Every registered service has a dedicated section in README.md.

    Enumerated from the registration table rather than from a list
    written here, so a service added later is documented or fails.
    """
    from custom_components.hospitable.actions import SERVICE_DEFINITIONS

    readme = README.read_text()

    # A dedicated HEADING, not a passing mention. get_property_info is
    # referenced inside send_message's field notes, so a bare substring
    # check passed even with its own section renamed away.
    for definition in SERVICE_DEFINITIONS:
        assert f"### `hospitable.{definition.name}`" in readme, (
            f"{definition.name} is registered but has no section of its "
            "own in README.md; a passing mention elsewhere is not "
            "documentation of the service"
        )
