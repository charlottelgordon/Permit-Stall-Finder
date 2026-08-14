"""End-to-end Agent 3 tests: explain_assessment / explain_detection,
including the NO_ENTRY_AVAILABLE path and passthrough of Agent 2's
caveats/cannot_infer/coverage_gaps (AGENT3_DESIGN.md §8)."""

from __future__ import annotations

from datetime import datetime, timezone

from permit_stall_finder.agents.developer_explainer import explain_assessment, explain_detection
from permit_stall_finder.knowledge_base.loader import default_knowledge_base
from permit_stall_finder.schema.developer_explanation import GroundingStatus
from permit_stall_finder.schema.journey import MatchStatus
from permit_stall_finder.schema.stall_detection import (
    BenchmarkSemantics,
    CohortConfidence,
    CohortDefinition,
    CohortSource,
    DelayStallDetection,
    FrictionStallDetection,
    IntervalState,
    LifecycleStage,
    Severity,
    StallAssessment,
    StallCategory,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def _cohort():
    return CohortDefinition(
        dimensions={}, specificity_level=1, source=CohortSource.SOURCE_EVENT_LOG,
        benchmark_semantics=BenchmarkSemantics.COMPLETED_INTERVAL, n=50, confidence=CohortConfidence.FULL,
        median_days_or_count=5.0, p75_days_or_count=10.0, p90_days_or_count=20.0, p95_days_or_count=30.0,
        computed_at=NOW,
    )


def _delay(category, stage_label="X", caveats=None, cannot_infer=None):
    return DelayStallDetection(
        permit_number="TEST-1", category=category, stage_label=stage_label, generated_at=NOW,
        elapsed_days=84, as_of=NOW, interval_state=IntervalState.COMPLETED,
        status_persistence_confirmed_by_repeated_observation=False,
        cohort=_cohort(), percentile_rank=97.0, excess_days_vs_median=79.0, severity=Severity.SEVERE,
        evidence=[], cannot_infer=cannot_infer or ["cannot infer cause"], caveats=caveats or ["a caveat"],
        based_on_match_status=MatchStatus.ISSUED_WITH_INSPECTIONS,
    )


def _friction(category, caveats=None, cannot_infer=None):
    return FrictionStallDetection(
        permit_number="TEST-1", category=category, generated_at=NOW,
        observed_count=5, meets_minimum_count=True, minimum_count_required=2,
        lifecycle_stage=LifecycleStage.COMPLETED, total_inspection_opportunities=62,
        observed_lifecycle_days=200, correction_rate=0.08, meets_minimum_exposure=True,
        cohort=_cohort(), percentile_rank=76.3, excess_count_vs_median=4.0, severity=Severity.WATCH,
        evidence=[], cannot_infer=cannot_infer or ["cannot infer cause"], caveats=caveats or ["a caveat"],
        based_on_match_status=MatchStatus.ISSUED_WITH_INSPECTIONS,
    )


def test_grounded_detection_produces_grounded_explanation():
    kb = default_knowledge_base()
    d = _delay(StallCategory.INTER_INSPECTION_GAP)
    explanation = explain_detection(d, kb, now=NOW)

    assert explanation.grounding_status == GroundingStatus.GROUNDED
    assert explanation.knowledge_base_entry_id == "inter_inspection_gap.generic"
    assert explanation.developer_actionable_steps
    assert explanation.city_dependent_steps
    assert explanation.kb_entry_version == "0.2.0"


def test_no_entry_available_case_repeated_cancellations():
    """The category with no KB entry by design -- must produce
    NO_ENTRY_AVAILABLE with the fixed fallback, not invented guidance."""
    kb = default_knowledge_base()
    d = _friction(StallCategory.REPEATED_CANCELLATIONS)
    explanation = explain_detection(d, kb, now=NOW)

    assert explanation.grounding_status == GroundingStatus.NO_ENTRY_AVAILABLE
    assert explanation.knowledge_base_entry_id is None
    assert explanation.developer_actionable_steps == []
    assert explanation.city_dependent_steps == []
    assert "No approved knowledge-base entry exists" in explanation.what_this_usually_means
    # section 1 facts are still present even when section 2 has no grounding
    assert "5 cancelled-related outcome(s)" in explanation.what_the_data_shows


def test_no_entry_available_case_repeated_not_ready():
    kb = default_knowledge_base()
    d = _friction(StallCategory.REPEATED_NOT_READY_OUTCOMES)
    explanation = explain_detection(d, kb, now=NOW)
    assert explanation.grounding_status == GroundingStatus.NO_ENTRY_AVAILABLE


def test_caveats_and_cannot_infer_pass_through_to_limitations():
    kb = default_knowledge_base()
    d = _delay(StallCategory.INTER_INSPECTION_GAP, caveats=["custom caveat X"], cannot_infer=["custom cannot-infer Y"])
    explanation = explain_detection(d, kb, now=NOW)
    assert "custom caveat X" in explanation.limitations
    assert "custom cannot-infer Y" in explanation.limitations


def test_disclaimer_always_present_and_correct():
    kb = default_knowledge_base()
    for d in (_delay(StallCategory.INTER_INSPECTION_GAP), _friction(StallCategory.REPEATED_CANCELLATIONS)):
        explanation = explain_detection(d, kb, now=NOW)
        assert "informational only" in explanation.disclaimer
        assert "LADBS" in explanation.disclaimer


def test_explain_assessment_produces_one_explanation_per_detection():
    kb = default_knowledge_base()
    assessment = StallAssessment(
        permit_number="TEST-1", generated_at=NOW, source_permit_journey_generated_at=NOW,
        detections=[
            _delay(StallCategory.INTER_INSPECTION_GAP),
            _friction(StallCategory.REPEATED_CORRECTIONS),
            _friction(StallCategory.REPEATED_CANCELLATIONS),
        ],
        coverage_gaps=["some coverage gap message"],
        summary_note="note",
    )
    result = explain_assessment(assessment, kb, now=NOW)

    assert len(result.explanations) == 3
    assert result.coverage_gaps == ["some coverage gap message"]  # passed through unchanged
    assert result.permit_number == "TEST-1"


def test_explain_assessment_empty_detections_still_passes_through_coverage_gaps():
    kb = default_knowledge_base()
    assessment = StallAssessment(
        permit_number="TEST-1", generated_at=NOW, source_permit_journey_generated_at=NOW,
        detections=[], coverage_gaps=["gap A", "gap B"], summary_note="note",
    )
    result = explain_assessment(assessment, kb, now=NOW)
    assert result.explanations == []
    assert result.coverage_gaps == ["gap A", "gap B"]


def test_never_recomputes_severity_or_percentile_rank():
    """Agent 3 must carry these through verbatim, never recalculate."""
    kb = default_knowledge_base()
    d = _delay(StallCategory.INTER_INSPECTION_GAP)
    explanation = explain_detection(d, kb, now=NOW)
    assert explanation.source_detection_severity == d.severity
    assert explanation.source_percentile_rank == d.percentile_rank


def test_developer_explanation_has_no_forecast_field():
    """The remaining-duration forecast (analysis/forecast.py) is
    deliberately NOT routed through DeveloperExplanation at all -- unlike
    severity/percentile_rank (which Agent 3 carries forward as
    traceability-only fields), the UI reads remaining_duration_forecast
    straight off the original DelayStallDetection, the same way it already
    reads elapsed_days/percentile_rank for the metrics row. This is a
    structural guarantee against Agent 3 ever duplicating or
    recomputing an Agent-2-owned number in a second place: there is
    simply no field here for that to happen to."""
    from permit_stall_finder.schema.developer_explanation import DeveloperExplanation

    assert "remaining_duration_forecast" not in DeveloperExplanation.__dataclass_fields__


def test_explain_detection_does_not_touch_source_forecast():
    """Agent 3 must not mutate or otherwise interfere with Agent 2's
    forecast -- it doesn't even look at it, since DelayStallDetection is
    a frozen dataclass and explain_detection() never reconstructs one."""
    kb = default_knowledge_base()
    d = _delay(StallCategory.NO_INSPECTION_SINCE_ISSUANCE)
    original_forecast = d.remaining_duration_forecast
    explain_detection(d, kb, now=NOW)
    assert d.remaining_duration_forecast is original_forecast
