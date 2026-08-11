from __future__ import annotations

from datetime import datetime, timezone

from permit_stall_finder.analysis.cohorts import (
    CohortTier,
    build_cohort_with_fallback,
    compute_cohort_definition,
)
from permit_stall_finder.schema.stall_detection import (
    BenchmarkSemantics,
    CohortConfidence,
    CohortSource,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def test_compute_cohort_definition_full_confidence():
    population = [float(i) for i in range(40)]
    cohort = compute_cohort_definition(
        population, {"a": "1"}, 1, CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, NOW
    )
    assert cohort.n == 40
    assert cohort.confidence == CohortConfidence.FULL
    assert cohort.median_days_or_count == 19.5


def test_compute_cohort_definition_reduced_confidence():
    population = [float(i) for i in range(15)]
    cohort = compute_cohort_definition(
        population, {}, 1, CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, NOW
    )
    assert cohort.confidence == CohortConfidence.REDUCED


def test_compute_cohort_definition_insufficient_confidence_has_no_stats_when_empty():
    cohort = compute_cohort_definition(
        [], {}, 1, CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, NOW
    )
    assert cohort.confidence == CohortConfidence.INSUFFICIENT
    assert cohort.n == 0
    assert cohort.median_days_or_count is None


def test_fallback_ladder_uses_first_tier_with_adequate_confidence():
    calls = []

    def fetch(dimensions, exclude):
        calls.append(dict(dimensions))
        if dimensions == {"permit_type": "Bldg-New", "status": "X"}:
            return []  # tier 1: too sparse
        return [float(i) for i in range(50)]  # tier 2: adequate

    tiers = [
        CohortTier({"permit_type": "Bldg-New", "status": "X"}, 1),
        CohortTier({"status": "X"}, 2),
    ]
    cohort, population = build_cohort_with_fallback(
        tiers, fetch, "TARGET-1", CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, NOW
    )
    assert cohort.specificity_level == 2
    assert cohort.confidence == CohortConfidence.FULL
    assert len(calls) == 2  # tried tier 1, fell back to tier 2


def test_fallback_ladder_returns_floor_tier_when_all_insufficient():
    def fetch(dimensions, exclude):
        return [1.0, 2.0]  # always too sparse

    tiers = [CohortTier({"a": "1"}, 1), CohortTier({"a": "2"}, 2)]
    cohort, population = build_cohort_with_fallback(
        tiers, fetch, "TARGET-1", CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, NOW
    )
    assert cohort.confidence == CohortConfidence.INSUFFICIENT
    assert cohort.specificity_level == 2  # the coarsest (last) tier


def test_compute_cohort_definition_zero_variance_all_identical_values():
    """The FINALIZATION_GAP bug: a cohort with adequate n but every value
    identical (e.g. same-day finalization) must not be treated as FULL --
    a percentile against it would tie-inflate any value to ~100."""
    population = [0.0] * 50
    cohort = compute_cohort_definition(
        population, {}, 1, CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, NOW
    )
    assert cohort.confidence == CohortConfidence.ZERO_VARIANCE
    assert cohort.n == 50
    # summary stats are still reported (all 0) -- just not usable for severity
    assert cohort.median_days_or_count == 0.0


def test_compute_cohort_definition_realistic_low_variance_is_not_zero_variance():
    """A friction-count-shaped population (mostly 0s, a few 1s) has real,
    if modest, spread and must NOT be treated as degenerate -- a permit
    with 5 corrections against this population is a genuine outlier."""
    population = [0.0] * 45 + [1.0] * 5
    cohort = compute_cohort_definition(
        population, {}, 1, CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, NOW
    )
    assert cohort.confidence == CohortConfidence.FULL


def test_fallback_ladder_skips_zero_variance_tier_for_a_better_one():
    def fetch(dimensions, exclude):
        if dimensions.get("level") == "specific":
            return [0.0] * 40  # degenerate but plenty of data
        return [float(i) for i in range(40)]  # coarser tier: real spread

    tiers = [CohortTier({"level": "specific"}, 1), CohortTier({"level": "coarse"}, 2)]
    cohort, population = build_cohort_with_fallback(
        tiers, fetch, "TARGET-1", CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, NOW
    )
    assert cohort.specificity_level == 2
    assert cohort.confidence == CohortConfidence.FULL


def test_fallback_ladder_returns_zero_variance_floor_when_no_tier_has_spread():
    def fetch(dimensions, exclude):
        return [0.0] * 40  # every tier is degenerate

    tiers = [CohortTier({"a": "1"}, 1), CohortTier({"a": "2"}, 2)]
    cohort, population = build_cohort_with_fallback(
        tiers, fetch, "TARGET-1", CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, NOW
    )
    assert cohort.confidence == CohortConfidence.ZERO_VARIANCE
    assert cohort.specificity_level == 2  # the coarsest (last) tier


def test_target_permit_is_excluded_from_its_own_cohort():
    """AGENT2_DESIGN.md §6d, generalized to all cohorts: fetch_population
    always receives the permit being assessed so it can filter it out at
    the source."""
    received_excludes = []

    def fetch(dimensions, exclude):
        received_excludes.append(exclude)
        return [float(i) for i in range(30)]

    tiers = [CohortTier({"a": "1"}, 1)]
    build_cohort_with_fallback(
        tiers, fetch, "TARGET-PERMIT-123",
        CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, NOW,
    )
    assert received_excludes == ["TARGET-PERMIT-123"]
