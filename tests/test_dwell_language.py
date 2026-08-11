"""Structural gate on continuity language (refinement #2, hardened).
render_dwell_statement must never produce "continuously remained" phrasing
unless status_persistence_confirmed_by_repeated_observation is True, and
must never translate an ACTIVE_PEER_DWELL benchmark into "permits normally
take N days" language."""

from __future__ import annotations

from datetime import datetime, timezone

from permit_stall_finder.schema.journey import MatchStatus
from permit_stall_finder.schema.stall_detection import (
    BenchmarkSemantics,
    CohortConfidence,
    CohortDefinition,
    CohortSource,
    DelayStallDetection,
    IntervalState,
    Severity,
    StallCategory,
    render_dwell_statement,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def _cohort(benchmark_semantics, confidence=CohortConfidence.FULL, n=100):
    return CohortDefinition(
        dimensions={"status_desc": "PC Approved"},
        specificity_level=1,
        source=CohortSource.CROSS_SECTIONAL_CURRENT_SNAPSHOT,
        benchmark_semantics=benchmark_semantics,
        n=n,
        confidence=confidence,
        median_days_or_count=100.0,
        p75_days_or_count=200.0,
        p90_days_or_count=300.0,
        p95_days_or_count=400.0,
        computed_at=NOW,
    )


def _detection(persistence_confirmed: bool, benchmark_semantics=BenchmarkSemantics.ACTIVE_PEER_DWELL, rank=80.0):
    return DelayStallDetection(
        permit_number="TEST-1",
        category=StallCategory.PRE_ISSUANCE_STATUS_DWELL,
        stage_label="PC Approved",
        generated_at=NOW,
        elapsed_days=261,
        as_of=NOW,
        interval_state=IntervalState.ONGOING,
        status_persistence_confirmed_by_repeated_observation=persistence_confirmed,
        cohort=_cohort(benchmark_semantics),
        percentile_rank=rank,
        excess_days_vs_median=161.0,
        severity=Severity.ELEVATED,
        evidence=[],
        cannot_infer=[],
        caveats=[],
        based_on_match_status=MatchStatus.UNISSUED,
    )


def test_single_observation_never_claims_continuity():
    statement = render_dwell_statement(_detection(persistence_confirmed=False))
    assert "261 days have elapsed since the published 'PC Approved' status_date." in statement
    assert "continuously remained" not in statement
    assert "confirmed present across repeated observation" not in statement


def test_repeated_observation_confirms_persistence_with_careful_wording():
    statement = render_dwell_statement(_detection(persistence_confirmed=True))
    assert "confirmed present across repeated observation" in statement
    # even the confirmed case must not escalate to the stronger phrasing
    assert "continuously remained" not in statement


def test_active_peer_dwell_never_produces_normally_take_language():
    statement = render_dwell_statement(
        _detection(persistence_confirmed=False, benchmark_semantics=BenchmarkSemantics.ACTIVE_PEER_DWELL, rank=82.0)
    )
    assert "normally take" not in statement
    assert "typically take" not in statement
    assert "longer than 82% of currently observed comparable permits" in statement


def test_completed_interval_may_use_typically_takes_language():
    statement = render_dwell_statement(
        _detection(persistence_confirmed=False, benchmark_semantics=BenchmarkSemantics.COMPLETED_INTERVAL, rank=82.0)
    )
    assert "longer than 82% of comparable completed intervals" in statement
    assert "normally take" not in statement  # this exact phrase is still never used, by design


def test_no_percentile_language_when_rank_is_none():
    d = _detection(persistence_confirmed=False, rank=None)
    statement = render_dwell_statement(d)
    assert "261 days have elapsed" in statement
    assert "longer than" not in statement
