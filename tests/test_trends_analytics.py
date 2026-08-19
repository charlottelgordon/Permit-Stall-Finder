"""Tests for analytics/trends.py -- the pure aggregation the trends
dashboard artifact is built from. Synthetic PermitJourney/StallAssessment
fixtures (same hand-built-dataclass approach as test_stall_detector.py),
no network, no Streamlit.
"""

from __future__ import annotations

from datetime import datetime, timezone

from permit_stall_finder.analytics.trends import (
    TrendsArtifact,
    YearTypeBucket,
    aggregate_bucket,
    from_json,
    to_json,
)
from permit_stall_finder.schema.journey import DerivedMetrics, MatchStatus, PermitJourney
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

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def _cohort() -> CohortDefinition:
    return CohortDefinition(
        dimensions={"permit_type": "Bldg-Alter/Repair"},
        specificity_level=1,
        source=CohortSource.CROSS_SECTIONAL_CURRENT_SNAPSHOT,
        benchmark_semantics=BenchmarkSemantics.COMPLETED_INTERVAL,
        n=50,
        confidence=CohortConfidence.FULL,
        median_days_or_count=10.0,
        p75_days_or_count=20.0,
        p90_days_or_count=30.0,
        p95_days_or_count=40.0,
        computed_at=NOW,
    )


def _detection(category: StallCategory, severity: Severity) -> DelayStallDetection:
    return DelayStallDetection(
        permit_number="TEST-1",
        category=category,
        stage_label="Issued",
        generated_at=NOW,
        elapsed_days=30,
        as_of=NOW,
        interval_state=IntervalState.ONGOING,
        status_persistence_confirmed_by_repeated_observation=False,
        cohort=_cohort(),
        percentile_rank=90.0,
        excess_days_vs_median=20.0,
        severity=severity,
        evidence=[],
        cannot_infer=[],
        caveats=[],
        based_on_match_status=MatchStatus.ISSUED_WITH_INSPECTIONS,
    )


def _journey(
    days_submitted_to_issuance=None,
    days_issuance_to_first_inspection=None,
    days_between_inspections=None,
) -> PermitJourney:
    return PermitJourney(
        permit_number="TEST-1",
        generated_at=NOW,
        source_provenance={},
        match_status=MatchStatus.ISSUED_WITH_INSPECTIONS,
        latest_snapshot=None,
        prior_snapshots=[],
        inspection_events=[],
        derived=DerivedMetrics(
            days_submitted_to_current_status=None,
            days_submitted_to_issuance=days_submitted_to_issuance,
            days_issuance_to_first_inspection=days_issuance_to_first_inspection,
            days_between_inspections=days_between_inspections or [],
            total_observed_elapsed_days=None,
        ),
    )


def _assessment(detections: list[DelayStallDetection]) -> StallAssessment:
    return StallAssessment(
        permit_number="TEST-1",
        generated_at=NOW,
        source_permit_journey_generated_at=NOW,
        detections=detections,
        coverage_gaps=[],
        summary_note="",
    )


# --- aggregate_bucket ----------------------------------------------------


def test_aggregate_bucket_computes_medians_from_derived_metrics():
    pairs = [
        (_journey(days_submitted_to_issuance=10.0), _assessment([])),
        (_journey(days_submitted_to_issuance=20.0), _assessment([])),
        (_journey(days_submitted_to_issuance=30.0), _assessment([])),
    ]
    bucket = aggregate_bucket(2024, "Bldg-Alter/Repair", n_sampled=3, journeys_and_assessments=pairs)

    assert bucket.median_days_submitted_to_issuance == 20.0
    assert bucket.n_sampled == 3
    assert bucket.n_analyzed == 3


def test_aggregate_bucket_ignores_none_derived_values():
    pairs = [
        (_journey(days_submitted_to_issuance=None), _assessment([])),
        (_journey(days_submitted_to_issuance=10.0), _assessment([])),
    ]
    bucket = aggregate_bucket(2024, "Bldg-New", n_sampled=2, journeys_and_assessments=pairs)

    assert bucket.median_days_submitted_to_issuance == 10.0


def test_aggregate_bucket_flattens_inter_inspection_gaps_across_permits():
    pairs = [
        (_journey(days_between_inspections=[5.0, 15.0]), _assessment([])),
        (_journey(days_between_inspections=[25.0]), _assessment([])),
    ]
    bucket = aggregate_bucket(2024, "Bldg-New", n_sampled=2, journeys_and_assessments=pairs)

    # median of [5, 15, 25]
    assert bucket.median_inter_inspection_gap_days == 15.0


def test_aggregate_bucket_tallies_categories_and_severities():
    pairs = [
        (
            _journey(),
            _assessment(
                [
                    _detection(StallCategory.INTER_INSPECTION_GAP, Severity.SEVERE),
                    _detection(StallCategory.REPEATED_CORRECTIONS, Severity.WATCH),
                ]
            ),
        ),
        (_journey(), _assessment([_detection(StallCategory.INTER_INSPECTION_GAP, Severity.ELEVATED)])),
    ]
    bucket = aggregate_bucket(2024, "Bldg-New", n_sampled=2, journeys_and_assessments=pairs)

    assert bucket.stall_category_counts == {
        StallCategory.INTER_INSPECTION_GAP.value: 2,
        StallCategory.REPEATED_CORRECTIONS.value: 1,
    }
    assert bucket.severity_counts == {
        Severity.SEVERE.value: 1,
        Severity.WATCH.value: 1,
        Severity.ELEVATED.value: 1,
    }


def test_aggregate_bucket_empty_input_produces_no_medians():
    bucket = aggregate_bucket(2024, "Bldg-New", n_sampled=5, journeys_and_assessments=[])

    assert bucket.n_analyzed == 0
    assert bucket.median_days_submitted_to_issuance is None
    assert bucket.stall_category_counts == {}


# --- to_json / from_json round trip --------------------------------------


def test_to_json_from_json_round_trip():
    bucket = YearTypeBucket(
        year=2024,
        permit_type="Bldg-New",
        n_sampled=10,
        n_analyzed=9,
        median_days_submitted_to_issuance=42.0,
        median_days_issuance_to_first_inspection=None,
        median_inter_inspection_gap_days=15.5,
        stall_category_counts={"inter_inspection_gap": 3},
        severity_counts={"severe": 1, "watch": 2},
    )
    artifact = TrendsArtifact(
        generated_at=datetime(2026, 8, 19, 3, 0, tzinfo=timezone.utc),
        start_year=2023,
        end_year=2024,
        sample_size_per_bucket=10,
        cohort_sample_size=50,
        permit_types=["Bldg-New"],
        buckets=[bucket],
    )

    round_tripped = from_json(to_json(artifact))

    assert round_tripped == artifact
