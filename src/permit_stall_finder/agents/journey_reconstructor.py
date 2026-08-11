"""Agent 1 — Journey Reconstructor.

Fetches a permit's current state and inspection history, persists a dated
snapshot (append-only — see storage/db.py), and assembles a PermitJourney
that describes only what has actually been observed. Never fabricates
pre-issuance transitions that weren't present in a stored snapshot.
"""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb

from permit_stall_finder import config
from permit_stall_finder.ingestion import inspections, permits
from permit_stall_finder.schema.journey import (
    DataQualityFlag,
    DerivedMetrics,
    MatchStatus,
    PermitJourney,
)
from permit_stall_finder.schema.transitions import collapse_snapshots_to_transitions
from permit_stall_finder.storage import snapshots as storage

# status_desc values that clearly describe a post-issuance state. Used only
# to detect the STATUS_ISSUE_DATE_INCONSISTENT data-quality flag (§9c of
# research/DATASET_VALIDATION.md found ~0.03% of unissued rows carry one of
# these) — never used to infer or override issue_date itself.
_POST_ISSUANCE_STATUSES = {
    "Issued",
    "CofO Issued",
    "CofO in Progress",
    "CofO Corrected",
    "Permit Finaled",
    "Permit Closed",
    "Permit Expired",
}


def _compute_derived_metrics(snapshot, inspection_events) -> DerivedMetrics:
    def days(a, b):
        return (b - a).days if a is not None and b is not None else None

    inspection_dates = [e.inspection_date for e in inspection_events]

    days_between = [
        (inspection_dates[i + 1] - inspection_dates[i]).days
        for i in range(len(inspection_dates) - 1)
    ]

    all_known_dates = [
        d
        for d in [
            snapshot.submitted_date,
            snapshot.status_date,
            snapshot.issue_date,
            snapshot.cofo_date,
            *inspection_dates,
        ]
        if d is not None
    ]
    total_elapsed = (
        (max(all_known_dates) - min(all_known_dates)).days if all_known_dates else None
    )

    return DerivedMetrics(
        days_submitted_to_current_status=days(snapshot.submitted_date, snapshot.status_date),
        days_submitted_to_issuance=days(snapshot.submitted_date, snapshot.issue_date),
        days_issuance_to_first_inspection=(
            days(snapshot.issue_date, inspection_dates[0]) if inspection_dates else None
        ),
        days_between_inspections=days_between,
        total_observed_elapsed_days=total_elapsed,
    )


def _data_quality_flags(snapshot, match_status, has_prior_history) -> list[DataQualityFlag]:
    flags = []

    if snapshot.issue_date is None and snapshot.status_desc in _POST_ISSUANCE_STATUSES:
        flags.append(DataQualityFlag.STATUS_ISSUE_DATE_INCONSISTENT)

    if (
        match_status == MatchStatus.ISSUED_NO_INSPECTIONS_FOUND
        and snapshot.permit_type in config.INSPECTION_MATCH_UNCERTAIN_PERMIT_TYPES
    ):
        flags.append(DataQualityFlag.INSPECTION_MATCH_UNCERTAIN_FOR_TYPE)

    if not has_prior_history:
        flags.append(DataQualityFlag.FIRST_OBSERVATION)

    return flags


def reconstruct_journey(
    conn: duckdb.DuckDBPyConnection,
    permit_number: str,
    *,
    fetch_permit_row=permits.fetch_raw_permit_row,
    fetch_inspection_rows=inspections.fetch_raw_inspection_rows,
    observed_at: datetime | None = None,
) -> PermitJourney:
    observed_at = observed_at or datetime.now(timezone.utc)

    provenance = {
        "permit_dataset_id": config.PERMIT_DATASET_ID,
        "inspection_dataset_id": config.INSPECTION_DATASET_ID,
        "normalization_rule": config.NORMALIZATION_RULE_DESCRIPTION,
    }

    raw_permit = fetch_permit_row(permit_number)
    if raw_permit is None:
        storage.log_reconstruction_issue(
            conn,
            permit_number,
            issue_type="permit_not_found",
            detail=f"No row found in {config.PERMIT_DATASET_ID} for permit_nbr='{permit_number}'.",
            observed_at=observed_at,
        )
        return PermitJourney(
            permit_number=permit_number,
            generated_at=observed_at,
            source_provenance=provenance,
            match_status=MatchStatus.PERMIT_NOT_FOUND,
            latest_snapshot=None,
            prior_snapshots=[],
            inspection_events=[],
            derived=None,
            not_observed_notes=[
                f"Permit '{permit_number}' was not found in {config.PERMIT_DATASET_ID}. "
                "No journey could be reconstructed."
            ],
            data_quality_flags=[],
            reconstruction_notes=[
                f"Logged to reconstruction_log as permit_not_found at {observed_at.isoformat()}."
            ],
        )

    new_snapshot = permits.parse_permit_snapshot(raw_permit, observed_at=observed_at)
    storage.persist_permit_snapshot(conn, new_snapshot)

    raw_inspections = fetch_inspection_rows(permit_number)
    parsed_events = [
        inspections.parse_inspection_event(row, permit_number, observed_at=observed_at)
        for row in raw_inspections
    ]
    parsed_events = [e for e in parsed_events if e is not None]
    storage.persist_inspection_events(conn, parsed_events)

    full_history = storage.read_snapshot_history(conn, permit_number)
    latest_snapshot = full_history[-1]
    prior_snapshots = full_history[:-1]
    inspection_events = storage.read_inspection_events(conn, permit_number)

    if latest_snapshot.issue_date is None:
        match_status = MatchStatus.UNISSUED
    elif inspection_events:
        match_status = MatchStatus.ISSUED_WITH_INSPECTIONS
    else:
        match_status = MatchStatus.ISSUED_NO_INSPECTIONS_FOUND

    data_quality_flags = _data_quality_flags(
        latest_snapshot, match_status, has_prior_history=bool(prior_snapshots)
    )
    derived = _compute_derived_metrics(latest_snapshot, inspection_events)

    transitions = collapse_snapshots_to_transitions(full_history)
    current_transition = transitions[-1] if transitions else None

    not_observed_notes = []
    if not prior_snapshots:
        not_observed_notes.append(
            f"This tool observed permit '{permit_number}' for the first time on "
            f"{observed_at.date()}. Any pre-issuance status transitions before that "
            "date are not known and are not represented in this journey — only the "
            "status recorded at first observation is available."
        )
    else:
        earliest = full_history[0]
        not_observed_notes.append(
            f"Status history is known from {earliest.observed_at.date()} onward "
            f"({len(full_history)} observations). Transitions before that date are "
            "not known."
        )

    reconstruction_notes = []
    if current_transition is not None:
        reconstruction_notes.append(current_transition.describe())

    if match_status == MatchStatus.UNISSUED:
        reconstruction_notes.append(
            f"Permit has not yet been issued (no issue_date on record); currently "
            f"in status '{latest_snapshot.status_desc}'."
        )
    elif match_status == MatchStatus.ISSUED_NO_INSPECTIONS_FOUND:
        reconstruction_notes.append(
            "No inspection records were found for this permit. This is a data "
            "state, not evidence of stalled or inactive work — see "
            "data_quality_flags for known coverage variability by permit type."
        )

    if DataQualityFlag.STATUS_ISSUE_DATE_INCONSISTENT in data_quality_flags:
        reconstruction_notes.append(
            f"Data-quality note: status_desc ('{latest_snapshot.status_desc}') "
            "implies issuance/finalization but issue_date is null on the source "
            "record. Both values are reported as-is; neither was inferred or "
            "corrected."
        )

    return PermitJourney(
        permit_number=permit_number,
        generated_at=observed_at,
        source_provenance=provenance,
        match_status=match_status,
        latest_snapshot=latest_snapshot,
        prior_snapshots=prior_snapshots,
        inspection_events=inspection_events,
        derived=derived,
        not_observed_notes=not_observed_notes,
        data_quality_flags=data_quality_flags,
        reconstruction_notes=reconstruction_notes,
    )
