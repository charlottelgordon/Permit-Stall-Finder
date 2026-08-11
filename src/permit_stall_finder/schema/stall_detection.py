"""The Agent 2 -> Agent 3 contract, and the structural controls that keep
its language honest. See research/AGENT2_DESIGN.md for the full design
rationale; this module implements exactly what's specified there.

Two mandatory disciplines carried from the design doc:

1. benchmark_semantics distinguishes ACTIVE_PEER_DWELL (a length-biased
   cross-sectional cohort of currently-active peers) from COMPLETED_INTERVAL
   (an unbiased cohort of intervals that already concluded). Language
   generated from an ACTIVE_PEER_DWELL detection may never claim permits
   "normally take" a given duration.

2. status_persistence_confirmed_by_repeated_observation plus
   render_dwell_statement() are the structural gate against overstating
   continuity: "N days have elapsed since status_date" is always safe;
   "has continuously remained in this status" requires repeated snapshot
   confirmation and is never produced otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from permit_stall_finder.schema.journey import MatchStatus


class StallClass(str, Enum):
    DELAY = "delay"
    FRICTION = "friction"


class StallCategory(str, Enum):
    PRE_ISSUANCE_STATUS_DWELL = "pre_issuance_status_dwell"
    ISSUANCE_TO_FIRST_INSPECTION_GAP = "issuance_to_first_inspection_gap"
    NO_INSPECTION_SINCE_ISSUANCE = "no_inspection_since_issuance"
    INTER_INSPECTION_GAP = "inter_inspection_gap"
    INACTIVITY_SINCE_LAST_INSPECTION = "inactivity_since_last_inspection"
    FINALIZATION_GAP = "finalization_gap"
    REPEATED_CORRECTIONS = "repeated_corrections"
    REPEATED_NOT_READY_OUTCOMES = "repeated_not_ready_outcomes"
    REPEATED_CANCELLATIONS = "repeated_cancellations"


class CohortSource(str, Enum):
    CROSS_SECTIONAL_CURRENT_SNAPSHOT = "cross_sectional_current_snapshot"
    COMPLETED_TRANSITIONS_OWN_HISTORY = "completed_transitions_own_history"
    SOURCE_EVENT_LOG = "source_event_log"


class BenchmarkSemantics(str, Enum):
    ACTIVE_PEER_DWELL = "active_peer_dwell"
    COMPLETED_INTERVAL = "completed_interval"


class IntervalState(str, Enum):
    COMPLETED = "completed"
    ONGOING = "ongoing"


class LifecycleStage(str, Enum):
    """Friction cohort stratification — COMPLETED and ONGOING permits are
    never pooled into the same cohort."""

    COMPLETED = "completed"
    ONGOING = "ongoing"


class CohortConfidence(str, Enum):
    FULL = "full"                  # n >= min_full (default 30)
    REDUCED = "reduced"            # min_reduced <= n < min_full (default 10-30)
    INSUFFICIENT = "insufficient"  # n < min_reduced -> no percentile/severity
    ZERO_VARIANCE = "zero_variance"
    # Cohort has adequate n but effectively no spread (e.g. every observed
    # value is 0) -- a percentile rank against a degenerate distribution is
    # not discriminatory (any value ties for the 100th percentile) and must
    # not be used to assign severity. See analysis/cohorts.py and
    # AGENT2_DESIGN.md's zero-variance-cohort fix.


class Severity(str, Enum):
    WATCH = "watch"        # [75, 90)
    ELEVATED = "elevated"  # [90, 95)
    SEVERE = "severe"      # >= 95
    UNSCORED = "unscored"  # CohortConfidence.INSUFFICIENT


class TerminalTrack(str, Enum):
    """FINALIZATION_GAP cohort stratification — see AGENT2_DESIGN.md §7."""

    COFO_TRACK = "cofo_track"
    FINALED_ONLY_TRACK = "finaled_only_track"


@dataclass(frozen=True)
class SeverityThresholds:
    watch: float = 75.0
    elevated: float = 90.0
    severe: float = 95.0


@dataclass(frozen=True)
class CohortDefinition:
    dimensions: dict[str, str]
    specificity_level: int
    source: CohortSource
    benchmark_semantics: BenchmarkSemantics
    n: int
    confidence: CohortConfidence
    median_days_or_count: float | None  # contextual only — never a severity threshold
    p75_days_or_count: float | None
    p90_days_or_count: float | None
    p95_days_or_count: float | None
    computed_at: datetime


@dataclass(frozen=True)
class EvidenceRef:
    kind: str  # "status_snapshot" | "inspection_event" | "inspection_event_pair" | "event_count"
    description: str
    source_event_ids: list[str] = field(default_factory=list)
    source_snapshot_refs: list[tuple[str, datetime]] = field(default_factory=list)
    source_status_date: date | None = None
    observed_dates: list[date] = field(default_factory=list)
    matching_method: str | None = None
    # "exact_inspection_type" | "mapped_stage_fallback" when this evidence
    # pairs two events (e.g. corrections -> reinspection)


@dataclass(frozen=True)
class DelayStallDetection:
    permit_number: str
    category: StallCategory
    stage_label: str
    generated_at: datetime

    elapsed_days: int
    as_of: datetime
    interval_state: IntervalState

    status_persistence_confirmed_by_repeated_observation: bool

    cohort: CohortDefinition
    percentile_rank: float | None
    excess_days_vs_median: float | None
    severity: Severity

    evidence: list[EvidenceRef]
    cannot_infer: list[str]
    caveats: list[str]
    based_on_match_status: MatchStatus
    carried_data_quality_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FrictionStallDetection:
    permit_number: str
    category: StallCategory
    generated_at: datetime

    observed_count: int
    meets_minimum_count: bool
    minimum_count_required: int

    lifecycle_stage: LifecycleStage
    total_inspection_opportunities: int
    observed_lifecycle_days: int
    correction_rate: float | None
    meets_minimum_exposure: bool

    cohort: CohortDefinition
    percentile_rank: float | None
    excess_count_vs_median: float | None
    severity: Severity

    evidence: list[EvidenceRef]
    cannot_infer: list[str]
    caveats: list[str]
    based_on_match_status: MatchStatus
    carried_data_quality_flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StallAssessment:
    permit_number: str
    generated_at: datetime
    source_permit_journey_generated_at: datetime

    detections: list[DelayStallDetection | FrictionStallDetection]
    coverage_gaps: list[str]
    summary_note: str


def render_dwell_statement(detection: DelayStallDetection) -> str:
    """The sanctioned way to turn a dwell-time DelayStallDetection into a
    sentence. Structurally cannot produce "has continuously remained"
    phrasing unless status_persistence_confirmed_by_repeated_observation is
    True, and even then stays at the more careful "confirmed present across
    repeated observation" wording rather than escalating the claim. Never
    translates an ACTIVE_PEER_DWELL benchmark into "permits normally take
    N days" language — that phrasing requires a COMPLETED_INTERVAL cohort.
    """
    statement = (
        f"{detection.elapsed_days} days have elapsed since the published "
        f"'{detection.stage_label}' status_date."
    )
    if (
        detection.cohort.benchmark_semantics == BenchmarkSemantics.ACTIVE_PEER_DWELL
        and detection.percentile_rank is not None
    ):
        statement += (
            f" This elapsed time is longer than {detection.percentile_rank:.0f}% "
            "of currently observed comparable permits with the same "
            "published status."
        )
    elif (
        detection.cohort.benchmark_semantics == BenchmarkSemantics.COMPLETED_INTERVAL
        and detection.percentile_rank is not None
    ):
        statement += (
            f" This is longer than {detection.percentile_rank:.0f}% of "
            "comparable completed intervals."
        )
    if detection.status_persistence_confirmed_by_repeated_observation:
        statement += " This status has been confirmed present across repeated observation."
    return statement
