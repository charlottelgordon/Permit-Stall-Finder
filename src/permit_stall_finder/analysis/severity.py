"""Percentile-band severity classification. The median is contextual only
-- it is never a threshold input here (AGENT2_DESIGN.md §3)."""

from __future__ import annotations

from permit_stall_finder.schema.stall_detection import Severity, SeverityThresholds


def percentile_rank(value: float, population: list[float]) -> float:
    """Percent of population at or below value. 0-100. Empty population is
    a caller error -- check CohortConfidence before calling this."""
    if not population:
        raise ValueError("percentile_rank requires a non-empty population")
    at_or_below = sum(1 for v in population if v <= value)
    return 100.0 * at_or_below / len(population)


def classify_severity(
    rank: float | None, thresholds: SeverityThresholds = SeverityThresholds()
) -> Severity | None:
    """Returns None (not a Severity) when rank is below the watch
    threshold -- callers must not emit a detection in that case; silence
    is itself the signal ("not unusually slow/frequent"), not a `NONE`
    enum member to keep the output list meaningful rather than noisy."""
    if rank is None:
        return Severity.UNSCORED
    if rank >= thresholds.severe:
        return Severity.SEVERE
    if rank >= thresholds.elevated:
        return Severity.ELEVATED
    if rank >= thresholds.watch:
        return Severity.WATCH
    return None
