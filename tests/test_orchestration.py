"""Deterministic, offline integration tests for the orchestration layer.
Reuses Agent 1's fixture-based fetch injection (tests/conftest.py) and
Agent 2's monkeypatched population-fetcher pattern (tests/test_stall_
detector.py) so the full Agent 1 -> 2 -> 3 chain runs with no network
access and a fully controlled outcome.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from permit_stall_finder.agents.developer_explainer import explain_assessment
from permit_stall_finder.agents.journey_reconstructor import reconstruct_journey
from permit_stall_finder.agents.stall_detector import assess_stalls
from permit_stall_finder.ingestion import cohort_populations as pop
from permit_stall_finder.orchestration.pipeline import (
    AnalysisOutcome,
    PipelineExecutionError,
    PipelineStage,
    classify_outcome,
    run_pipeline,
    verify_provenance_chain,
)
from permit_stall_finder.schema.journey import MatchStatus
from permit_stall_finder.schema.stall_detection import (
    BenchmarkSemantics,
    CohortConfidence,
    CohortDefinition,
    CohortSource,
    DelayStallDetection,
    IntervalState,
    Severity,
    StallAssessment,
    StallCategory,
)

from .conftest import load_fixture_fetchers

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)
_DEFAULT_POPULATION = [float(i) for i in range(50)]


@pytest.fixture(autouse=True)
def _default_populations(monkeypatch):
    """Same default-population fixture as test_stall_detector.py, so any
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


# --- end-to-end, using real fixture permits ---------------------------


def test_pipeline_end_to_end_stall_detected(conn, monkeypatch):
    """corrections_then_reinspection (21010-10000-05865) has 82 real
    inspection events including genuine correction cycles -- with the
    default population, this should clear WATCH on at least one category."""
    fetch_permit, fetch_inspections = load_fixture_fetchers("corrections_then_reinspection")

    result = run_pipeline(
        conn, "21010-10000-05865",
        fetch_permit_row=fetch_permit, fetch_inspection_rows=fetch_inspections,
        now=NOW,
    )

    assert result.permit_number == "21010-10000-05865"
    assert result.outcome == AnalysisOutcome.STALL_DETECTED
    assert result.stall_assessment.detections
    assert len(result.developer_explanations.explanations) == len(result.stall_assessment.detections)
    verify_provenance_chain(result)  # doesn't raise


def test_pipeline_end_to_end_unissued_no_material_stall(conn, monkeypatch):
    """unissued (21030-20000-00256) has genuinely elapsed ~1800+ real days,
    which would trivially rank at the 100th percentile of the shared
    small default population -- override with a wide-range population
    (comparable in spirit to the real, heavily-skewed active-peer cohort
    found during Agent 2 validation) so this test exercises a real 'below
    threshold' outcome rather than a population-scale artifact."""
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

    assert result.stall_assessment.detections == []
    assert result.stall_assessment.coverage_gaps == []
    assert result.outcome == AnalysisOutcome.NO_MATERIAL_STALL_DETECTED
    assert result.developer_explanations.explanations == []


def test_pipeline_end_to_end_permit_not_found_is_insufficient_evidence_not_clean(conn):
    """A not-found permit must never read as 'no problem found.'"""

    def fetch_permit_row(permit_number):
        return None

    def fetch_inspection_rows(permit_number):
        return []

    result = run_pipeline(
        conn, "99999-99999-99999",
        fetch_permit_row=fetch_permit_row, fetch_inspection_rows=fetch_inspection_rows,
        now=NOW,
    )

    assert result.journey.match_status == MatchStatus.PERMIT_NOT_FOUND
    assert result.stall_assessment.detections == []
    assert result.coverage_gaps  # non-empty
    assert result.outcome == AnalysisOutcome.INSUFFICIENT_EVIDENCE
    assert result.outcome != AnalysisOutcome.NO_MATERIAL_STALL_DETECTED


def test_pipeline_end_to_end_issued_no_inspections_administrative_exempt(conn):
    """issued_no_inspections (18010-20001-05038) is the real administrative
    correction permit -- Agent 2's exemption layer should keep it a clean
    (or at worst insufficient-evidence) read, never a fabricated stall."""
    fetch_permit, fetch_inspections = load_fixture_fetchers("issued_no_inspections")

    result = run_pipeline(
        conn, "18010-20001-05038",
        fetch_permit_row=fetch_permit, fetch_inspection_rows=fetch_inspections,
        now=NOW,
    )

    assert result.stall_assessment.detections == []
    assert result.outcome != AnalysisOutcome.STALL_DETECTED


# --- outcome classification: pure unit tests ---------------------------


def _cohort():
    return CohortDefinition(
        dimensions={}, specificity_level=1, source=CohortSource.SOURCE_EVENT_LOG,
        benchmark_semantics=BenchmarkSemantics.COMPLETED_INTERVAL, n=50, confidence=CohortConfidence.FULL,
        median_days_or_count=5.0, p75_days_or_count=10.0, p90_days_or_count=20.0, p95_days_or_count=30.0,
        computed_at=NOW,
    )


def _detection():
    return DelayStallDetection(
        permit_number="X", category=StallCategory.INTER_INSPECTION_GAP, stage_label="A -> B", generated_at=NOW,
        elapsed_days=50, as_of=NOW, interval_state=IntervalState.COMPLETED,
        status_persistence_confirmed_by_repeated_observation=False,
        cohort=_cohort(), percentile_rank=90.0, excess_days_vs_median=45.0, severity=Severity.ELEVATED,
        evidence=[], cannot_infer=[], caveats=[], based_on_match_status=MatchStatus.ISSUED_WITH_INSPECTIONS,
    )


def _assessment(detections=None, coverage_gaps=None):
    return StallAssessment(
        permit_number="X", generated_at=NOW, source_permit_journey_generated_at=NOW,
        detections=detections or [], coverage_gaps=coverage_gaps or [], summary_note="",
    )


def test_classify_outcome_no_material_stall():
    assert classify_outcome(_assessment()) == AnalysisOutcome.NO_MATERIAL_STALL_DETECTED


def test_classify_outcome_insufficient_evidence():
    assert classify_outcome(_assessment(coverage_gaps=["some gap"])) == AnalysisOutcome.INSUFFICIENT_EVIDENCE


def test_classify_outcome_stall_detected():
    assert classify_outcome(_assessment(detections=[_detection()])) == AnalysisOutcome.STALL_DETECTED


def test_classify_outcome_stall_detected_takes_priority_over_coverage_gaps():
    """A real, common shape in our data: one confirmed detection plus
    coverage gaps for other, separately-unassessable categories. The
    confirmed stall must not be diluted by the coexisting gap."""
    result = classify_outcome(_assessment(detections=[_detection()], coverage_gaps=["unrelated gap"]))
    assert result == AnalysisOutcome.STALL_DETECTED


# --- provenance chain integrity -----------------------------------------


def test_verify_provenance_chain_passes_for_a_real_pipeline_run(conn):
    fetch_permit, fetch_inspections = load_fixture_fetchers("finaled_completed")
    result = run_pipeline(
        conn, "20010-20000-02739",
        fetch_permit_row=fetch_permit, fetch_inspection_rows=fetch_inspections, now=NOW,
    )
    verify_provenance_chain(result)  # must not raise


def test_verify_provenance_chain_detects_a_substituted_stall_assessment(conn):
    fetch_permit, fetch_inspections = load_fixture_fetchers("unissued")
    result = run_pipeline(
        conn, "21030-20000-00256",
        fetch_permit_row=fetch_permit, fetch_inspection_rows=fetch_inspections, now=NOW,
    )
    tampered_assessment = replace(
        result.stall_assessment,
        source_permit_journey_generated_at=datetime(2000, 1, 1, tzinfo=timezone.utc),
    )
    tampered_result = replace(result, stall_assessment=tampered_assessment)
    with pytest.raises(AssertionError):
        verify_provenance_chain(tampered_result)


# --- error handling -----------------------------------------------------


def test_pipeline_execution_error_wraps_journey_stage_failure(conn):
    def fetch_permit_row(permit_number):
        raise ConnectionError("simulated network failure")

    with pytest.raises(PipelineExecutionError) as exc_info:
        run_pipeline(conn, "SOME-PERMIT", fetch_permit_row=fetch_permit_row, now=NOW)

    assert exc_info.value.permit_number == "SOME-PERMIT"
    assert exc_info.value.stage == PipelineStage.JOURNEY_RECONSTRUCTION
    assert isinstance(exc_info.value.original, ConnectionError)


# --- identity checks: orchestrated vs standalone agent output -----------


def test_orchestrated_stall_assessment_matches_standalone_call(conn):
    """Same journey in, same StallAssessment out -- proves the orchestrator
    doesn't transform Agent 2's output in transit."""
    fetch_permit, fetch_inspections = load_fixture_fetchers("corrections_then_reinspection")

    orchestrated = run_pipeline(
        conn, "21010-10000-05865",
        fetch_permit_row=fetch_permit, fetch_inspection_rows=fetch_inspections, now=NOW,
    )

    conn2_journey = reconstruct_journey(
        conn, "21010-10000-05865",
        fetch_permit_row=fetch_permit, fetch_inspection_rows=fetch_inspections, observed_at=NOW,
    )
    standalone = assess_stalls(conn2_journey, now=NOW)

    assert orchestrated.stall_assessment == standalone


def test_orchestrated_explanations_match_standalone_call(conn):
    fetch_permit, fetch_inspections = load_fixture_fetchers("corrections_then_reinspection")

    orchestrated = run_pipeline(
        conn, "21010-10000-05865",
        fetch_permit_row=fetch_permit, fetch_inspection_rows=fetch_inspections, now=NOW,
    )
    standalone = explain_assessment(orchestrated.stall_assessment, now=NOW)

    assert orchestrated.developer_explanations == standalone
