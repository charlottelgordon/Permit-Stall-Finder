"""Fetch inspection events for a permit from 9w5z-rg2h.

The inspections dataset mixes dash- and space-separated permit number
formats within the same column (research/DATASET_VALIDATION.md §3), so we
query for both variants of the normalized permit number explicitly rather
than relying on a single format guess."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from permit_stall_finder import config
from permit_stall_finder.ingestion import socrata
from permit_stall_finder.schema.journey import InspectionEvent

INSPECTION_FIELDS = ["permit", "inspection_date", "inspection", "inspection_result"]


def _permit_variants(permit_number: str) -> list[str]:
    dash_form = permit_number
    space_form = permit_number.replace("-", " ")
    return sorted({dash_form, space_form})


def fetch_raw_inspection_rows(
    permit_number: str, base_url: str = config.SOCRATA_BASE_URL
) -> list[dict]:
    variants = _permit_variants(permit_number)
    quoted = ",".join("'" + v.replace("'", "''") + "'" for v in variants)
    rows = socrata.query(
        config.INSPECTION_DATASET_ID,
        {
            "$select": socrata.select_with_system_columns(INSPECTION_FIELDS),
            "$where": f"permit in({quoted})",
            "$order": "inspection_date",
            "$limit": "5000",
        },
        base_url,
    )
    return rows


def _deterministic_event_id(raw: dict, permit_number: str) -> str:
    """Fallback only — used if the source row lacks a :id system column.
    Deterministic over the fields that define a distinct inspection event,
    so re-fetching the same event always yields the same id."""
    basis = "|".join(
        [
            config.INSPECTION_DATASET_ID,
            permit_number,
            str(raw.get("inspection_date", "")),
            str(raw.get("inspection", "")),
            str(raw.get("inspection_result", "")),
        ]
    )
    return "hash:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def parse_inspection_event(
    raw: dict, permit_number: str, observed_at: datetime | None = None
) -> InspectionEvent | None:
    observed_at = observed_at or datetime.now(timezone.utc)
    inspection_date = socrata.parse_date(raw.get("inspection_date"))
    if inspection_date is None:
        return None  # not a usable event without a date

    source_record_id = raw.get(":id")
    event_id = source_record_id or _deterministic_event_id(raw, permit_number)

    return InspectionEvent(
        event_id=event_id,
        source_dataset_id=config.INSPECTION_DATASET_ID,
        source_record_id=source_record_id,
        source_updated_at=socrata.parse_datetime(raw.get(":updated_at")),
        observed_at=observed_at,
        permit_number=permit_number,
        inspection_date=inspection_date,
        inspection_type=raw.get("inspection", ""),
        inspection_result=raw.get("inspection_result", ""),
        raw=raw,
    )
