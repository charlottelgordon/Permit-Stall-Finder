"""Deterministic rendering tests for section 1 ("what the data shows"),
covering all categories, both benchmark_semantics values, and both
interval_states (AGENT3_DESIGN.md §4, §8)."""

from __future__ import annotations

from datetime import datetime, timezone

from permit_stall_finder.rendering.fact_renderer import _ordinal, render_what_the_data_shows
from permit_stall_finder.rendering.safeguards import (
    assert_no_blame_language,
    assert_no_known_total_duration_claim,
    assert_no_normal_duration_claim,
)
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
    StallCategory,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def _cohort(benchmark_semantics, source=CohortSource.SOURCE_EVENT_LOG, n=100):
    return CohortDefinition(
        dimensions={"a": "1"}, specificity_level=1, source=source,
        benchmark_semantics=benchmark_semantics, n=n, confidence=CohortConfidence.FULL,
        median_days_or_count=10.0, p75_days_or_count=20.0, p90_days_or_count=30.0, p95_days_or_count=40.0,
        computed_at=NOW,
    )


def _delay(category, stage_label="PC Approved", elapsed_days=261, benchmark_semantics=BenchmarkSemantics.ACTIVE_PEER_DWELL,
           interval_state=IntervalState.ONGOING, rank=90.0, severity=Severity.ELEVATED, persistence=False, n=100):
    return DelayStallDetection(
        permit_number="TEST-1", category=category, stage_label=stage_label, generated_at=NOW,
        elapsed_days=elapsed_days, as_of=NOW, interval_state=interval_state,
        status_persistence_confirmed_by_repeated_observation=persistence,
        cohort=_cohort(benchmark_semantics, n=n), percentile_rank=rank, excess_days_vs_median=elapsed_days - 10,
        severity=severity, evidence=[], cannot_infer=[], caveats=[],
        based_on_match_status=MatchStatus.ISSUED_WITH_INSPECTIONS,
    )


def _friction(category, observed_count=5, total=20, rate=0.25, rank=80.0, severity=Severity.WATCH):
    return FrictionStallDetection(
        permit_number="TEST-1", category=category, generated_at=NOW,
        observed_count=observed_count, meets_minimum_count=True, minimum_count_required=2,
        lifecycle_stage=LifecycleStage.ONGOING, total_inspection_opportunities=total,
        observed_lifecycle_days=200, correction_rate=rate, meets_minimum_exposure=True,
        cohort=_cohort(BenchmarkSemantics.COMPLETED_INTERVAL), percentile_rank=rank,
        excess_count_vs_median=observed_count - 1, severity=severity,
        evidence=[], cannot_infer=[], caveats=[], based_on_match_status=MatchStatus.ISSUED_WITH_INSPECTIONS,
    )


# --- one test per category, confirming the renderer doesn't crash and
# produces category-appropriate content ---


def test_pre_issuance_status_dwell_active_peer_dwell():
    d = _delay(StallCategory.PRE_ISSUANCE_STATUS_DWELL, stage_label="PC Approved", elapsed_days=261,
               benchmark_semantics=BenchmarkSemantics.ACTIVE_PEER_DWELL, rank=92.0)
    text = render_what_the_data_shows(d)
    assert "261 days have elapsed since the published 'PC Approved' status_date." in text
    assert "longer than 92% of currently observed comparable permits" in text
    assert "not closed" in text  # ONGOING
    assert_no_normal_duration_claim(text)


def test_issuance_to_first_inspection_gap_completed_interval():
    d = _delay(StallCategory.ISSUANCE_TO_FIRST_INSPECTION_GAP, elapsed_days=400,
               benchmark_semantics=BenchmarkSemantics.COMPLETED_INTERVAL,
               interval_state=IntervalState.COMPLETED, rank=91.0, n=85)
    text = render_what_the_data_shows(d)
    assert "400 days" in text and "issuance" in text
    assert "ranked at approximately the 91st percentile of 85 comparable completed intervals" in text
    assert "not closed" not in text  # COMPLETED, must not claim open-ended


def test_no_inspection_since_issuance_is_ongoing():
    d = _delay(StallCategory.NO_INSPECTION_SINCE_ISSUANCE, elapsed_days=620,
               benchmark_semantics=BenchmarkSemantics.COMPLETED_INTERVAL,
               interval_state=IntervalState.ONGOING, rank=91.0)
    text = render_what_the_data_shows(d)
    assert "620 days have elapsed since issuance with no inspection record found." in text
    assert "not closed" in text
    assert_no_known_total_duration_claim(text)


def test_inter_inspection_gap():
    d = _delay(StallCategory.INTER_INSPECTION_GAP, stage_label="A -> B", elapsed_days=84,
               benchmark_semantics=BenchmarkSemantics.COMPLETED_INTERVAL,
               interval_state=IntervalState.COMPLETED, rank=97.0, n=566)
    text = render_what_the_data_shows(d)
    assert "84 days" in text
    assert "ranked at approximately the 97th percentile of 566 comparable completed intervals" in text


def test_inactivity_since_last_inspection_is_ongoing():
    d = _delay(StallCategory.INACTIVITY_SINCE_LAST_INSPECTION, stage_label="Final", elapsed_days=500,
               benchmark_semantics=BenchmarkSemantics.COMPLETED_INTERVAL, interval_state=IntervalState.ONGOING)
    text = render_what_the_data_shows(d)
    assert "no further inspection recorded since" in text
    assert "not closed" in text


def test_finalization_gap_cofo_track():
    d = _delay(StallCategory.FINALIZATION_GAP, stage_label="cofo_track", elapsed_days=150,
               benchmark_semantics=BenchmarkSemantics.COMPLETED_INTERVAL, interval_state=IntervalState.COMPLETED)
    text = render_what_the_data_shows(d)
    assert "150 days" in text and "terminal outcome" in text


def test_friction_repeated_corrections():
    d = _friction(StallCategory.REPEATED_CORRECTIONS, observed_count=17, total=62, rate=0.274, rank=98.7,
                  severity=Severity.SEVERE)
    text = render_what_the_data_shows(d)
    assert "17 corrections-related outcome(s) out of 62 substantive inspection(s) recorded (27.4%)" in text
    assert "98th percentile" in text or "99th percentile" in text  # 98.7 rounds to 99
    assert "'severe' statistical tier" in text


def test_friction_repeated_not_ready():
    d = _friction(StallCategory.REPEATED_NOT_READY_OUTCOMES, observed_count=18, total=62)
    text = render_what_the_data_shows(d)
    assert "not-ready-related" in text


def test_friction_repeated_cancellations():
    d = _friction(StallCategory.REPEATED_CANCELLATIONS, observed_count=5, total=62)
    text = render_what_the_data_shows(d)
    assert "cancelled-related" in text


# --- structural safeguard tests specific to the renderer ---


def test_active_peer_dwell_never_claims_normal_duration():
    d = _delay(StallCategory.PRE_ISSUANCE_STATUS_DWELL, elapsed_days=1833,
               benchmark_semantics=BenchmarkSemantics.ACTIVE_PEER_DWELL, rank=74.6)
    text = render_what_the_data_shows(d)
    assert_no_normal_duration_claim(text)
    assert "currently observed comparable permits" in text


def test_ongoing_interval_never_claims_known_total():
    d = _delay(StallCategory.INACTIVITY_SINCE_LAST_INSPECTION, elapsed_days=999,
               interval_state=IntervalState.ONGOING)
    text = render_what_the_data_shows(d)
    assert_no_known_total_duration_claim(text)


def test_completed_interval_does_not_get_ongoing_caveat():
    d = _delay(StallCategory.INTER_INSPECTION_GAP, elapsed_days=50, interval_state=IntervalState.COMPLETED)
    text = render_what_the_data_shows(d)
    assert "not closed" not in text


def test_persistence_confirmed_adds_the_careful_phrase_not_the_strong_one():
    d = _delay(StallCategory.PRE_ISSUANCE_STATUS_DWELL, persistence=True)
    text = render_what_the_data_shows(d)
    assert "confirmed present across repeated observation" in text
    assert "continuously remained" not in text


def test_all_rendered_facts_are_free_of_blame_language():
    detections = [
        _delay(StallCategory.PRE_ISSUANCE_STATUS_DWELL),
        _delay(StallCategory.ISSUANCE_TO_FIRST_INSPECTION_GAP, interval_state=IntervalState.COMPLETED),
        _delay(StallCategory.NO_INSPECTION_SINCE_ISSUANCE),
        _delay(StallCategory.INTER_INSPECTION_GAP, interval_state=IntervalState.COMPLETED),
        _delay(StallCategory.INACTIVITY_SINCE_LAST_INSPECTION),
        _delay(StallCategory.FINALIZATION_GAP, stage_label="cofo_track", interval_state=IntervalState.COMPLETED),
        _friction(StallCategory.REPEATED_CORRECTIONS),
        _friction(StallCategory.REPEATED_NOT_READY_OUTCOMES),
        _friction(StallCategory.REPEATED_CANCELLATIONS),
    ]
    for d in detections:
        assert_no_blame_language(render_what_the_data_shows(d), context=str(d.category))


def test_ordinal_suffix_correctness():
    """A real bug found during Agent 3's demo run: naive '{n}th' formatting
    produced '92th percentile' instead of '92nd'. Locks in the fix,
    including the 11/12/13 exceptions."""
    cases = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 11: "11th", 12: "12th", 13: "13th",
             21: "21st", 22: "22nd", 23: "23rd", 91: "91st", 92: "92nd", 97: "97th", 100: "100th"}
    for n, expected in cases.items():
        assert _ordinal(n) == expected


def test_no_percentile_language_when_rank_missing():
    d = _delay(StallCategory.PRE_ISSUANCE_STATUS_DWELL, elapsed_days=100)
    object.__setattr__(d, "percentile_rank", None)  # frozen dataclass, bypass for this one test
    text = render_what_the_data_shows(d)
    assert "longer than" not in text
    assert "percentile" not in text
