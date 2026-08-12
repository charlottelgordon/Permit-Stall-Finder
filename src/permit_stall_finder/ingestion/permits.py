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
    # Presentation-only fields -- never read by any Agent 1/2/3 analytical
    # logic, only by app/ section renderers (quick_glance.py, portfolio.py,
    # sections/location_map.py) via PermitSnapshot.raw. Added 2026-08: the
    # UI already read raw.get("primary_address") but this dataset's
    # $select had never included it, so it silently returned None against
    # the live Socrata API (fixtures happened to mask this -- they carry
    # whatever raw dict a test hand-built). primary_address is the
    # dataset's official mailing/site address; lat/lon are its
    # geocoded coordinates (type_lat_lon indicates how they were derived).
    "primary_address",
    "lat",
    "lon",
    "zip_code",
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


ADDRESS_SEARCH_LIMIT = 10
"""Max rows returned by fetch_permits_by_address(). This is a resolver for
a public text input (address may be known, permit number may not) -- it
exists purely to help a user find a permit_number to hand to the normal
pipeline, never to feed a whole address's permits into analysis at once.
A small cap keeps the picker list short and keeps the query cheap; a
genuinely address-wide portfolio scan is a different, unbuilt feature."""


def fetch_permits_by_address(
    address_query: str, base_url: str = config.SOCRATA_BASE_URL, limit: int = ADDRESS_SEARCH_LIMIT
) -> list[dict]:
    """Case-insensitive substring match against primary_address, returning
    raw Socrata rows (same shape fetch_raw_permit_row returns) so a caller
    can list "permit_nbr -- permit_type -- status_desc" choices for a user
    to pick from, then re-fetch that one permit through the normal
    fetch_raw_permit_row() + pipeline path -- this function is only ever a
    resolver, never a substitute for that per-permit fetch.

    address_query is interpolated into the $where clause only after
    socrata.escape_soql_string(), the same rule every other $where-building
    call site in this package follows (see test_permit_query_escaping.py).
    Ordered by status_date desc so the most recently active permits at an
    address surface first among (often many) historical ones."""
    where = (
        f"upper(primary_address) like upper('%{socrata.escape_soql_string(address_query)}%')"
    )
    return socrata.query(
        config.PERMIT_DATASET_ID,
        {
            "$select": socrata.select_with_system_columns(PERMIT_FIELDS),
            "$where": where,
            "$order": "status_date DESC",
            "$limit": str(limit),
        },
        base_url,
    )


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

