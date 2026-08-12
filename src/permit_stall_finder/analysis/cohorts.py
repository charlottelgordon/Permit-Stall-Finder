"""Cohort statistics and the fallback ladder (AGENT2_DESIGN.md §2d/§2e).

Population *sourcing* (querying the live datasets) is injected via a
`fetch_population` callable so this module stays pure and independently
testable with synthetic populations -- no network access required to test
the ladder/confidence-tier logic itself.

The target permit is always excluded from its own cohort (§6d, generalized
to every cohort type, not just friction): every fetch_population call
receives the permit being assessed and is responsible for filtering it out
at the source.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from permit_stall_finder.schema.stall_detection import (
    BenchmarkSemantics,
    CohortConfidence,
    CohortDefinition,
    CohortSource,
)

FetchPopulation = Callable[[dict[str, str], str], list[float]]
"""(dimensions, exclude_permit_number) -> population values (days or counts)."""

MIN_FULL_CONFIDENCE_N = 30
MIN_REDUCED_CONFIDENCE_N = 10

ZERO_VARIANCE_RANGE_THRESHOLD = 1.0
"""Every population this project computes is in whole days or whole event
counts, so a range (max - min) below one full unit means every observed
value is effectively the same number -- e.g. a same-day-finalization
population where every value is 0.0 has range exactly 0.

Deliberately a *range* check, not a stdev threshold: an earlier version
used stdev < 0.5, which correctly caught the degenerate all-zero
FINALIZATION_GAP case but also mis-flagged legitimate low-variance count
data (e.g. a friction population that's mostly 0s with a handful of 1s --
stdev ~0.3, but the spread is real and discriminatory: a permit with 5
corrections against that population is genuinely unusual). Range < 1.0
catches only true ties (all values identical at the metric's own
granularity) without penalizing realistic, low-but-nonzero-spread data."""


@dataclass(frozen=True)
class CohortTier:
    dimensions: dict[str, str]
    specificity_level: int


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (matches numpy's default 'linear'
    method) -- implemented without a numpy dependency."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (len(sorted_values) - 1) * (pct / 100)
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


def _confidence_for(n: int) -> CohortConfidence:
    if n >= MIN_FULL_CONFIDENCE_N:
        return CohortConfidence.FULL
    if n >= MIN_REDUCED_CONFIDENCE_N:
        return CohortConfidence.REDUCED
    return CohortConfidence.INSUFFICIENT


def _is_zero_variance(population: list[float]) -> bool:
    if len(population) < 2:
        return False  # too small to judge variance at all; handled by _confidence_for
    return (max(population) - min(population)) < ZERO_VARIANCE_RANGE_THRESHOLD


def compute_cohort_definition(
    population: list[float],
    dimensions: dict[str, str],
    specificity_level: int,
    source: CohortSource,
    benchmark_semantics: BenchmarkSemantics,
    computed_at: datetime,
) -> CohortDefinition:
    n = len(population)
    confidence = _confidence_for(n)
    if confidence != CohortConfidence.INSUFFICIENT and _is_zero_variance(population):
        # Adequate sample size, but the population carries no discriminatory
        # information (every permit lands at ~the same value) -- a
        # percentile rank against this would tie-inflate to ~100 for any
        # value at or above the constant, which is exactly the
        # FINALIZATION_GAP bug this check exists to prevent.
        confidence = CohortConfidence.ZERO_VARIANCE
    if n == 0:
        median = p75 = p90 = p95 = None
    else:
        s = sorted(population)
        median = _percentile(s, 50)
        p75 = _percentile(s, 75)
        p90 = _percentile(s, 90)
        p95 = _percentile(s, 95)
    return CohortDefinition(
        dimensions=dimensions,
        specificity_level=specificity_level,
        source=source,
        benchmark_semantics=benchmark_semantics,
        n=n,
        confidence=confidence,
        median_days_or_count=median,
        p75_days_or_count=p75,
        p90_days_or_count=p90,
        p95_days_or_count=p95,
        computed_at=computed_at,
    )


def build_cohort_with_fallback(
    tiers: list[CohortTier],
    fetch_population: FetchPopulation,
    exclude_permit_number: str,
    source: CohortSource,
    benchmark_semantics: BenchmarkSemantics,
    computed_at: datetime,
) -> tuple[CohortDefinition, list[float]]:
    """Tries tiers most-specific first. Returns the first tier reaching at
    least REDUCED confidence (n >= 10) *and* non-degenerate variance, plus
    its raw population (so callers can compute an exact percentile rank for
    their specific value rather than approximating from summary stats). A
    zero-variance tier is treated like an inadequate one here -- a coarser
    tier might have real spread even if a narrow one doesn't -- so the
    ladder keeps falling back past it. If no tier reaches usable confidence,
    returns the coarsest (last) tier's result with confidence=INSUFFICIENT
    or ZERO_VARIANCE -- callers must check `.confidence` and route to
    coverage_gaps rather than fabricate a percentile from it (§2e)."""
    if not tiers:
        raise ValueError("build_cohort_with_fallback requires at least one tier")

    _unusable = (CohortConfidence.INSUFFICIENT, CohortConfidence.ZERO_VARIANCE)
    floor_result: tuple[CohortDefinition, list[float]] | None = None
    for tier in tiers:
        population = fetch_population(tier.dimensions, exclude_permit_number)
        cohort = compute_cohort_definition(
            population, tier.dimensions, tier.specificity_level, source, benchmark_semantics, computed_at
        )
        if cohort.confidence not in _unusable:
            return cohort, population
        floor_result = (cohort, population)
    return floor_result
