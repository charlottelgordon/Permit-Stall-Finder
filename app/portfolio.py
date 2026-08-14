"""Portfolio triage -- batch analysis across multiple permits, for anyone
who pastes more than one permit number at once (streamlit_app.py decides
single-permit vs. portfolio purely by how many permit numbers came in --
there's no persona gate upstream of this anymore).

Like every other module under app/, this performs no analysis of its own.
Each row is a presentation-layer summary of a PermitAnalysisResult that
orchestration.pipeline.run_pipeline() already produced in full, unchanged
-- run once per permit, exactly the same call the single-permit view
makes. The one piece of logic here, `_max_severity()`, is a plain max()
over Severity values Agent 2 already assigned to that permit's own
detections -- ranking for sort/color order, not a new severity judgment,
the same spirit as formatting.summarize_severity_counts()'s plain count.

run_batch() collects permit numbers from either input path -- typed
number(s) or an address-search selection -- and runs the pipeline once
per permit, worst-first sorted; app/sections/results_table.py and
app/drill_down.py (Phase 10 redesign) do the actual rendering from the
PortfolioRow/PermitAnalysisResult data this module produces, rather than
this module rendering its own table as earlier versions did.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import streamlit as st

from i18n import (
    issuance_status_text,
    outcome_headline,
    plain_status_desc,
    status_updated_phrase,
    summarize_severity_counts_compact,
)
from permit_stall_finder.orchestration.pipeline import (
    AnalysisOutcome,
    PermitAnalysisResult,
    PipelineExecutionError,
    run_pipeline,
)
from permit_stall_finder.schema.stall_detection import Severity

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.SEVERE: 3,
    Severity.ELEVATED: 2,
    Severity.WATCH: 1,
    Severity.UNSCORED: 0,
}

_OUTCOME_RANK: dict[AnalysisOutcome, int] = {
    AnalysisOutcome.STALL_DETECTED: 2,
    AnalysisOutcome.INSUFFICIENT_EVIDENCE: 1,
    AnalysisOutcome.NO_MATERIAL_STALL_DETECTED: 0,
}


def _max_severity(result: PermitAnalysisResult) -> Severity | None:
    """Highest Severity already assigned to any of this permit's
    detections -- a plain max() over Agent 2's own labels. Returns None
    if there are no detections at all (a clean or insufficient-evidence
    read), which is a data state, not "lowest severity"."""
    severities = [d.severity for d in result.stall_assessment.detections]
    if not severities:
        return None
    return max(severities, key=lambda s: _SEVERITY_RANK[s])


def _address(result: PermitAnalysisResult) -> str:
    """Best-effort raw street address, exactly as the source dataset's
    primary_address column carries it -- no city/zip appended. This is the
    form address_of() exposes for the "other permits at this address"
    lookup, which matches against that same raw column
    (permits.fetch_permits_by_address's LIKE '%...%' query); appending
    anything here would break that match. PermitSnapshot (schema/journey.py)
    deliberately carries only permit-process facts, not a normalized
    address field, so this reads primary_address out of the raw source row
    Agent 1 already preserved -- the same pattern formatting.kb_entry_by_id()
    uses to resolve something that already exists in already-fetched data,
    never deriving anything new."""
    snapshot = result.journey.latest_snapshot
    if snapshot is None:
        return "—"
    return snapshot.raw.get("primary_address") or "—"


def _display_address(result: PermitAnalysisResult) -> str:
    """Street address plus city/zip, for on-screen display only (quick
    glance, the downloadable report) -- never for the address-lookup query,
    which needs the bare _address() instead. The source dataset has no
    separate city field (confirmed against its schema); "Los Angeles, CA"
    is appended here as a fixed literal because this tool is scoped to City
    of Los Angeles permits only (see CLAUDE.md scope boundaries), not read
    off any row."""
    street = _address(result)
    if street == "—":
        return street
    snapshot = result.journey.latest_snapshot
    zip_code = snapshot.raw.get("zip_code") if snapshot else None
    city_state = f"Los Angeles, CA {zip_code}".strip() if zip_code else "Los Angeles, CA"
    return f"{street}, {city_state}"


def _has_actionable_step(result: PermitAnalysisResult) -> bool:
    return any(
        exp.developer_actionable_steps for exp in result.developer_explanations.explanations
    )


def address_of(result: PermitAnalysisResult) -> str:
    """Public wrapper around _address() -- drill_down.py needs the same
    best-effort display address (to look up "other permits at this
    address") without reaching into a name-mangled internal helper."""
    return _address(result)


@dataclass(frozen=True)
class PortfolioRow:
    permit_number: str
    address: str
    permit_type: str
    status_desc: str
    outcome: AnalysisOutcome
    headline: str
    top_severity: Severity | None
    severity_counts: str
    days_in_current_status: int | None
    has_actionable_step: bool
    sort_key: tuple
    # --- added for the unified results table (Phase 10 redesign) ---
    submitted_date: date | None = None
    issuance_status: str = "—"
    raw_status_desc: str = "—"
    last_status_update: str = "—"
    status_date: date | None = None
    # Raw day count behind last_status_update's pre-worded string --
    # quick_glance.py's combined "Permit status" block words this
    # itself (a more spelled-out phrasing than the results table's own
    # column), and needs the number, not the already-composed sentence.
    days_since_status_change: int | None = None


def summarize_result(result: PermitAnalysisResult) -> PortfolioRow:
    """Builds one results-table row from an already-complete
    PermitAnalysisResult. Every field is read directly off the result or
    its nested journey/derived metrics -- no recomputation of anything
    Agent 1/2/3 didn't already compute; the only arithmetic done here is
    day-count subtraction against "as of" (analyzed_at, when present), a
    plain re-expression of already-observed dates, not a new judgment."""
    snapshot = result.journey.latest_snapshot
    top_severity = _max_severity(result)
    days = (
        result.journey.derived.days_submitted_to_current_status
        if result.journey.derived is not None
        else None
    )

    as_of = getattr(result, "analyzed_at", None)
    as_of_date = as_of.date() if as_of is not None else date.today()

    submitted_date = snapshot.submitted_date if snapshot else None
    status_date = snapshot.status_date if snapshot else None

    days_since_status_change = (as_of_date - status_date).days if status_date else None
    last_status_update = (
        status_updated_phrase(days_since_status_change) if days_since_status_change is not None else "—"
    )
    issuance_status = issuance_status_text(bool(snapshot and snapshot.issue_date))
    raw_status_desc = snapshot.status_desc if snapshot else "—"

    sort_key = (
        _OUTCOME_RANK[result.outcome],
        _SEVERITY_RANK.get(top_severity, -1) if top_severity is not None else -1,
        days if days is not None else 0,
    )

    return PortfolioRow(
        permit_number=result.permit_number,
        address=_display_address(result),
        permit_type=snapshot.permit_type if snapshot else "—",
        status_desc=plain_status_desc(snapshot.status_desc) if snapshot else "—",
        outcome=result.outcome,
        headline=outcome_headline(result),
        top_severity=top_severity,
        severity_counts=summarize_severity_counts_compact(result.stall_assessment.detections),
        days_in_current_status=days,
        has_actionable_step=_has_actionable_step(result),
        sort_key=sort_key,
        submitted_date=submitted_date,
        issuance_status=issuance_status,
        raw_status_desc=raw_status_desc,
        last_status_update=last_status_update,
        status_date=status_date,
        days_since_status_change=days_since_status_change,
    )


def sort_rows(rows: list[PortfolioRow]) -> list[PortfolioRow]:
    """Worst-first: STALL_DETECTED before INSUFFICIENT_EVIDENCE before
    NO_MATERIAL_STALL_DETECTED, then by highest already-assigned severity,
    then by days in current status. Three tiers of already-computed
    labels, sorted -- never a new judgment about which permit is "worse"
    than Agent 2 didn't already imply via its own severity assignment."""
    return sorted(rows, key=lambda r: r.sort_key, reverse=True)


def parse_permit_numbers(raw_text: str) -> list[str]:
    """Splits on newlines and commas, strips whitespace, drops blanks and
    exact duplicates while preserving first-seen order. Pure text parsing
    only -- permit-number validity is still checked per-permit by the same
    pipeline call the single-permit view uses (a not-found permit is a
    valid INSUFFICIENT_EVIDENCE result, not rejected here)."""
    seen: set[str] = set()
    cleaned_numbers: list[str] = []
    for chunk in raw_text.replace(",", "\n").splitlines():
        cleaned = chunk.strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            cleaned_numbers.append(cleaned)
    return cleaned_numbers


@dataclass(frozen=True)
class BatchResult:
    rows: list[PortfolioRow]
    results_by_permit: dict[str, PermitAnalysisResult]
    errors: list[tuple[str, str]]  # (permit_number, error message)


def run_batch(
    conn, permit_numbers: list[str], *, sample_size: int, progress: bool = True
) -> BatchResult:
    """Runs run_pipeline() once per permit number -- the exact same call
    the single-permit view makes -- and summarizes each success into a
    worst-first-sorted PortfolioRow. No Streamlit input widgets here, so
    this is directly unit-testable and callable from any entry point that
    has already collected a list of permit numbers (typed input, an
    address-search selection, or anything else)."""
    rows: list[PortfolioRow] = []
    results_by_permit: dict[str, PermitAnalysisResult] = {}
    errors: list[tuple[str, str]] = []

    progress_bar = st.progress(0.0) if progress else None
    for i, permit_number in enumerate(permit_numbers):
        try:
            result = run_pipeline(conn, permit_number, sample_size=sample_size)
            rows.append(summarize_result(result))
            results_by_permit[permit_number] = result
        except PipelineExecutionError as exc:
            errors.append((permit_number, str(exc)))
        if progress_bar is not None:
            progress_bar.progress((i + 1) / len(permit_numbers))
    if progress_bar is not None:
        progress_bar.empty()

    return BatchResult(
        rows=sort_rows(rows), results_by_permit=results_by_permit, errors=errors
    )


