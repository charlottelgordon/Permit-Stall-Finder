"""Fetch a single permit's current row from the canonical permit dataset
(gwh9-jnip) and parse it into a PermitSnapshot."""

from __future__ import annotations

from datetime import datetime, timezone

from permit_stall_finder import config
from permit_stall_finder.ingestion import socrata
from permit_stall_finder.schema.journey import PermitSnapshot

PERMIT_FIELDS = [
    "permit_nbr",
    "permit_type",
    "permit_sub_type",
    "business_unit",
    "work_desc",
    "submitted_date",
    "status_desc",
    "status_date",
    "issue_date",
    "cofo_date",
    "valuation",
    "refresh_time",
]


def fetch_raw_permit_row(
    permit_number: str, base_url: str = config.SOCRATA_BASE_URL
) -> dict | None:
    """Returns the raw Socrata row (including system columns), or None if
    the permit number does not exist in the source dataset."""
    rows = socrata.query(
        config.PERMIT_DATASET_ID,
        {
            "$select": socrata.select_with_system_columns(PERMIT_FIELDS),
            "$where": f"permit_nbr='{socrata.escape_soql_string(permit_number)}'",
            "$limit": "1",
        },
        base_url,
    )
    return rows[0] if rows else None


def parse_permit_snapshot(raw: dict, observed_at: datetime | None = None) -> PermitSnapshot:
    observed_at = observed_at or datetime.now(timezone.utc)
    valuation_raw = raw.get("valuation")
    return PermitSnapshot(
        source_dataset_id=config.PERMIT_DATASET_ID,
        source_record_id=raw.get(":id"),
        source_updated_at=socrata.parse_datetime(raw.get(":updated_at")),
        observed_at=observed_at,
        source_refresh_time=socrata.parse_date(raw.get("refresh_time")),
        permit_number=raw.get("permit_nbr", ""),
        permit_type=raw.get("permit_type", ""),
        permit_sub_type=raw.get("permit_sub_type"),
        business_unit=raw.get("business_unit"),
        work_description=raw.get("work_desc"),
        submitted_date=socrata.parse_date(raw.get("submitted_date")),
        status_desc=raw.get("status_desc", ""),
        status_date=socrata.parse_date(raw.get("status_date")),
        issue_date=socrata.parse_date(raw.get("issue_date")),
        cofo_date=socrata.parse_date(raw.get("cofo_date")),
        valuation=float(valuation_raw) if valuation_raw not in (None, "") else None,
        raw=raw,
    )
