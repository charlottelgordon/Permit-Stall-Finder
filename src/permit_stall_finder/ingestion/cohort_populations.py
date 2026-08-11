"""Live population-sourcing for Agent 2's cohorts.

Pre-issuance dwell populations are a direct SoQL aggregation over the full
matching population (gwh9-jnip supports filtering on status_desc/
permit_type/issue_date directly). Post-issuance (inspection-gap and
friction) populations require per-permit inspection-history joins that
aren't expressible as a single SoQL query, so they're built from a live-
pulled sample of permits of the relevant type (config.
DEFAULT_COHORT_SAMPLE_SIZE) rather than the full population -- documented
as CohortSource.SOURCE_EVENT_LOG either way, since the underlying data (the
inspections table) is a genuine historical log regardless of sample size.

Every function excludes the target permit from its own population,
implementing AGENT2_DESIGN.md §6d.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

from permit_stall_finder import config
from permit_stall_finder.ingestion import socrata
from permit_stall_finder.ingestion.inspections import _permit_variants
from permit_stall_finder.schema.inspection_vocabulary import (
    SUBSTANTIVE_RESULT_FAMILIES,
    ResultFamily,
    result_family,
)


def fetch_pre_issuance_dwell_population(
    status_desc: str,
    as_of: date,
    permit_type: str | None = None,
    exclude_permit_number: str | None = None,
    base_url: str = config.SOCRATA_BASE_URL,
) -> list[float]:
    """Elapsed days (as_of - status_date) for every currently-unissued
    permit matching status_desc [and permit_type]. This is the
    ACTIVE_PEER_DWELL population -- see AGENT2_DESIGN.md §2b for why it's
    length-biased."""
    where = f"issue_date IS NULL AND status_desc='{_esc(status_desc)}'"
    if permit_type:
        where += f" AND permit_type='{_esc(permit_type)}'"
    if exclude_permit_number:
        where += f" AND permit_nbr != '{_esc(exclude_permit_number)}'"

    rows = _paginated_query(
        config.PERMIT_DATASET_ID,
        {"$select": "status_date", "$where": where},
        base_url,
    )
    out = []
    for r in rows:
        sd = socrata.parse_date(r.get("status_date"))
        if sd is not None:
            out.append(float((as_of - sd).days))
    return out


@dataclass(frozen=True)
class _InspectionLite:
    inspection_date: date
    inspection_result: str


@dataclass(frozen=True)
class _PermitLite:
    permit_nbr: str
    issue_date: date | None
    status_desc: str
    cofo_date: date | None
    inspections: list[_InspectionLite]


def _fetch_issued_permit_sample(
    permit_type: str,
    exclude_permit_number: str | None,
    sample_size: int,
    base_url: str = config.SOCRATA_BASE_URL,
) -> list[_PermitLite]:
    where = f"issue_date IS NOT NULL AND permit_type='{_esc(permit_type)}'"
    if exclude_permit_number:
        where += f" AND permit_nbr != '{_esc(exclude_permit_number)}'"
    rows = socrata.query(
        config.PERMIT_DATASET_ID,
        {
            "$select": "permit_nbr,issue_date,status_desc,cofo_date",
            "$where": where,
            "$limit": str(sample_size),
        },
        base_url,
    )
    permits = {
        r["permit_nbr"]: _PermitLite(
            permit_nbr=r["permit_nbr"],
            issue_date=socrata.parse_date(r.get("issue_date")),
            status_desc=r.get("status_desc", ""),
            cofo_date=socrata.parse_date(r.get("cofo_date")),
            inspections=[],
        )
        for r in rows
        if r.get("permit_nbr")
    }
    if not permits:
        return []

    inspections_by_permit = _bulk_fetch_inspections(list(permits.keys()), base_url)
    result = []
    for permit_nbr, p in permits.items():
        events = sorted(inspections_by_permit.get(permit_nbr, []), key=lambda e: e.inspection_date)
        result.append(
            _PermitLite(
                permit_nbr=p.permit_nbr,
                issue_date=p.issue_date,
                status_desc=p.status_desc,
                cofo_date=p.cofo_date,
                inspections=events,
            )
        )
    return result


def _bulk_fetch_inspections(
    permit_numbers: list[str], base_url: str = config.SOCRATA_BASE_URL
) -> dict[str, list[_InspectionLite]]:
    out: dict[str, list[_InspectionLite]] = defaultdict(list)
    batch_size = 40
    for i in range(0, len(permit_numbers), batch_size):
        chunk = permit_numbers[i : i + batch_size]
        variants = []
        for p in chunk:
            variants.extend(_permit_variants(p))
        quoted = ",".join("'" + v.replace("'", "''") + "'" for v in variants)
        rows = socrata.query(
            config.INSPECTION_DATASET_ID,
            {
                "$select": "permit,inspection_date,inspection_result",
                "$where": f"permit in({quoted})",
                "$limit": "5000",
            },
            base_url,
        )
        norm_to_original = {socrata.normalize_permit(p): p for p in chunk}
        for r in rows:
            raw_permit = r.get("permit", "")
            original = norm_to_original.get(socrata.normalize_permit(raw_permit))
            if original is None:
                continue
            d = socrata.parse_date(r.get("inspection_date"))
            if d is None:
                continue
            out[original].append(
                _InspectionLite(inspection_date=d, inspection_result=r.get("inspection_result", ""))
            )
    return out


def _substantive_events(p: _PermitLite) -> list[_InspectionLite]:
    return [e for e in p.inspections if result_family(e.inspection_result) in SUBSTANTIVE_RESULT_FAMILIES]


def fetch_issuance_to_first_inspection_population(
    permit_type: str,
    exclude_permit_number: str | None = None,
    sample_size: int = config.DEFAULT_COHORT_SAMPLE_SIZE,
) -> list[float]:
    sample = _fetch_issued_permit_sample(permit_type, exclude_permit_number, sample_size)
    out = []
    for p in sample:
        if p.issue_date is None:
            continue
        substantive = _substantive_events(p)
        if substantive:
            out.append(float((substantive[0].inspection_date - p.issue_date).days))
    return out


def fetch_inter_inspection_gap_population(
    permit_type: str,
    exclude_permit_number: str | None = None,
    sample_size: int = config.DEFAULT_COHORT_SAMPLE_SIZE,
) -> list[float]:
    sample = _fetch_issued_permit_sample(permit_type, exclude_permit_number, sample_size)
    out = []
    for p in sample:
        substantive = _substantive_events(p)
        for a, b in zip(substantive, substantive[1:]):
            out.append(float((b.inspection_date - a.inspection_date).days))
    return out


def fetch_friction_count_population(
    permit_type: str,
    result_family_filter: ResultFamily,
    lifecycle_stage: str,  # "completed" | "ongoing"
    exclude_permit_number: str | None = None,
    sample_size: int = config.DEFAULT_COHORT_SAMPLE_SIZE,
) -> list[float]:
    """Counts of result_family_filter-family events per permit, restricted
    to permits in the same lifecycle_stage (§6c.1 -- COMPLETED and ONGOING
    are never pooled)."""
    sample = _fetch_issued_permit_sample(permit_type, exclude_permit_number, sample_size)
    out = []
    for p in sample:
        stage = "completed" if p.status_desc in _TERMINAL_STATUSES or p.cofo_date else "ongoing"
        if stage != lifecycle_stage:
            continue
        count = sum(1 for e in p.inspections if result_family(e.inspection_result) == result_family_filter)
        out.append(float(count))
    return out


def fetch_finalization_gap_population(
    permit_type: str,
    track: str,  # "cofo_track" | "finaled_only_track"
    exclude_permit_number: str | None = None,
    sample_size: int = config.DEFAULT_COHORT_SAMPLE_SIZE,
) -> list[float]:
    sample = _fetch_issued_permit_sample(permit_type, exclude_permit_number, sample_size)
    out = []
    for p in sample:
        terminal_date = None
        if track == "cofo_track" and p.cofo_date is not None:
            terminal_date = p.cofo_date
        elif track == "finaled_only_track" and p.status_desc == "Permit Finaled" and p.cofo_date is None:
            substantive = _substantive_events(p)
            if substantive:
                # no separate "finaled date" field is available; the last
                # substantive inspection date is the best observed anchor
                terminal_date = substantive[-1].inspection_date
        if terminal_date is None:
            continue
        substantive = [e for e in _substantive_events(p) if e.inspection_date <= terminal_date]
        if not substantive:
            continue
        out.append(float((terminal_date - substantive[-1].inspection_date).days))
    return out


_TERMINAL_STATUSES = {
    "Permit Finaled",
    "CofO Issued",
    "CofC Issued",
    "Permit Closed",
    "Permit Expired",
    "Permit Withdrawn",
    "Permit Revoked",
}


def _esc(value: str) -> str:
    return value.replace("'", "''")


def _paginated_query(dataset_id: str, params: dict, base_url: str, page_size: int = 50000) -> list[dict]:
    out = []
    offset = 0
    while True:
        page_params = dict(params)
        page_params["$limit"] = str(page_size)
        page_params["$offset"] = str(offset)
        rows = socrata.query(dataset_id, page_params, base_url)
        out.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return out
