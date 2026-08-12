"""Agent 2 integration tests. Synthetic PermitJourney fixtures + monkeypatched
population-fetch functions (permit_stall_finder.ingestion.cohort_populations)
-- fully offline and deterministic, no network access. Monkeypatching the
population layer (rather than threading an injectable fetcher object through
every detector function, as Agent 1 does for its ingestion calls) was the
pragmatic choice here given the number of call sites; it's a standard,
supported pytest pattern and keeps the detector functions themselves simple.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from permit_stall_finder.agents.stall_detector import assess_stalls
from permit_stall_finder.ingestion import cohort_populations as pop
from permit_stall_finder.schema.journey import (
    DerivedMetrics,
    InspectionEvent,
    MatchStatus,
    PermitJourney,
    PermitSnapshot,
)
from permit_stall_finder.schema.stall_detection import (
    LifecycleStage,
    Severity,
    StallCategory,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)
TODAY = date(2026, 8, 11)


def _snapshot(
    permit_number="TEST-1",
    permit_type="Bldg-Alter/Repair",
    status_desc="PC Approved",
    status_date=date(2025, 1, 1),
    issue_date=None,
    cofo_date=None,
    observed_at=NOW,
    work_description="test",
    valuation=10000.0,
):
    return PermitSnapshot(
        source_dataset_id="gwh9-jnip",
        source_record_id="row-test",
        source_updated_at=None,
        observed_at=observed_at,
        source_refresh_time=TODAY,
        permit_number=permit_number,
        permit_type=permit_type,
        permit_sub_type="1 or 2 Family Dwelling",
        business_unit="Regular Plan Check",
        work_description=work_description,
        submitted_date=date(2024, 1, 1),
        status_desc=status_desc,
        status_date=status_date,
        issue_date=issue_date,
        cofo_date=cofo_date,
        valuation=valuation,
        raw={},
    )


def _event(inspection_date, inspection_result, inspection_type="Final", event_id=None):
    return InspectionEvent(
        event_id=event_id or f"evt-{inspection_date}-{inspection_result}",
        source_dataset_id="9w5z-rg2h",
        source_record_id=None,
        source_updated_at=None,
        observed_at=NOW,
        permit_number="TEST-1",
        inspection_date=inspection_date,
        inspection_type=inspection_type,
        inspection_result=inspection_result,
        raw={},
    )


def _journey(match_status, snapshot, inspection_events=None, prior_snapshots=None):
    return PermitJourney(
        permit_number=snapshot.permit_number if snapshot else "TEST-1",
        generated_at=NOW,
        source_provenance={},
        match_status=match_status,
        latest_snapshot=snapshot,
        prior_snapshots=prior_snapshots or [],
        inspection_events=inspection_events or [],
        derived=DerivedMetrics(None, None, None, [], None) if snapshot else None,
    )


_DEFAULT_POPULATION = [float(i) for i in range(50)]  # n=50 -> FULL confidence, mid-range values


@pytest.fixture(autouse=True)
def _default_populations(monkeypatch):
    """Every category detector Agent 2 attempts for a given journey shape
    calls its own population fetcher -- a test exercising one category
    still exercises whichever others apply to that journey. Default all
    fetchers to a safe, generic large population so unrelated categories
    don't crash the test; individual tests override the fetcher(s) they
    actually care about to get specific, deliberate behavior."""
    monkeypatch.setattr(
        pop, "fetch_pre_issuance_dwell_population",
        lambda status_desc, as_of, permit_type=None, exclude_permit_number=None: list(_DEFAULT_POPULATION),
    )
    monkeypatch.setattr(
        pop, "fetch_issuance_to_first_inspection_population",
        lambda permit_type, exclude_permit_number=None, sample_size=200: list(_DEFAULT_POPULATION),
    )
    monkeypatch.setattr(
        pop, "fetch_inter_inspection_gap_population",
        lambda permit_type, exclude_permit_number=None, sample_size=200: list(_DEFAULT_POPULATION),
    )
    monkeypatch.setattr(
        pop, "fetch_friction_count_population",
        lambda permit_type, result_family_filter, lifecycle_stage, exclude_permit_number=None, sample_size=200: list(
            _DEFAULT_POPULATION
        ),
    )
    monkeypatch.setattr(
        pop, "fetch_finalization_gap_population",
        lambda permit_type, track, exclude_permit_number=None, sample_size=200: list(_DEFAULT_POPULATION),
    )


# --- pre-issuance dwell ---------------------------------------------------


def test_pre_issuance_dwell_severe(monkeypatch):
    monkeypatch.setattr(
        pop, "fetch_pre_issuance_dwell_population",
        lambda status_desc, as_of, permit_type=None, exclude_permit_number=None: [float(i) for i in range(100)],
    )
    snapshot = _snapshot(status_date=date(2020, 1, 1))  # elapsed ~= 2412 days, far above any p95=99
    journey = _journey(MatchStatus.UNISSUED, snapshot)

    assessment = assess_stalls(journey, now=NOW)

    assert len(assessment.detections) == 1
    d = assessment.detections[0]
    assert d.category == StallCategory.PRE_ISSUANCE_STATUS_DWELL
    assert d.severity == Severity.SEVERE
    assert d.percentile_rank == 100.0
    assert d.interval_state.value == "ongoing"
    assert d.status_persistence_confirmed_by_repeated_observation is False
    assert any("length-biased" in c or "currently sitting" in c for c in d.caveats)
    assert any("single occasion" in c for c in d.caveats)
    assert d.cannot_infer  # never empty


def test_pre_issuance_dwell_below_watch_produces_no_detection(monkeypatch):
    monkeypatch.setattr(
        pop, "fetch_pre_issuance_dwell_population",
        lambda status_desc, as_of, permit_type=None, exclude_permit_number=None: [float(i) for i in range(1000)],
    )
    snapshot = _snapshot(status_date=date(2026, 8, 1))  # elapsed = 10 days, near the bottom
    journey = _journey(MatchStatus.UNISSUED, snapshot)

    assessment = assess_stalls(journey, now=NOW)

    assert assessment.detections == []
    assert assessment.coverage_gaps == []  # not a coverage gap -- genuinely unremarkable


def test_pre_issuance_dwell_insufficient_cohort_is_a_coverage_gap(monkeypatch):
    monkeypatch.setattr(
        pop, "fetch_pre_issuance_dwell_population",
        lambda status_desc, as_of, permit_type=None, exclude_permit_number=None: [1.0, 2.0],  # n=2, always insufficient
    )
    snapshot = _snapshot(status_date=date(2020, 1, 1))
    journey = _journey(MatchStatus.UNISSUED, snapshot)

    assessment = assess_stalls(journey, now=NOW)

    assert assessment.detections == []
    assert len(assessment.coverage_gaps) == 1
    assert "insufficient cohort data" in assessment.coverage_gaps[0]


def test_pre_issuance_dwell_status_persistence_confirmed_by_repeated_snapshots(monkeypatch):
    monkeypatch.setattr(
        pop, "fetch_pre_issuance_dwell_population",
        lambda status_desc, as_of, permit_type=None, exclude_permit_number=None: [float(i) for i in range(100)],
    )
    prior = _snapshot(status_date=date(2020, 1, 1), observed_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    latest = _snapshot(status_date=date(2020, 1, 1), observed_at=NOW)
    journey = _journey(MatchStatus.UNISSUED, latest, prior_snapshots=[prior])

    assessment = assess_stalls(journey, now=NOW)

    d = assessment.detections[0]
    assert d.status_persistence_confirmed_by_repeated_observation is True
    assert not any("single occasion" in c for c in d.caveats)


# --- no inspection since issuance -----------------------------------------


def test_no_inspection_since_issuance_eligible_type(monkeypatch):
    monkeypatch.setattr(
        pop, "fetch_issuance_to_first_inspection_population",
        lambda permit_type, exclude_permit_number=None, sample_size=200: [float(i) for i in range(50)],
    )
    snapshot = _snapshot(permit_type="Bldg-Alter/Repair", status_desc="Issued", issue_date=date(2020, 1, 1))
    journey = _journey(MatchStatus.ISSUED_NO_INSPECTIONS_FOUND, snapshot, inspection_events=[])

    assessment = assess_stalls(journey, now=NOW)

    assert len(assessment.detections) == 1
    d = assessment.detections[0]
    assert d.category == StallCategory.NO_INSPECTION_SINCE_ISSUANCE
    assert d.severity == Severity.SEVERE


def test_no_inspection_since_issuance_ineligible_type_is_coverage_gap(monkeypatch):
    # Bldg-New fails the eligibility gate at the default 0.60 threshold --
    # the fetcher must never even be called.
    snapshot = _snapshot(permit_type="Bldg-New", status_desc="Issued", issue_date=date(2020, 1, 1))
    journey = _journey(MatchStatus.ISSUED_NO_INSPECTIONS_FOUND, snapshot, inspection_events=[])

    assessment = assess_stalls(journey, now=NOW)

    no_inspection_detections = [d for d in assessment.detections if d.category == StallCategory.NO_INSPECTION_SINCE_ISSUANCE]
    assert no_inspection_detections == []
    matching_gaps = [g for g in assessment.coverage_gaps if "not assessed for Bldg-New" in g]
    assert len(matching_gaps) == 1
    assert "not currently interpretable as evidence" in matching_gaps[0]


def test_no_inspection_since_issuance_administrative_permit_no_false_positive(monkeypatch):
    """Regression test for the real false positive on 18010-20001-05038:
    a $0-valuation administrative correction permit, Bldg-Alter/Repair
    (which clears the aggregate type-level rate), must not be flagged even
    though the fetcher would happily return a population that ranks it
    SEVERE if it were reached."""
    monkeypatch.setattr(
        pop, "fetch_issuance_to_first_inspection_population",
        lambda permit_type, exclude_permit_number=None, sample_size=200: [float(i) for i in range(50)],
    )
    snapshot = _snapshot(
        permit_type="Bldg-Alter/Repair",
        status_desc="Permit Finaled",
        issue_date=date(2020, 2, 24),
        work_description="SUPPLEMENTAL TO 18010-20000-05038:  TO CORRECT LEGAL DESCRIPTION DUE TO TRACT MAP RECORDATION",
        valuation=0.0,
    )
    journey = _journey(MatchStatus.ISSUED_NO_INSPECTIONS_FOUND, snapshot, inspection_events=[])

    assessment = assess_stalls(journey, now=NOW)

    assert not any(d.category == StallCategory.NO_INSPECTION_SINCE_ISSUANCE for d in assessment.detections)
    assert any(
        "plausibly does not require a physical inspection" in g for g in assessment.coverage_gaps
    )


def test_no_inspection_since_issuance_ambiguous_permit_is_coverage_gap_not_stall(monkeypatch):
    """Only one exemption signal present (zero valuation, no matching
    administrative language) -- must not be treated as either exempt or
    fully eligible."""
    snapshot = _snapshot(
        permit_type="Bldg-Alter/Repair",
        status_desc="Issued",
        issue_date=date(2020, 1, 1),
        work_description="SUPPLEMENTAL PERMIT TO INCREASE BUILDING HEIGHT AND REVISE CEILING HEIGHTS",
        valuation=0.0,
    )
    journey = _journey(MatchStatus.ISSUED_NO_INSPECTIONS_FOUND, snapshot, inspection_events=[])

    assessment = assess_stalls(journey, now=NOW)

    assert not any(d.category == StallCategory.NO_INSPECTION_SINCE_ISSUANCE for d in assessment.detections)
    assert any("Only one exemption signal present" in g for g in assessment.coverage_gaps)


# --- inter-inspection gap --------------------------------------------------


def test_inter_inspection_gap_uses_largest_substantive_gap(monkeypatch):
    monkeypatch.setattr(
        pop, "fetch_inter_inspection_gap_population",
        lambda permit_type, exclude_permit_number=None, sample_size=200: [float(i) for i in range(50)],
    )
    events = [
        _event(date(2021, 1, 1), "Approved", event_id="e1"),
        _event(date(2021, 1, 5), "Corrections Issued", event_id="e2"),  # small gap: 4 days
        _event(date(2021, 6, 1), "Approved", event_id="e3"),  # large gap: 147 days
    ]
    snapshot = _snapshot(status_desc="Issued", issue_date=date(2020, 12, 1))
    journey = _journey(MatchStatus.ISSUED_WITH_INSPECTIONS, snapshot, inspection_events=events)

    assessment = assess_stalls(journey, now=NOW)

    gap_detections = [d for d in assessment.detections if d.category == StallCategory.INTER_INSPECTION_GAP]
    assert len(gap_detections) == 1
    d = gap_detections[0]
    assert d.elapsed_days == 147
    assert d.evidence[0].source_event_ids == ["e2", "e3"]
    assert "corrections issued" in d.evidence[0].description.lower()


def test_scheduled_and_cancelled_events_excluded_from_gap_calculation(monkeypatch):
    """Insp Scheduled / Insp Cancelled are not SUBSTANTIVE -- must not be
    used as gap endpoints."""
    populations_requested = []
    monkeypatch.setattr(
        pop, "fetch_inter_inspection_gap_population",
        lambda permit_type, exclude_permit_number=None, sample_size=200: populations_requested.append(1) or (
            [float(i) for i in range(10)] * 4 + [31.0]  # mostly small gaps; 31 should stand out
        ),
    )
    events = [
        _event(date(2021, 1, 1), "Approved", event_id="e1"),
        _event(date(2021, 1, 2), "Insp Scheduled", event_id="e2"),
        _event(date(2021, 1, 3), "Insp Cancelled", event_id="e3"),
        _event(date(2021, 2, 1), "Approved", event_id="e4"),
    ]
    snapshot = _snapshot(status_desc="Issued", issue_date=date(2020, 12, 1))
    journey = _journey(MatchStatus.ISSUED_WITH_INSPECTIONS, snapshot, inspection_events=events)

    assessment = assess_stalls(journey, now=NOW)

    gap_detections = [d for d in assessment.detections if d.category == StallCategory.INTER_INSPECTION_GAP]
    assert len(gap_detections) == 1
    # gap must be e1 -> e4 (31 days), not e1->e2 or e2->e3
    assert gap_detections[0].evidence[0].source_event_ids == ["e1", "e4"]


# --- friction ---------------------------------------------------------


def test_friction_below_minimum_count_produces_no_detection_and_no_gap():
    events = [_event(date(2021, 1, i), "Approved") for i in range(1, 6)]
    events.append(_event(date(2021, 1, 10), "Corrections Issued"))  # only 1 correction
    snapshot = _snapshot(status_desc="Issued", issue_date=date(2020, 12, 1))
    journey = _journey(MatchStatus.ISSUED_WITH_INSPECTIONS, snapshot, inspection_events=events)

    assessment = assess_stalls(journey, now=NOW)

    corrections = [d for d in assessment.detections if d.category == StallCategory.REPEATED_CORRECTIONS]
    assert corrections == []
    assert not any("REPEATED_CORRECTIONS" in g for g in assessment.coverage_gaps)


def test_friction_below_minimum_exposure_is_a_coverage_gap():
    # 2 corrections (clears MIN_FRICTION_COUNT) but only 2 total substantive
    # events (below MIN_EXPOSURE_FOR_FRICTION_ASSESSMENT=3)
    events = [
        _event(date(2021, 1, 1), "Corrections Issued"),
        _event(date(2021, 1, 5), "Corrections Issued"),
    ]
    snapshot = _snapshot(status_desc="Issued", issue_date=date(2020, 12, 1))
    journey = _journey(MatchStatus.ISSUED_WITH_INSPECTIONS, snapshot, inspection_events=events)

    assessment = assess_stalls(journey, now=NOW)

    assert not any(
        isinstance(d, object) and getattr(d, "category", None) == StallCategory.REPEATED_CORRECTIONS
        for d in assessment.detections
    )
    assert any("insufficient inspection exposure" in g for g in assessment.coverage_gaps)


def test_friction_detected_carries_exposure_and_rate(monkeypatch):
    # Most comparable permits have 0-1 corrections; this permit's 5 should
    # clearly stand out (percentile 100).
    monkeypatch.setattr(
        pop, "fetch_friction_count_population",
        lambda permit_type, result_family_filter, lifecycle_stage, exclude_permit_number=None, sample_size=200: (
            [0.0] * 45 + [1.0] * 5
        ),
    )
    events = [_event(date(2021, 1, i), "Approved") for i in range(1, 6)]
    events += [_event(date(2021, 2, i), "Corrections Issued") for i in range(1, 6)]  # 5 corrections, high count
    snapshot = _snapshot(status_desc="Permit Finaled", issue_date=date(2020, 12, 1))  # lifecycle_stage=completed
    journey = _journey(MatchStatus.ISSUED_WITH_INSPECTIONS, snapshot, inspection_events=events)

    assessment = assess_stalls(journey, now=NOW)

    corrections = [d for d in assessment.detections if d.category == StallCategory.REPEATED_CORRECTIONS]
    assert len(corrections) == 1
    d = corrections[0]
    assert d.observed_count == 5
    assert d.total_inspection_opportunities == 10
    assert d.correction_rate == 0.5
    assert d.lifecycle_stage == LifecycleStage.COMPLETED
    assert d.meets_minimum_count is True
    assert d.meets_minimum_exposure is True


# --- finalization gap -------------------------------------------------


def test_finalization_gap_not_assessed_for_non_terminal_exit():
    """Permit Expired/Withdrawn/Revoked/Closed are excluded from
    FINALIZATION_GAP entirely (§7) -- not scored on the wrong scale."""
    events = [_event(date(2021, 1, 1), "Approved")]
    snapshot = _snapshot(status_desc="Permit Expired", issue_date=date(2020, 12, 1))
    journey = _journey(MatchStatus.ISSUED_WITH_INSPECTIONS, snapshot, inspection_events=events)

    assessment = assess_stalls(journey, now=NOW)

    assert not any(d.category == StallCategory.FINALIZATION_GAP for d in assessment.detections)
    assert any("not a standard finalization outcome" in g for g in assessment.coverage_gaps)


def test_finalization_gap_cofo_track(monkeypatch):
    monkeypatch.setattr(
        pop, "fetch_finalization_gap_population",
        lambda permit_type, track, exclude_permit_number=None, sample_size=200: [float(i) for i in range(50)],
    )
    events = [_event(date(2021, 1, 1), "Approved")]
    snapshot = _snapshot(
        status_desc="CofO Issued", issue_date=date(2020, 12, 1), cofo_date=date(2021, 6, 1)
    )
    journey = _journey(MatchStatus.ISSUED_WITH_INSPECTIONS, snapshot, inspection_events=events)

    assessment = assess_stalls(journey, now=NOW)

    fin = [d for d in assessment.detections if d.category == StallCategory.FINALIZATION_GAP]
    assert len(fin) == 1
    assert fin[0].stage_label == "cofo_track"
    assert fin[0].elapsed_days == (date(2021, 6, 1) - date(2021, 1, 1)).days


def test_finalization_gap_never_assessed_for_finaled_only_track():
    """Regression test: FINALED_ONLY_TRACK is confirmed degenerate on real
    data (research/AGENT2_DESIGN.md §7) and is skipped outright, not just
    caught by the zero-variance gate -- the fetcher must never be called."""
    events = [_event(date(2021, 1, 1), "Approved")]
    snapshot = _snapshot(status_desc="Permit Finaled", issue_date=date(2020, 12, 1), cofo_date=None)
    journey = _journey(MatchStatus.ISSUED_WITH_INSPECTIONS, snapshot, inspection_events=events)

    assessment = assess_stalls(journey, now=NOW)

    assert not any(d.category == StallCategory.FINALIZATION_GAP for d in assessment.detections)
    assert any("finaled_only_track" in g and "confirmed degenerate" in g for g in assessment.coverage_gaps)


# --- not found / unissued edge cases ---------------------------------


def test_permit_not_found_returns_empty_assessment_not_a_crash():
    journey = _journey(MatchStatus.PERMIT_NOT_FOUND, snapshot=None)
    assessment = assess_stalls(journey, now=NOW)
    assert assessment.detections == []
    assert assessment.coverage_gaps == ["Permit not found by Agent 1 -- no stall assessment possible."]
