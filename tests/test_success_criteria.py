# SPDX-FileCopyrightText: 2026 Andrew Grimberg <tykeal@bardicgrove.org>
# SPDX-License-Identifier: Apache-2.0
"""Success-criteria traceability, made executable (T163).

T163 asks for SC-001 to SC-009 to be verified against concrete
evidence, and forbids marking a criterion verified without naming the
test that verifies it. A prose table would satisfy the letter of that
and decay immediately: a renamed or deleted test leaves the table
asserting a verification that no longer happens, and nothing fails.

So the mapping lives here as data and is checked. Every criterion names
the test node ids that verify it, and each of those node ids must
resolve to a test that actually exists. The whole table is also
required to be complete, so a criterion cannot be dropped to make the
check pass.

TWO CRITERIA ARE ONLY PARTLY AUTOMATABLE, and they are recorded as such
rather than silently claimed:

* SC-001's "within 5 seconds" and SC-007's latency figure are NOT
  verified by any test and cannot be. The suite runs against ``respx``,
  which serves responses from memory, so any wall-clock bound measured
  there is a property of the mock. ``spec.md`` already says this. The
  BEHAVIOURAL halves of both criteria are automated and named below;
  the latency halves are listed separately as manual, and the split is
  asserted so neither half can quietly absorb the other.

Node ids are resolved statically. Running the referenced tests here
would re-run a large part of the suite inside itself; whether they pass
is the job of the suite, and whether they EXIST is the job of this
file.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

#: Criterion -> the test node ids that verify it. Node ids are
#: ``path::name``. Every entry was checked by reading the test body,
#: not by matching on names.
SC_EVIDENCE: dict[str, tuple[str, ...]] = {
    "SC-001": (
        # A send returns an acceptance, and the response says accepted
        # rather than sent, which is the substance of the criterion.
        "tests/actions/test_send_message.py::test_happy_path_reports_acceptance_not_delivery",
        "tests/actions/test_send_message.py::test_a_202_with_an_empty_body_is_not_an_error",
        "tests/actions/test_e2e_actions.py::test_a_202_is_reported_as_accepted_and_never_as_sent",
    ),
    "SC-002": (
        "tests/test_no_writes.py::test_full_lifecycle_issues_only_get_requests",
        "tests/test_no_writes.py::test_the_opt_in_message_poll_stays_read_only",
        "tests/test_write_isolation.py::test_gate_3_polling_modules_never_name_write_symbols",
        "tests/test_write_isolation.py::test_gate_3_scan_covers_every_polling_module",
        "tests/test_isolation_discovery.py::test_every_client_holding_module_is_listed_by_gate_1",
    ),
    "SC-003": (
        # Logs and the diagnostics DOWNLOAD, not just the redactor
        # function. The download half was unverifiable until the entry
        # point existed at all.
        "tests/test_entity_pii_allowlist.py::test_no_guest_or_message_value_reaches_a_log_record",
        "tests/test_entity_pii_allowlist.py::test_no_guest_or_message_value_reaches_diagnostics",
        "tests/test_diagnostics_platform.py::test_no_guest_value_or_token_survives_the_download",
        "tests/test_diagnostics_platform.py::test_the_download_shows_guest_fields_as_redacted",
    ),
    "SC-003a": (
        "tests/test_response_pii_allowlist.py::test_every_service_response_key_is_allowlisted",
        "tests/test_response_pii_allowlist.py::test_no_service_response_carries_a_forbidden_key",
        "tests/test_response_pii_allowlist.py::test_contact_keys_track_the_option_exactly",
        "tests/test_response_pii_allowlist.py::test_the_audited_call_set_covers_every_registered_service",
        "tests/test_response_pii_allowlist.py::test_the_send_response_is_allowlisted_too",
    ),
    "SC-004": (
        "tests/sensor/test_tasks.py::test_the_task_count_spans_every_page",
        "tests/sensor/test_tasks.py::test_the_task_count_breaks_down_by_progress",
    ),
    "SC-005": (
        "tests/actions/test_rate_limit.py::test_per_reservation_budget_is_two_per_sixty_seconds",
        "tests/actions/test_rate_limit.py::test_per_token_budget_is_fifty_per_three_hundred_seconds",
        "tests/actions/test_rate_limit.py::test_per_reservation_buckets_are_independent",
        "tests/actions/test_e2e_actions.py::test_two_entries_on_one_token_share_the_budget",
        "tests/actions/test_e2e_actions.py::test_the_budget_is_per_reservation_not_global",
        "tests/test_poll_throttling.py::test_a_throttled_poll_is_actually_attempted_and_refused",
        "tests/test_poll_throttling.py::test_the_poll_honours_retry_after_beyond_the_floor",
    ),
    "SC-006": (
        "tests/actions/test_disambiguation.py::test_single_entry_resolves_without_an_explicit_id",
        "tests/actions/test_disambiguation.py::test_two_entries_require_an_explicit_id",
    ),
    "SC-007": (
        "tests/actions/test_e2e_actions.py::test_a_read_only_service_produces_no_side_effect",
        "tests/actions/test_e2e_actions.py::test_a_read_only_service_does_not_refresh_a_coordinator",
    ),
    "SC-008": (
        "tests/sensor/test_tasks.py::test_the_maintenance_task_is_labelled_from_the_task_type_table",
    ),
    "SC-009": (
        "tests/sensor/test_reservation.py::test_guest_identity_attributes_are_exposed_by_default",
        "tests/sensor/test_reservation.py::test_a_null_guest_reports_no_identity_at_all",
        "tests/sensor/test_reservation.py::test_every_guest_attribute_is_unrecorded",
        "tests/test_entity_pii_allowlist.py::test_every_guest_attribute_is_excluded_from_the_recorder",
    ),
}

#: Criteria with a half that NO test verifies, and the reason. Listed
#: explicitly so the honest gap is part of the record rather than an
#: omission a reader has to notice.
MANUAL_ONLY: dict[str, str] = {
    "SC-001": (
        "the 'within 5 seconds' latency bound is manual; under respx "
        "the response is already in memory, so a timing assertion "
        "would measure the mock"
    ),
    "SC-007": (
        "the latency figure is manual for the same reason; only the "
        "no-side-effect half is automated"
    ),
}

ALL_CRITERIA = (*(f"SC-{index:03d}" for index in range(1, 10)), "SC-003a")


def _defined_tests(path: Path) -> set[str]:
    """Return every test function name defined in a file.

    Args:
        path: The test file to parse.

    Returns:
        The names of all test functions found.
    """
    tree = ast.parse(path.read_text())
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name.startswith("test_")
    }


def test_every_success_criterion_has_evidence() -> None:
    """No criterion is left without a named verifying test.

    The set is compared exactly rather than checked for membership, so
    neither a dropped criterion nor an invented one passes.
    """
    assert set(SC_EVIDENCE) == set(ALL_CRITERIA), (
        f"evidence is recorded for {sorted(SC_EVIDENCE)}, but the "
        f"criteria are {sorted(ALL_CRITERIA)}"
    )
    empty = [criterion for criterion, tests in SC_EVIDENCE.items() if not tests]
    assert not empty, f"criteria claimed as verified with no test named: {empty}"


@pytest.mark.parametrize(
    "node_id",
    sorted({node for nodes in SC_EVIDENCE.values() for node in nodes}),
)
def test_every_named_evidence_test_exists(node_id: str) -> None:
    """Each named node id resolves to a test that really exists.

    This is the check that stops the table from decaying into a claim
    about tests that were renamed or deleted.

    Args:
        node_id: A ``path::name`` node id from the evidence table.
    """
    raw_path, _, name = node_id.partition("::")
    path = Path(raw_path)

    assert path.exists(), f"{node_id} names a file that does not exist"
    assert name in _defined_tests(path), (
        f"{node_id} names a test that is not defined in {raw_path}; the "
        "criterion it verifies is no longer verified by anything"
    )


def test_the_manual_gaps_are_declared_not_hidden() -> None:
    """Partly-manual criteria are recorded, and still automated in part.

    A criterion listed as manual-only with no automated evidence would
    be an untested criterion wearing a disclaimer. Both entries here
    keep automated evidence for their behavioural half.
    """
    assert set(MANUAL_ONLY) <= set(SC_EVIDENCE), (
        "a criterion is declared partly manual but has no entry in the evidence table"
    )
    for criterion in MANUAL_ONLY:
        assert SC_EVIDENCE[criterion], (
            f"{criterion} is declared partly manual and has no automated "
            "evidence at all, which is a different and worse thing"
        )
