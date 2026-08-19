"""Agent 2 — Stall Detector.

Consumes a PermitJourney (Agent 1's output) and produces a StallAssessment:
zero or more DelayStallDetection/FrictionStallDetection records, plus an
explicit coverage_gaps list for cases where a category was considered but
couldn't be responsibly assessed (insufficient cohort, zero-variance cohort,
ineligible/exempt/ambiguous coverage, insufficient exposure). Never
fabricates a severity from inadequate or non-discriminatory data; never
treats absence of inspections as evidence on its own.

Four MVP scope reductions from AGENT2_DESIGN.md, classified and stated here
so they aren't silently narrower than the design promised (see §9 of the
design doc for the full reasoning behind each classification):

ACCEPTABLE MVP DEFERRALS (do not produce misleading results, only less
precise ones -- reviewed and confirmed unrelated to the two bugs fixed in
this revision):
  - Year-bucket cohort fallback tier not built; the 2-tier ladder (permit_type
    + stage, then stage-only) still compares against a real, appropriately-
    scoped cohort.
  - Friction cohorts stratify by lifecycle_stage (COMPLETED vs ONGOING, the
    primary/mandatory control, which prevents the worst case: comparing a
    brand-new permit's count against a multi-year completed one) but do not
    further sub-bucket ONGOING permits by exposure tier. total_inspection_
    opportunities is still computed and carried on every detection, and
    gates whether friction is assessed at all -- just not yet used to
    sub-bucket the comparison cohort. Flagged as the most likely of these
    four to eventually matter; next priority if revisited.
  - INTER_INSPECTION_GAP reports only the single largest consecutive-
    substantive gap per permit, not every qualifying gap. This underreports
    (a second real gap elsewhere in the history won't surface) but the gap
    it does report is accurate, not misleading.
  - INTER_INSPECTION_GAP does not implement the same-inspection_type /
    mapped-stage corrections<->reinspection pairing from §5b -- it uses the
    largest gap between any two consecutive substantive events regardless
    of inspection_type. This is a real, true statement ("no inspection
    activity of any kind occurred in this window") even though it's coarser
    than a same-defect-resolution-time signal would be.

FIXED THIS REVISION (were producing materially misleading results):
  - Zero-variance cohorts no longer produce a percentile-based severity
    (CohortConfidence.ZERO_VARIANCE, analysis/cohorts.py) -- previously a
    degenerate cohort (e.g. same-day finalization, stdev=0) tie-inflated any
    value to the 100th percentile.
  - NO_INSPECTION_SINCE_ISSUANCE now also checks analysis.
    inspection_exemption before the aggregate type-level coverage-rate gate
    -- previously a $0-valuation administrative/documentary permit
    (e.g. a legal-description correction) could be flagged SEVERE purely
    because its permit_type happened to clear the aggregate rate.
"""

from __future__ import annotations

from datetime import datetime, timezone

from permit_stall_finder import config
from permit_stall_finder.analysis import cohorts as cohort_lib
from permit_stall_finder.analysis.coverage_eligibility import assess_eligibility
from permit_stall_finder.analysis.inspection_exemption import assess_inspection_exemption
from permit_stall_finder.analysis.severity import classify_severity, percentile_rank
from permit_stall_finder.ingestion import cohort_populations as pop
from permit_stall_finder.schema.inspection_vocabulary import ResultFamily, is_substantive, result_family
from permit_stall_finder.schema.journey import MatchStatus, PermitJourney
from permit_stall_finder.schema.stall_detection import (
    BenchmarkSemantics,
    CohortConfidence,
    CohortSource,
    DelayStallDetection,
    EvidenceRef,
    FrictionStallDetection,
    IntervalState,
    LifecycleStage,
    SeverityThresholds,
    StallAssessment,
    StallCategory,
    TerminalTrack,
)
from permit_stall_finder.schema.transitions import collapse_snapshots_to_transitions

_TERMINAL_STATUSES = {
    "Permit Finaled",
    "CofO Issued",
    "CofC Issued",
    "Permit Closed",
    "Permit Expired",
    "Permit Withdrawn",
    "Permit Revoked",
}

_ACTIVE_PEER_DWELL_CAVEAT = (
    "This percentile answers a specific, narrower question than it may "
    "appear to: 'how unusual is this permit's elapsed time among permits "
    "*currently observed* sitting in this same published status?' It does "
    "NOT estimate normal or expected stage-completion time. The comparison "
    "cohort is permits currently sitting in the same status (an active-peer "
    "cohort), not permits whose time in this status has already concluded, "
    "and such a cohort systematically overrepresents slow-moving permits (a "
    "permit that clears a status quickly is less likely to be observed "
    "sitting in it). Do not read this percentile as 'X% of permits "
    "typically finish this stage faster than this one' -- only as 'this "
    "permit's current wait is longer than X% of permits currently waiting "
    "in the same status.'"
)

_ONGOING_CAVEAT = (
    "This interval has not closed. elapsed_days reflects time observed so "
    "far, not a completed duration -- the eventual total is not known."
)

_ONGOING_VS_COMPLETED_COHORT_CAVEAT = (
    "This ongoing, still-accumulating interval is being compared against a "
    "cohort of intervals that already concluded. An open interval that has "
    "already exceeded a given percentile of completed intervals is a "
    "meaningful signal, but the comparison itself is asymmetric -- it is "
    "not a like-for-like comparison of two completed durations."
)

_RESPONSIBILITY_CANNOT_INFER = (
    "Which party (the applicant, their contractor, or LADBS) is responsible "
    "for this elapsed time or gap cannot be determined from this data."
)
_CAUSE_CANNOT_INFER = (
    "Why this specific permit has not progressed further cannot be "
    "determined from this data -- this tool observes elapsed time and "
    "counts, not cause."
)


def _cohort_gap_message(label: str, cohort) -> str | None:
    """Returns a coverage_gaps message when the cohort can't responsibly
    support a percentile-based severity -- either too few observations
    (INSUFFICIENT) or an adequately-sized but non-discriminatory
    population (ZERO_VARIANCE, e.g. a same-day-finalization cohort where
    every observed value is 0). Returns None when the cohort is usable."""
    if cohort.confidence == CohortConfidence.INSUFFICIENT:
        return f"{label}: insufficient cohort data (n={cohort.n})."
    if cohort.confidence == CohortConfidence.ZERO_VARIANCE:
        return (
            f"{label}: ZERO_VARIANCE_COHORT -- the comparison cohort (n={cohort.n}) has "
            "no meaningful spread (observed values are effectively identical), so it "
            "provides no discriminatory information and cannot support a percentile-based "
            "severity."
        )
    return None


def assess_stalls(
    journey: PermitJourney,
    now: datetime | None = None,
    thresholds: SeverityThresholds = SeverityThresholds(),
    sample_size: int = config.DEFAULT_COHORT_SAMPLE_SIZE,
) -> StallAssessment:
    now = now or datetime.now(timezone.utc)
    as_of = now.date()

    if journey.match_status == MatchStatus.PERMIT_NOT_FOUND or journey.latest_snapshot is None:
        return StallAssessment(
            permit_number=journey.permit_number,
            generated_at=now,
            source_permit_journey_generated_at=journey.generated_at,
            detections=[],
            coverage_gaps=["Permit not found by Agent 1 -- no stall assessment possible."],
            summary_note="No assessment: permit not found in the source dataset.",
        )

    snapshot = journey.latest_snapshot
    permit_type = snapshot.permit_type
    detections: list[DelayStallDetection | FrictionStallDetection] = []
    coverage_gaps: list[str] = []

    data_quality_flags = [f.value for f in journey.data_quality_flags]

    if journey.match_status == MatchStatus.UNISSUED:
        d, gap = _detect_pre_issuance_dwell(
            journey, permit_type, as_of, now, thresholds, data_quality_flags
        )
        _append(detections, coverage_gaps, d, gap)
    else:
        substantive_events = [e for e in journey.inspection_events if is_substantive(e.inspection_result)]

        d, gap = _detect_issuance_to_first_inspection_gap(
            journey, permit_type, substantive_events, now, thresholds, data_quality_flags, sample_size
        )
        _append(detections, coverage_gaps, d, gap)

        if not substantive_events:
            d, gap = _detect_no_inspection_since_issuance(
                journey, permit_type, as_of, now, thresholds, data_quality_flags, sample_size
            )
            _append(detections, coverage_gaps, d, gap)

        d, gap = _detect_inter_inspection_gap(
            journey, permit_type, substantive_events, now, thresholds, data_quality_flags, sample_size
        )
        _append(detections, coverage_gaps, d, gap)

        if snapshot.status_desc not in _TERMINAL_STATUSES:
            d, gap = _detect_inactivity_since_last_inspection(
                journey, permit_type, substantive_events, as_of, now, thresholds, data_quality_flags, sample_size
            )
            _append(detections, coverage_gaps, d, gap)
        else:
            d, gap = _detect_finalization_gap(
                journey, permit_type, substantive_events, now, thresholds, data_quality_flags, sample_size
            )
            _append(detections, coverage_gaps, d, gap)

        for category, fam in (
            (StallCategory.REPEATED_CORRECTIONS, ResultFamily.CORRECTIONS),
            (StallCategory.REPEATED_NOT_READY_OUTCOMES, ResultFamily.NOT_READY),
            (StallCategory.REPEATED_CANCELLATIONS, ResultFamily.CANCELLED),
        ):
            d, gap = _detect_friction(
                journey, permit_type, category, fam, substantive_events, as_of, now,
                thresholds, data_quality_flags, sample_size,
            )
            _append(detections, coverage_gaps, d, gap)

    summary_note = _summarize(detections, coverage_gaps)
    return StallAssessment(
        permit_number=journey.permit_number,
        generated_at=now,
        source_permit_journey_generated_at=journey.generated_at,
        detections=detections,
        coverage_gaps=coverage_gaps,
        summary_note=summary_note,
    )


def _append(detections, coverage_gaps, detection, gap_message) -> None:
    if detection is not None:
        detections.append(detection)
    if gap_message is not None:
        coverage_gaps.append(gap_message)


def _summarize(detections, coverage_gaps) -> str:
    if not detections and not coverage_gaps:
        return "No delay or friction signals reached the reporting threshold; no coverage gaps encountered."
    parts = []
    if detections:
        by_sev = {}
        for d in detections:
            by_sev[d.severity.value] = by_sev.get(d.severity.value, 0) + 1
        counts = ", ".join(f"{n} {sev}" for sev, n in sorted(by_sev.items()))
        parts.append(
            f"{len(detections)} detection(s) ({counts}). Each describes an independent aspect "
            "of this permit's history and may have unrelated causes -- they are not combined "
            "into a single score."
        )
    if coverage_gaps:
        parts.append(f"{len(coverage_gaps)} categor(y/ies) could not be responsibly assessed (see coverage_gaps).")
    return " ".join(parts)


# --- Pre-issuance -----------------------------------------------------


def _detect_pre_issuance_dwell(journey, permit_type, as_of, now, thresholds, data_quality_flags):
    snapshot = journey.latest_snapshot
    if snapshot.status_date is None:
        return None, f"PRE_ISSUANCE_STATUS_DWELL: no status_date on record for '{snapshot.status_desc}'."

    elapsed_days = (as_of - snapshot.status_date).days
    full_history = list(journey.prior_snapshots) + [snapshot]
    transitions = collapse_snapshots_to_transitions(full_history)
    persistence_confirmed = bool(transitions) and transitions[-1].confirmed_by_repeated_observation

    def fetch(dimensions: dict[str, str], exclude: str) -> list[float]:
        return pop.fetch_pre_issuance_dwell_population(
            status_desc=dimensions["status_desc"],
            as_of=as_of,
            permit_type=dimensions.get("permit_type"),
            exclude_permit_number=exclude,
        )

    tiers = [
        cohort_lib.CohortTier({"permit_type": permit_type, "status_desc": snapshot.status_desc}, 1),
        cohort_lib.CohortTier({"status_desc": snapshot.status_desc}, 2),
    ]
    cohort, population = cohort_lib.build_cohort_with_fallback(
        tiers, fetch, journey.permit_number,
        CohortSource.CROSS_SECTIONAL_CURRENT_SNAPSHOT, BenchmarkSemantics.ACTIVE_PEER_DWELL, now,
    )
    gap = _cohort_gap_message(
        f"PRE_ISSUANCE_STATUS_DWELL for status '{snapshot.status_desc}' (permit_type={permit_type})", cohort
    )
    if gap:
        return None, gap

    rank = percentile_rank(elapsed_days, population)
    severity = classify_severity(rank, thresholds)
    if severity is None:
        return None, None

    caveats = [_ACTIVE_PEER_DWELL_CAVEAT, _ONGOING_CAVEAT]
    if not persistence_confirmed:
        caveats.append(
            "This permit has been observed in this status on a single occasion; continuous "
            "residence in this status is not confirmed by repeated observation."
        )

    detection = DelayStallDetection(
        permit_number=journey.permit_number,
        category=StallCategory.PRE_ISSUANCE_STATUS_DWELL,
        stage_label=snapshot.status_desc,
        generated_at=now,
        elapsed_days=elapsed_days,
        as_of=now,
        interval_state=IntervalState.ONGOING,
        status_persistence_confirmed_by_repeated_observation=persistence_confirmed,
        cohort=cohort,
        percentile_rank=rank,
        excess_days_vs_median=(
            elapsed_days - cohort.median_days_or_count if cohort.median_days_or_count is not None else None
        ),
        severity=severity,
        evidence=[
            EvidenceRef(
                kind="status_snapshot",
                description=f"Latest observed snapshot: status_desc='{snapshot.status_desc}', status_date={snapshot.status_date}.",
                source_snapshot_refs=[(journey.permit_number, snapshot.observed_at)],
                source_status_date=snapshot.status_date,
                observed_dates=[snapshot.status_date],
            )
        ],
        cannot_infer=[_RESPONSIBILITY_CANNOT_INFER, _CAUSE_CANNOT_INFER],
        caveats=caveats,
        based_on_match_status=journey.match_status,
        carried_data_quality_flags=data_quality_flags,
    )
    return detection, None


# --- Post-issuance: delay -----------------------------------------------


def _detect_issuance_to_first_inspection_gap(
    journey, permit_type, substantive_events, now, thresholds, data_quality_flags, sample_size
):
    snapshot = journey.latest_snapshot
    if snapshot.issue_date is None or not substantive_events:
        return None, None

    first = substantive_events[0]
    elapsed_days = (first.inspection_date - snapshot.issue_date).days

    def fetch(dimensions: dict[str, str], exclude: str) -> list[float]:
        return pop.fetch_issuance_to_first_inspection_population(
            permit_type=dimensions["permit_type"], exclude_permit_number=exclude, sample_size=sample_size
        )

    tiers = [cohort_lib.CohortTier({"permit_type": permit_type}, 1)]
    cohort, population = cohort_lib.build_cohort_with_fallback(
        tiers, fetch, journey.permit_number,
        CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, now,
    )
    gap = _cohort_gap_message(f"ISSUANCE_TO_FIRST_INSPECTION_GAP for permit_type={permit_type}", cohort)
    if gap:
        return None, gap

    rank = percentile_rank(elapsed_days, population)
    severity = classify_severity(rank, thresholds)
    if severity is None:
        return None, None

    return (
        DelayStallDetection(
            permit_number=journey.permit_number,
            category=StallCategory.ISSUANCE_TO_FIRST_INSPECTION_GAP,
            stage_label="issuance_to_first_inspection",
            generated_at=now,
            elapsed_days=elapsed_days,
            as_of=now,
            interval_state=IntervalState.COMPLETED,
            status_persistence_confirmed_by_repeated_observation=False,
            cohort=cohort,
            percentile_rank=rank,
            excess_days_vs_median=(
                elapsed_days - cohort.median_days_or_count if cohort.median_days_or_count is not None else None
            ),
            severity=severity,
            evidence=[
                EvidenceRef(
                    kind="inspection_event",
                    description=f"issue_date={snapshot.issue_date} -> first substantive inspection "
                    f"'{first.inspection_type}' ({first.inspection_result}) on {first.inspection_date}.",
                    source_event_ids=[first.event_id],
                    observed_dates=[snapshot.issue_date, first.inspection_date],
                )
            ],
            cannot_infer=[_RESPONSIBILITY_CANNOT_INFER, _CAUSE_CANNOT_INFER],
            caveats=[],
            based_on_match_status=journey.match_status,
            carried_data_quality_flags=data_quality_flags,
        ),
        None,
    )


def _detect_no_inspection_since_issuance(journey, permit_type, as_of, now, thresholds, data_quality_flags, sample_size):
    snapshot = journey.latest_snapshot
    if snapshot.issue_date is None:
        return None, None

    # Layer A: permit-level administrative/documentary-permit check, before
    # the aggregate type-level rate. permit_type alone is not enough --
    # see analysis/inspection_exemption.py and the false positive on
    # 18010-20001-05038 this layer exists to fix.
    exemption = assess_inspection_exemption(journey.permit_number, snapshot.work_description, snapshot.valuation)
    if exemption.is_plausibly_exempt:
        return None, (
            f"NO_INSPECTION_SINCE_ISSUANCE not assessed for {journey.permit_number}: {exemption.reasoning} "
            f"(matched signals: {', '.join(exemption.matched_signals)})."
        )
    if exemption.is_ambiguous:
        return None, (
            f"NO_INSPECTION_SINCE_ISSUANCE not assessed for {journey.permit_number}: {exemption.reasoning}"
        )

    # Layer B: aggregate type-level inspection-coverage reliability.
    eligibility = assess_eligibility(permit_type)
    if not eligibility.eligible:
        return None, (
            f"NO_INSPECTION_SINCE_ISSUANCE not assessed for {permit_type}: {eligibility.reason} -- "
            "absence of an inspection record is not currently interpretable as evidence for this "
            "permit type."
        )

    elapsed_days = (as_of - snapshot.issue_date).days

    def fetch(dimensions: dict[str, str], exclude: str) -> list[float]:
        return pop.fetch_issuance_to_first_inspection_population(
            permit_type=dimensions["permit_type"], exclude_permit_number=exclude, sample_size=sample_size
        )

    tiers = [cohort_lib.CohortTier({"permit_type": permit_type}, 1)]
    cohort, population = cohort_lib.build_cohort_with_fallback(
        tiers, fetch, journey.permit_number,
        CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, now,
    )
    gap = _cohort_gap_message(f"NO_INSPECTION_SINCE_ISSUANCE for permit_type={permit_type}", cohort)
    if gap:
        return None, gap

    rank = percentile_rank(elapsed_days, population)
    severity = classify_severity(rank, thresholds)
    if severity is None:
        return None, None

    return (
        DelayStallDetection(
            permit_number=journey.permit_number,
            category=StallCategory.NO_INSPECTION_SINCE_ISSUANCE,
            stage_label="no_inspection_since_issuance",
            generated_at=now,
            elapsed_days=elapsed_days,
            as_of=now,
            interval_state=IntervalState.ONGOING,
            status_persistence_confirmed_by_repeated_observation=False,
            cohort=cohort,
            percentile_rank=rank,
            excess_days_vs_median=(
                elapsed_days - cohort.median_days_or_count if cohort.median_days_or_count is not None else None
            ),
            severity=severity,
            evidence=[
                EvidenceRef(
                    kind="status_snapshot",
                    description=f"issue_date={snapshot.issue_date}; zero inspection records found as of {as_of}. "
                    f"Coverage eligibility: {eligibility.reason}",
                    source_snapshot_refs=[(journey.permit_number, snapshot.observed_at)],
                    observed_dates=[snapshot.issue_date],
                )
            ],
            cannot_infer=[
                _RESPONSIBILITY_CANNOT_INFER,
                "Whether this permit genuinely requires an inspection at all cannot be determined "
                "from this data (some permits, e.g. administrative corrections, legitimately need none).",
            ],
            caveats=[_ONGOING_CAVEAT, _ONGOING_VS_COMPLETED_COHORT_CAVEAT],
            based_on_match_status=journey.match_status,
            carried_data_quality_flags=data_quality_flags,
        ),
        None,
    )


def _detect_inter_inspection_gap(journey, permit_type, substantive_events, now, thresholds, data_quality_flags, sample_size):
    if len(substantive_events) < 2:
        return None, None

    gaps = [
        (a, b, (b.inspection_date - a.inspection_date).days)
        for a, b in zip(substantive_events, substantive_events[1:])
    ]
    worst = max(gaps, key=lambda g: g[2])
    a, b, elapsed_days = worst

    def fetch(dimensions: dict[str, str], exclude: str) -> list[float]:
        return pop.fetch_inter_inspection_gap_population(
            permit_type=dimensions["permit_type"], exclude_permit_number=exclude, sample_size=sample_size
        )

    tiers = [cohort_lib.CohortTier({"permit_type": permit_type}, 1)]
    cohort, population = cohort_lib.build_cohort_with_fallback(
        tiers, fetch, journey.permit_number,
        CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, now,
    )
    gap = _cohort_gap_message(f"INTER_INSPECTION_GAP for permit_type={permit_type}", cohort)
    if gap:
        return None, gap

    rank = percentile_rank(elapsed_days, population)
    severity = classify_severity(rank, thresholds)
    if severity is None:
        return None, None

    correction_note = " (gap begins with a CORRECTIONS-family outcome)" if result_family(a.inspection_result) == ResultFamily.CORRECTIONS else ""
    return (
        DelayStallDetection(
            permit_number=journey.permit_number,
            category=StallCategory.INTER_INSPECTION_GAP,
            stage_label=f"{a.inspection_type} -> {b.inspection_type}",
            generated_at=now,
            elapsed_days=elapsed_days,
            as_of=now,
            interval_state=IntervalState.COMPLETED,
            status_persistence_confirmed_by_repeated_observation=False,
            cohort=cohort,
            percentile_rank=rank,
            excess_days_vs_median=(
                elapsed_days - cohort.median_days_or_count if cohort.median_days_or_count is not None else None
            ),
            severity=severity,
            evidence=[
                EvidenceRef(
                    kind="inspection_event_pair",
                    description=f"'{a.inspection_type}' ({a.inspection_result}) on {a.inspection_date} -> "
                    f"'{b.inspection_type}' ({b.inspection_result}) on {b.inspection_date}{correction_note}. "
                    "Largest gap between consecutive substantive-family inspections observed on this permit.",
                    source_event_ids=[a.event_id, b.event_id],
                    observed_dates=[a.inspection_date, b.inspection_date],
                    matching_method="chronological_consecutive_substantive",
                )
            ],
            cannot_infer=[_RESPONSIBILITY_CANNOT_INFER, _CAUSE_CANNOT_INFER],
            caveats=[],
            based_on_match_status=journey.match_status,
            carried_data_quality_flags=data_quality_flags,
        ),
        None,
    )


def _detect_inactivity_since_last_inspection(
    journey, permit_type, substantive_events, as_of, now, thresholds, data_quality_flags, sample_size
):
    if not substantive_events:
        return None, None
    last = substantive_events[-1]
    elapsed_days = (as_of - last.inspection_date).days

    def fetch(dimensions: dict[str, str], exclude: str) -> list[float]:
        return pop.fetch_inter_inspection_gap_population(
            permit_type=dimensions["permit_type"], exclude_permit_number=exclude, sample_size=sample_size
        )

    tiers = [cohort_lib.CohortTier({"permit_type": permit_type}, 1)]
    cohort, population = cohort_lib.build_cohort_with_fallback(
        tiers, fetch, journey.permit_number,
        CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, now,
    )
    gap = _cohort_gap_message(f"INACTIVITY_SINCE_LAST_INSPECTION for permit_type={permit_type}", cohort)
    if gap:
        return None, gap

    rank = percentile_rank(elapsed_days, population)
    severity = classify_severity(rank, thresholds)
    if severity is None:
        return None, None

    return (
        DelayStallDetection(
            permit_number=journey.permit_number,
            category=StallCategory.INACTIVITY_SINCE_LAST_INSPECTION,
            stage_label=last.inspection_type,
            generated_at=now,
            elapsed_days=elapsed_days,
            as_of=now,
            interval_state=IntervalState.ONGOING,
            status_persistence_confirmed_by_repeated_observation=False,
            cohort=cohort,
            percentile_rank=rank,
            excess_days_vs_median=(
                elapsed_days - cohort.median_days_or_count if cohort.median_days_or_count is not None else None
            ),
            severity=severity,
            evidence=[
                EvidenceRef(
                    kind="inspection_event",
                    description=f"Most recent substantive inspection: '{last.inspection_type}' "
                    f"({last.inspection_result}) on {last.inspection_date}. No further inspection "
                    f"observed as of {as_of}.",
                    source_event_ids=[last.event_id],
                    observed_dates=[last.inspection_date],
                )
            ],
            cannot_infer=[_RESPONSIBILITY_CANNOT_INFER, _CAUSE_CANNOT_INFER],
            caveats=[_ONGOING_CAVEAT, _ONGOING_VS_COMPLETED_COHORT_CAVEAT],
            based_on_match_status=journey.match_status,
            carried_data_quality_flags=data_quality_flags,
        ),
        None,
    )


def _detect_finalization_gap(journey, permit_type, substantive_events, now, thresholds, data_quality_flags, sample_size):
    snapshot = journey.latest_snapshot
    if snapshot.cofo_date is not None:
        track = TerminalTrack.COFO_TRACK
        terminal_date = snapshot.cofo_date
    elif snapshot.status_desc == "Permit Finaled":
        # FINALED_ONLY_TRACK is deliberately not assessed: measured directly
        # against real data (research/AGENT2_DESIGN.md §7), this track's
        # elapsed time is degenerate -- last-substantive-inspection-to-
        # status_date was 0 for every one of 50 real Bldg-Alter/Repair
        # permits sampled (stdev=0.00), consistent with status_date being
        # set the same day as the qualifying final inspection as a matter
        # of LADBS process. There is no discriminatory signal here to
        # measure, so the category is skipped outright for this track
        # rather than relying on the ZERO_VARIANCE_COHORT gate to catch it
        # on every single permit. COFO_TRACK is kept -- it has real,
        # confirmed variance (stdev ~63-68 days in the same measurement).
        return None, (
            "FINALIZATION_GAP not assessed for finaled_only_track: confirmed degenerate "
            "(effectively same-day finalization is normal LADBS behavior for this track, "
            "not a stall) -- see AGENT2_DESIGN.md §7."
        )
    else:
        # exited via Expired/Withdrawn/Revoked/Closed -- explicitly out of
        # scope for FINALIZATION_GAP (§7), not scored on the wrong scale
        return None, (
            f"FINALIZATION_GAP not assessed: permit exited via '{snapshot.status_desc}', which is not "
            "a standard finalization outcome."
        )

    prior = [e for e in substantive_events if terminal_date is None or e.inspection_date <= terminal_date]
    if not prior or terminal_date is None:
        return None, None
    last = prior[-1]
    elapsed_days = (terminal_date - last.inspection_date).days

    def fetch(dimensions: dict[str, str], exclude: str) -> list[float]:
        return pop.fetch_finalization_gap_population(
            permit_type=dimensions["permit_type"], track=dimensions["track"],
            exclude_permit_number=exclude, sample_size=sample_size,
        )

    tiers = [cohort_lib.CohortTier({"permit_type": permit_type, "track": track.value}, 1)]
    cohort, population = cohort_lib.build_cohort_with_fallback(
        tiers, fetch, journey.permit_number,
        CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, now,
    )
    gap = _cohort_gap_message(f"FINALIZATION_GAP for permit_type={permit_type}, track={track.value}", cohort)
    if gap:
        return None, gap

    rank = percentile_rank(elapsed_days, population)
    severity = classify_severity(rank, thresholds)
    if severity is None:
        return None, None

    return (
        DelayStallDetection(
            permit_number=journey.permit_number,
            category=StallCategory.FINALIZATION_GAP,
            stage_label=track.value,
            generated_at=now,
            elapsed_days=elapsed_days,
            as_of=now,
            interval_state=IntervalState.COMPLETED,
            status_persistence_confirmed_by_repeated_observation=False,
            cohort=cohort,
            percentile_rank=rank,
            excess_days_vs_median=(
                elapsed_days - cohort.median_days_or_count if cohort.median_days_or_count is not None else None
            ),
            severity=severity,
            evidence=[
                EvidenceRef(
                    kind="inspection_event",
                    description=f"Last substantive inspection '{last.inspection_type}' ({last.inspection_result}) "
                    f"on {last.inspection_date} -> terminal outcome ({track.value}) on {terminal_date}.",
                    source_event_ids=[last.event_id],
                    observed_dates=[last.inspection_date, terminal_date],
                )
            ],
            cannot_infer=[_RESPONSIBILITY_CANNOT_INFER, _CAUSE_CANNOT_INFER],
            caveats=[],
            based_on_match_status=journey.match_status,
            carried_data_quality_flags=data_quality_flags,
        ),
        None,
    )


# --- Post-issuance: friction ---------------------------------------------


def _detect_friction(
    journey, permit_type, category, fam, substantive_events, as_of, now, thresholds, data_quality_flags, sample_size
):
    snapshot = journey.latest_snapshot
    observed_count = sum(1 for e in journey.inspection_events if result_family(e.inspection_result) == fam)
    total_inspection_opportunities = len(substantive_events)
    lifecycle_stage = (
        LifecycleStage.COMPLETED if snapshot.status_desc in _TERMINAL_STATUSES else LifecycleStage.ONGOING
    )
    observed_lifecycle_days = (
        (as_of - snapshot.issue_date).days if snapshot.issue_date is not None else 0
    )
    meets_minimum_exposure = total_inspection_opportunities >= config.MIN_EXPOSURE_FOR_FRICTION_ASSESSMENT
    meets_minimum_count = observed_count >= config.MIN_FRICTION_COUNT
    rate = observed_count / total_inspection_opportunities if total_inspection_opportunities > 0 else None

    if not meets_minimum_exposure:
        return None, (
            f"{category.value} not assessed: insufficient inspection exposure "
            f"({total_inspection_opportunities} substantive inspection(s) observed so far, "
            f"minimum {config.MIN_EXPOSURE_FOR_FRICTION_ASSESSMENT})."
        )
    if not meets_minimum_count:
        return None, None  # not a coverage gap -- ordinary, unremarkable case

    def fetch(dimensions: dict[str, str], exclude: str) -> list[float]:
        return pop.fetch_friction_count_population(
            permit_type=dimensions["permit_type"], result_family_filter=fam,
            lifecycle_stage=dimensions["lifecycle_stage"], exclude_permit_number=exclude, sample_size=sample_size,
        )

    tiers = [cohort_lib.CohortTier({"permit_type": permit_type, "lifecycle_stage": lifecycle_stage.value}, 1)]
    cohort, population = cohort_lib.build_cohort_with_fallback(
        tiers, fetch, journey.permit_number,
        CohortSource.SOURCE_EVENT_LOG, BenchmarkSemantics.COMPLETED_INTERVAL, now,
    )
    gap = _cohort_gap_message(f"{category.value} for permit_type={permit_type}, lifecycle_stage={lifecycle_stage.value}", cohort)
    if gap:
        return None, gap

    rank = percentile_rank(float(observed_count), population)
    severity = classify_severity(rank, thresholds)
    if severity is None:
        return None, None

    contributing = [e for e in journey.inspection_events if result_family(e.inspection_result) == fam]
    return (
        FrictionStallDetection(
            permit_number=journey.permit_number,
            category=category,
            generated_at=now,
            observed_count=observed_count,
            meets_minimum_count=meets_minimum_count,
            minimum_count_required=config.MIN_FRICTION_COUNT,
            lifecycle_stage=lifecycle_stage,
            total_inspection_opportunities=total_inspection_opportunities,
            observed_lifecycle_days=observed_lifecycle_days,
            correction_rate=rate,
            meets_minimum_exposure=meets_minimum_exposure,
            cohort=cohort,
            percentile_rank=rank,
            excess_count_vs_median=(
                observed_count - cohort.median_days_or_count if cohort.median_days_or_count is not None else None
            ),
            severity=severity,
            evidence=[
                EvidenceRef(
                    kind="event_count",
                    description=f"{observed_count} {fam.value}-family event(s) out of "
                    f"{total_inspection_opportunities} substantive inspection(s) observed.",
                    source_event_ids=[e.event_id for e in contributing],
                    observed_dates=[e.inspection_date for e in contributing],
                )
            ],
            cannot_infer=[
                _RESPONSIBILITY_CANNOT_INFER,
                "Whether these outcomes reflect scheduling/access issues, technical compliance "
                "issues, or something else cannot be determined from the result label alone.",
            ],
            caveats=[],
            based_on_match_status=journey.match_status,
            carried_data_quality_flags=data_quality_flags,
        ),
        None,
    )
