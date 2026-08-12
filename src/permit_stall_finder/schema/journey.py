"""The Agent 1 -> Agent 2/3 contract.

Every field on PermitJourney is grouped under OBSERVED, DERIVED, or
NOT_OBSERVED. This grouping is structural, not a naming convention: Agent 1
must never populate an OBSERVED or DERIVED field from a guess, and
NOT_OBSERVED exists specifically to say what we do *not* know rather than
silently omitting it. See research/DATASET_VALIDATION.md sections 4 and 8
for why this distinction matters for these two source datasets.

Every persisted source record (PermitSnapshot, InspectionEvent) carries
source_dataset_id, source_record_id, source_updated_at, and observed_at so
any factual claim in a PermitJourney can be traced back to the exact
LA Open Data row it came from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum


class MatchStatus(str, Enum):
    """Where this permit landed relative to issuance and inspection matching.
    An unissued permit is never scored as a failed inspection join — see
    research/DATASET_VALIDATION.md §9b."""

    UNISSUED = "unissued"
    ISSUED_WITH_INSPECTIONS = "issued_with_inspections"
    ISSUED_NO_INSPECTIONS_FOUND = "issued_no_inspections_found"
    """A data state, not itself evidence of a stall or inactivity. ~30% of
    issued permits in the validation sample showed no inspection match for
    reasons including recency and per-type coverage variance — see
    DataQualityFlag.INSPECTION_MATCH_UNCERTAIN_FOR_TYPE. Agent 2 must not
    treat this status alone as a stall signal."""
    PERMIT_NOT_FOUND = "permit_not_found"


class DataQualityFlag(str, Enum):
    STATUS_ISSUE_DATE_INCONSISTENT = "status_issue_date_inconsistent"
    """status_desc implies issuance/finalization but issue_date is null,
    or vice versa. Observed in ~0.03% of gwh9-jnip's unissued rows."""

    INSPECTION_MATCH_UNCERTAIN_FOR_TYPE = "inspection_match_uncertain_for_type"
    """This permit_type has a historically low/variable forward match rate
    against 9w5z-rg2h (e.g. Bldg-New at ~50%, §9b) — a missing inspection
    match is less informative for these types than for others. This is a
    coverage flag, not a stall signal."""

    FIRST_OBSERVATION = "first_observation"
    """No prior snapshot exists for this permit in our own storage. All
    pre-issuance status history before this observation is NOT_OBSERVED,
    not absent-therefore-nothing-happened."""


@dataclass(frozen=True)
class InspectionEvent:
    """OBSERVED — one row from 9w5z-rg2h, joined by normalized permit number."""

    event_id: str
    """The source dataset's own unique row identifier (Socrata system
    column :id, e.g. "row-789q.jfdb~2vgh") when available. Only if no
    reliable source identifier exists does this fall back to a deterministic
    hash of (source_dataset_id, permit_number, inspection_date,
    inspection_type, inspection_result) — see ingestion/inspections.py."""
    source_dataset_id: str  # "9w5z-rg2h"
    source_record_id: str | None  # Socrata :id, when present
    source_updated_at: datetime | None  # Socrata :updated_at
    observed_at: datetime  # our clock: when we fetched this row

    permit_number: str
    inspection_date: date
    inspection_type: str
    inspection_result: str

    raw: dict
    """Full raw source row (including system columns), for audit/replay."""


@dataclass(frozen=True)
class PermitSnapshot:
    """OBSERVED — one dated pull of a permit's row from gwh9-jnip. This is
    the unit of persistence: every Agent 1 run that fetches a permit writes
    one of these, even if nothing changed since the last pull — repeated
    identical snapshots are meaningful, they establish that a published
    state *persisted* across polling dates (see schema/transitions.py).
    Over time, the sequence of snapshots for a permit_number becomes real
    transition history — but only from the day we started collecting them
    forward."""

    source_dataset_id: str  # "gwh9-jnip"
    source_record_id: str | None  # Socrata :id, when present
    source_updated_at: datetime | None  # Socrata :updated_at
    observed_at: datetime  # our clock: when this snapshot was fetched
    source_refresh_time: date | None  # the dataset's own REFRESH_TIME field

    permit_number: str
    permit_type: str
    permit_sub_type: str | None
    business_unit: str | None  # review pathway, e.g. "Express Permit"
    work_description: str | None

    submitted_date: date | None
    status_desc: str
    status_date: date | None
    issue_date: date | None
    cofo_date: date | None
    valuation: float | None

    raw: dict  # full raw source row, for audit/replay


@dataclass(frozen=True)
class DerivedMetrics:
    """DERIVED — every field here is None unless the OBSERVED dates needed
    to compute it are both present. Never backfilled or estimated."""

    days_submitted_to_current_status: int | None
    days_submitted_to_issuance: int | None
    days_issuance_to_first_inspection: int | None
    days_between_inspections: list[int]  # gaps between consecutive events
    total_observed_elapsed_days: int | None
    """Span between the earliest and latest OBSERVED dates known for this
    permit (submitted_date/status_date/issue_date/cofo_date/inspection
    dates) — not a claim about what happened in between."""


@dataclass(frozen=True)
class PermitJourney:
    """Agent 1's output. Describes an *observable* permit journey — never
    a fabricated or inferred one."""

    permit_number: str
    generated_at: datetime
    source_provenance: dict[str, str]
    """e.g. {"permit_dataset_id": "gwh9-jnip", "inspection_dataset_id":
    "9w5z-rg2h", "normalization_rule": "strip non-alphanumeric, uppercase"}.
    Per-record provenance (which exact source row backs which fact) lives
    on each PermitSnapshot/InspectionEvent — this dict is the dataset-level
    summary."""

    match_status: MatchStatus

    # --- OBSERVED ---
    latest_snapshot: PermitSnapshot | None  # None only if PERMIT_NOT_FOUND
    prior_snapshots: list[PermitSnapshot]  # empty until we've polled >1x
    inspection_events: list[InspectionEvent]  # ordered by inspection_date

    # --- DERIVED ---
    derived: DerivedMetrics | None  # None only if PERMIT_NOT_FOUND

    # --- NOT OBSERVED ---
    not_observed_notes: list[str] = field(default_factory=list)
    """Explicit statements of what is unknown, e.g. "pre-issuance status
    transitions before 2026-08-11 were not observed by this tool; only the
    status as of first observation (PC Approved, 2021-08-04) is known.\""""

    # --- meta ---
    data_quality_flags: list[DataQualityFlag] = field(default_factory=list)
    reconstruction_notes: list[str] = field(default_factory=list)
    """Free-text notes on how this journey was assembled, for the PRD's
    "log unreconstructable permits for review" requirement — populated even
    when match_status is PERMIT_NOT_FOUND."""
