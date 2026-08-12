"""Agent 1 tests against five real, verified permits (see
research/DATASET_VALIDATION.md §9 for how each was selected and confirmed
live before being captured as a fixture) plus one synthetic not-found case.
All offline — no network access."""

from __future__ import annotations

from datetime import date, datetime, timezone

from permit_stall_finder.agents.journey_reconstructor import reconstruct_journey
from permit_stall_finder.schema.journey import DataQualityFlag, MatchStatus

from .conftest import load_fixture_fetchers

OBSERVED_AT = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def test_submitted_but_not_issued(conn):
    """21030-20000-00256: submitted 2020-11-16, PC Approved since
    2021-08-04, still no issue_date years later — a real pre-issuance
    stall candidate."""
    fetch_permit, fetch_inspections = load_fixture_fetchers("unissued")
    journey = reconstruct_journey(
        conn,
        "21030-20000-00256",
        fetch_permit_row=fetch_permit,
        fetch_inspection_rows=fetch_inspections,
        observed_at=OBSERVED_AT,
    )

    assert journey.match_status == MatchStatus.UNISSUED
    assert journey.latest_snapshot.issue_date is None
    assert journey.latest_snapshot.status_desc == "PC Approved"
    assert journey.latest_snapshot.submitted_date == date(2020, 11, 16)
    assert journey.inspection_events == []

    # derived: submission -> current status is known; submission -> issuance is not
    assert journey.derived.days_submitted_to_issuance is None
    assert journey.derived.days_submitted_to_current_status == (
        date(2021, 8, 4) - date(2020, 11, 16)
    ).days

    # first observation -> weak "current status" language only
    assert DataQualityFlag.FIRST_OBSERVATION in journey.data_quality_flags
    assert any("Observed once" in note for note in journey.reconstruction_notes)
    assert not any("continuously remained" in note for note in journey.reconstruction_notes)

    # not itself a stall claim
    assert any("not yet been issued" in note for note in journey.reconstruction_notes)

    # persisted
    assert conn.execute("SELECT count(*) FROM permit_snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM inspection_events").fetchone()[0] == 0


def test_issued_with_no_inspections(conn):
    """18010-20001-05038: a $0-valuation administrative correction permit
    (fixing a legal description) — legitimately has zero inspections, not
    a data gap."""
    fetch_permit, fetch_inspections = load_fixture_fetchers("issued_no_inspections")
    journey = reconstruct_journey(
        conn,
        "18010-20001-05038",
        fetch_permit_row=fetch_permit,
        fetch_inspection_rows=fetch_inspections,
        observed_at=OBSERVED_AT,
    )

    assert journey.match_status == MatchStatus.ISSUED_NO_INSPECTIONS_FOUND
    assert journey.latest_snapshot.issue_date == date(2020, 2, 24)
    assert journey.inspection_events == []

    # rule 4: this is a data state, explicitly not framed as a stall signal
    assert any(
        "not evidence of stalled or inactive work" in note
        for note in journey.reconstruction_notes
    )

    # Bldg-Alter/Repair is not in the uncertain-match-rate type set (only
    # Bldg-New is, per §9b) — the coverage flag must not fire here
    assert journey.latest_snapshot.permit_type == "Bldg-Alter/Repair"
    assert DataQualityFlag.INSPECTION_MATCH_UNCERTAIN_FOR_TYPE not in journey.data_quality_flags

    # issue_date is present, so the inconsistency flag must not fire
    assert DataQualityFlag.STATUS_ISSUE_DATE_INCONSISTENT not in journey.data_quality_flags


def test_issued_with_multiple_inspections(conn):
    """21016-20000-20141: a clean 3-event inspection history."""
    fetch_permit, fetch_inspections = load_fixture_fetchers("issued_multiple_inspections")
    journey = reconstruct_journey(
        conn,
        "21016-20000-20141",
        fetch_permit_row=fetch_permit,
        fetch_inspection_rows=fetch_inspections,
        observed_at=OBSERVED_AT,
    )

    assert journey.match_status == MatchStatus.ISSUED_WITH_INSPECTIONS
    assert len(journey.inspection_events) == 3
    # ordered by inspection_date
    dates = [e.inspection_date for e in journey.inspection_events]
    assert dates == sorted(dates)

    assert journey.derived.days_issuance_to_first_inspection is not None
    assert journey.derived.days_issuance_to_first_inspection >= 0
    assert len(journey.derived.days_between_inspections) == 2

    # every event carries traceable provenance back to its source row
    for event in journey.inspection_events:
        assert event.source_dataset_id == "9w5z-rg2h"
        assert event.event_id  # either a real :id or the deterministic fallback
        assert event.raw  # full raw row retained for audit

    assert conn.execute("SELECT count(*) FROM inspection_events").fetchone()[0] == 3


def test_corrections_followed_by_reinspection(conn):
    """21010-10000-05865: new SFD with 82 inspection events including
    genuine Corrections Issued -> Approved cycles."""
    fetch_permit, fetch_inspections = load_fixture_fetchers("corrections_then_reinspection")
    journey = reconstruct_journey(
        conn,
        "21010-10000-05865",
        fetch_permit_row=fetch_permit,
        fetch_inspection_rows=fetch_inspections,
        observed_at=OBSERVED_AT,
    )

    assert journey.match_status == MatchStatus.ISSUED_WITH_INSPECTIONS
    assert journey.latest_snapshot.permit_type == "Bldg-New"
    results = [e.inspection_result for e in journey.inspection_events]
    assert "Corrections Issued" in results
    assert "Approved" in results
    assert len(journey.inspection_events) == 82
    assert len(journey.derived.days_between_inspections) == 81

    # Bldg-New IS in the uncertain-match-rate set, but that flag only
    # applies when NO inspections were found — this permit has 82, so it
    # must not fire here (the flag is about missing-match uncertainty, not
    # about presence).
    assert DataQualityFlag.INSPECTION_MATCH_UNCERTAIN_FOR_TYPE not in journey.data_quality_flags

    # every event individually traceable
    event_ids = {e.event_id for e in journey.inspection_events}
    assert len(event_ids) == 82  # no dedup collisions


def test_finaled_completed_permit(conn):
    """20010-20000-02739: full lifecycle through CofO Issued, 49 inspection
    events."""
    fetch_permit, fetch_inspections = load_fixture_fetchers("finaled_completed")
    journey = reconstruct_journey(
        conn,
        "20010-20000-02739",
        fetch_permit_row=fetch_permit,
        fetch_inspection_rows=fetch_inspections,
        observed_at=OBSERVED_AT,
    )

    assert journey.match_status == MatchStatus.ISSUED_WITH_INSPECTIONS
    assert journey.latest_snapshot.status_desc == "CofO Issued"
    assert journey.latest_snapshot.cofo_date == date(2023, 3, 14)
    assert len(journey.inspection_events) == 49

    # total observed span covers at least submission through CofO
    assert journey.derived.total_observed_elapsed_days is not None
    assert journey.derived.total_observed_elapsed_days >= (
        date(2023, 3, 14) - date(2020, 8, 13)
    ).days


def test_permit_not_found_is_logged_not_dropped(conn):
    """PRD requirement: unreconstructable permits are logged for review,
    never silently dropped."""

    def fetch_permit_row(permit_number: str):
        return None

    def fetch_inspection_rows(permit_number: str):
        return []

    journey = reconstruct_journey(
        conn,
        "99999-99999-99999",
        fetch_permit_row=fetch_permit_row,
        fetch_inspection_rows=fetch_inspection_rows,
        observed_at=OBSERVED_AT,
    )

    assert journey.match_status == MatchStatus.PERMIT_NOT_FOUND
    assert journey.latest_snapshot is None
    assert journey.derived is None

    logged = conn.execute(
        "SELECT permit_number, issue_type FROM reconstruction_log"
    ).fetchall()
    assert logged == [("99999-99999-99999", "permit_not_found")]
