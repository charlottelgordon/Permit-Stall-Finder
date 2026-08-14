"""Conditional remaining-duration forecast for an ONGOING interval
benchmarked against a COMPLETED_INTERVAL cohort (AGENT2_DESIGN.md's
BenchmarkSemantics split, schema/stall_detection.py:52-54).

Only ever answers one question: among population members that were
*already* at least this far along, how much MORE time did they take
before concluding? That's a distributional statement about other
permits, never a point-estimate promise about the one being assessed --
see schema/stall_detection.py's render_remaining_duration_forecast() for
the sanctioned way to turn this into a sentence.

Deliberately excluded: ACTIVE_PEER_DWELL cohorts (PRE_ISSUANCE_STATUS_DWELL
is the only one) -- their length-bias means even a completed member's
raw duration overrepresents slow permits, so a conditional tail drawn
from that population would compound the bias rather than just carry it
forward. This module has no opinion on that exclusion; callers must not
invoke it for an ACTIVE_PEER_DWELL cohort at all.
"""

from __future__ import annotations

import math

from permit_stall_finder.analysis.cohorts import MIN_FULL_CONFIDENCE_N, MIN_REDUCED_CONFIDENCE_N
from permit_stall_finder.schema.stall_detection import CohortConfidence, RemainingDurationForecast


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (matches analysis/cohorts.py's
    _percentile exactly) -- kept as a local copy rather than importing
    that module's underscore-prefixed helper, so this module stays a
    self-contained, independently testable unit like severity.py."""
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


def conditional_remaining_duration(
    elapsed_days: float,
    population: list[float],
    min_n: int = MIN_REDUCED_CONFIDENCE_N,
) -> RemainingDurationForecast | None:
    """Among `population` members whose own completed duration was >=
    elapsed_days (comparable permits that were already at least this
    delayed), returns the distribution of how much MORE time they took
    beyond elapsed_days. Returns None when fewer than min_n population
    members qualify -- never speculate on a conditional sample thinner
    than the codebase's existing confidence floor (same
    MIN_REDUCED_CONFIDENCE_N used everywhere else a cohort is judged
    usable, analysis/cohorts.py)."""
    tail = sorted(v - elapsed_days for v in population if v >= elapsed_days)
    if len(tail) < min_n:
        return None
    return RemainingDurationForecast(
        conditional_n=len(tail),
        conditional_confidence=_confidence_for(len(tail)),
        remaining_p50_days=_percentile(tail, 50),
        remaining_p75_days=_percentile(tail, 75),
        remaining_p90_days=_percentile(tail, 90),
    )
