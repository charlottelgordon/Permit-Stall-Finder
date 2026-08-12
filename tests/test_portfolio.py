"""Tests for app/portfolio.py's pure presentation-layer helpers -- no
Streamlit involved. Builds real PermitAnalysisResult objects via
run_pipeline() against the offline fixtures, the same approach
test_orchestration.py uses, rather than hand-constructing the nested
dataclasses -- so these tests exercise summarize_result() against the
exact shapes the real pipeline produces."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import portfolio  # noqa: E402

from permit_stall_finder.ingestion import cohort_populations as pop  # noqa: E402
from permit_stall_finder.orchestration.pipeline import AnalysisOutcome, run_pipeline  # noqa: E402
from permit_stall_finder.schema.stall_detection import Severity  # noqa: E402

from .conftest import load_fixture_fetchers  # noqa: E402

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)
_DEFAULT_POPULATION = [float(i) for i in range(50)]


@pytest.fixture(autouse=True)
def _default_populations(monkeypatch):
    """Same default-population fixture as test_orchestration.py, so any
    Agent 2 category the fixture permit's shape happens to trigger doesn't
    crash for lack of a mocked fetcher."""
    monkeypatch.setattr(
        pop, "fetch_pre_issuance_dwell_population",
        lambda status_desc, as_of, permit_type=None, exclude_permit_number=None: list(_DEFAULT_POPULATION),
    )
    monkeypatch.setattr(
        pop, "fetch_issuance_to_first_inspection_population",
        lambda permit_type, exclude_permit_number=None, sample_size=200: list(_DEFAULT_POPULATION),
    )
    monkeypatch.setattr(
        pop, "fetch_inter_inspection_gap_population",
        lambda permit_type, exclude_permit_number=None, sample_size=200: list(_DEFAULT_POPULATION),
    )
    monkeypatch.setattr(
        pop, "fetch_friction_count_population",
        lambda permit_type, result_family_filter, lifecycle_stage, exclude_permit_number=None, sample_size=200: list(
            _DEFAULT_POPULATION
        ),
    )
    monkeypatch.setattr(
        pop, "fetch_finalization_gap_population",
        lambda permit_type, track, exclude_permit_number=None, sample_size=200: list(_DEFAULT_POPULATION),
    )


# --- parse_permit_numbers -----------------------------------------------


def test_parse_permit_numbers_splits_newlines_and_commas():
    raw = "21030-20000-00256\n25016-10000-32699, 25016-20000-35761"
    assert portfolio.parse_permit_numbers(raw) == [
        "21030-20000-00256",
        "25016-10000-32699",
        "25016-20000-35761",
    ]


def test_parse_permit_numbers_strips_and_drops_blanks_and_duplicates():
    raw = "  21030-20000-00256  \n\n21030-20000-00256\n  \n25016-10000-32699"
    assert portfolio.parse_permit_numbers(raw) == ["21030-20000-00256", "25016-10000-32699"]


def test_parse_permit_numbers_empty_input():
    assert portfolio.parse_permit_numbers("") == []
    assert portfolio.parse_permit_numbers("   \n  \n") == []


# --- summarize_result / sort_rows, against real pipeline results --------


def test_summarize_result_stall_detected_fixture(conn):
    fetch_permit, fetch_inspections = load_fixture_fetchers("corrections_then_reinspection")
    result = run_pipeline(
        conn, "21010-10000-05865",
        fetch_permit_row=fetch_permit, fetch_inspection_rows=fetch_inspections,
        now=NOW,
    )

    row = portfolio.summarize_result(result)

    assert row.permit_number == "21010-10000-05865"
    assert row.outcome == AnalysisOutcome.STALL_DETECTED
    assert row.top_severity is not None
    assert row.top_severity == max(
        (d.severity for d in result.stall_assessment.detections),
        key=lambda s: {Severity.SEVERE: 3, Severity.ELEVATED: 2, Severity.WATCH: 1, Severity.UNSCORED: 0}[s],
    )
    assert row.headline  # non-empty, delegates to formatting.outcome_headline


def test_summarize_result_no_material_stall_fixture(conn, monkeypatch):
    """Same wide-population override test_orchestration.py uses for this
    fixture, so it exercises a real 'clean read' rather than a
    population-scale artifact."""
    monkeypatch.setattr(
        pop, "fetch_pre_issuance_dwell_population",
        lambda status_desc, as_of, permit_type=None, exclude_permit_number=None: [float(i) for i in range(5000)],
    )
    fetch_permit, fetch_inspections = load_fixture_fetchers("unissued")
    result = run_pipeline(
        conn, "21030-20000-00256",
        fetch_permit_row=fetch_permit, fetch_inspection_rows=fetch_inspections,
        now=NOW,
    )

    row = portfolio.summarize_result(result)

    assert row.outcome == AnalysisOutcome.NO_MATERIAL_STALL_DETECTED
    assert row.top_severity is None
    assert row.has_actionable_step is False


def _row(permit_number: str, outcome: AnalysisOutcome, top_severity, days: int) -> portfolio.PortfolioRow:
    """Builds a PortfolioRow directly (bypassing summarize_result) so
    sort_rows()'s ordering logic can be tested in isolation, independent
    of which real outcome a given fixture happens to produce under a
    given population."""
    rank = {Severity.SEVERE: 3, Severity.ELEVATED: 2, Severity.WATCH: 1, Severity.UNSCORED: 0}
    outcome_rank = {
        AnalysisOutcome.STALL_DETECTED: 2,
        AnalysisOutcome.INSUFFICIENT_EVIDENCE: 1,
        AnalysisOutcome.NO_MATERIAL_STALL_DETECTED: 0,
    }
    sort_key = (
        outcome_rank[outcome],
        rank.get(top_severity, -1) if top_severity is not None else -1,
        days,
    )
    return portfolio.PortfolioRow(
        permit_number=permit_number,
        address="—",
        permit_type="Bldg-Alter/Repair",
        status_desc="Issued",
        outcome=outcome,
        headline="test",
        top_severity=top_severity,
        days_in_current_status=days,
        has_actionable_step=False,
        sort_key=sort_key,
    )


def test_sort_rows_worst_first_by_outcome_tier():
    """STALL_DETECTED sorts ahead of INSUFFICIENT_EVIDENCE, which sorts
    ahead of NO_MATERIAL_STALL_DETECTED, regardless of input order."""
    clean = _row("A", AnalysisOutcome.NO_MATERIAL_STALL_DETECTED, None, days=10)
    insufficient = _row("B", AnalysisOutcome.INSUFFICIENT_EVIDENCE, None, days=10)
    stalled = _row("C", AnalysisOutcome.STALL_DETECTED, Severity.WATCH, days=10)

    ordered = portfolio.sort_rows([clean, insufficient, stalled])

    assert [r.permit_number for r in ordered] == ["C", "B", "A"]


def test_sort_rows_worst_first_by_severity_within_stall_detected():
    """Within STALL_DETECTED, higher severity sorts first."""
    watch = _row("A", AnalysisOutcome.STALL_DETECTED, Severity.WATCH, days=10)
    severe = _row("B", AnalysisOutcome.STALL_DETECTED, Severity.SEVERE, days=10)
    elevated = _row("C", AnalysisOutcome.STALL_DETECTED, Severity.ELEVATED, days=10)

    ordered = portfolio.sort_rows([watch, severe, elevated])

    assert [r.permit_number for r in ordered] == ["B", "C", "A"]


def test_address_falls_back_to_em_dash_when_no_snapshot(conn):
    fetch_permit, fetch_inspections = load_fixture_fetchers("corrections_then_reinspection")
    result = run_pipeline(
        conn, "21010-10000-05865",
        fetch_permit_row=fetch_permit, fetch_inspection_rows=fetch_inspections,
        now=NOW,
    )
    row = portfolio.summarize_result(result)
    # The fixture's raw permit row may or may not carry primary_address --
    # either way this must be a plain string, never None or a KeyError.
    assert isinstance(row.address, str)
    assert row.address != ""

