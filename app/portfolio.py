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

run_batch() and render_table() are split apart (rather than one monolithic
render()) so streamlit_app.py can collect permit numbers from either input
path -- a pasted list or an address-search selection -- and feed either
into the same batch-run-and-display logic.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st

from formatting import SEVERITY_COLORS
from i18n import outcome_headline, plain_status_desc, severity_label, t
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
    """Best-effort display address. PermitSnapshot (schema/journey.py)
    deliberately carries only permit-process facts, not a normalized
    address field. This reads primary_address out of the raw source row
    Agent 1 already preserved for exactly this kind of presentation-only
    lookup -- the same pattern formatting.kb_entry_by_id() uses to resolve
    something that already exists in already-fetched data, never deriving
    anything new."""
    snapshot = result.journey.latest_snapshot
    if snapshot is None:
        return "—"
    return snapshot.raw.get("primary_address") or "—"


def _has_actionable_step(result: PermitAnalysisResult) -> bool:
    return any(
        exp.developer_actionable_steps for exp in result.developer_explanations.explanations
    )


@dataclass(frozen=True)
class PortfolioRow:
    permit_number: str
    address: str
    permit_type: str
    status_desc: str
    outcome: AnalysisOutcome
    headline: str
    top_severity: Severity | None
    days_in_current_status: int | None
    has_actionable_step: bool
    sort_key: tuple


def summarize_result(result: PermitAnalysisResult) -> PortfolioRow:
    """Builds one portfolio-table row from an already-complete
    PermitAnalysisResult. Every field is read directly off the result or
    its nested journey/derived metrics -- no recomputation of anything
    Agent 1/2/3 didn't already compute."""
    snapshot = result.journey.latest_snapshot
    top_severity = _max_severity(result)
    days = (
        result.journey.derived.days_submitted_to_current_status
        if result.journey.derived is not None
        else None
    )

    sort_key = (
        _OUTCOME_RANK[result.outcome],
        _SEVERITY_RANK.get(top_severity, -1) if top_severity is not None else -1,
        days if days is not None else 0,
    )

    return PortfolioRow(
        permit_number=result.permit_number,
        address=_address(result),
        permit_type=snapshot.permit_type if snapshot else "—",
        status_desc=plain_status_desc(snapshot.status_desc) if snapshot else "—",
        outcome=result.outcome,
        headline=outcome_headline(result),
        top_severity=top_severity,
        days_in_current_status=days,
        has_actionable_step=_has_actionable_step(result),
        sort_key=sort_key,
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


def render_table(rows: list[PortfolioRow]) -> None:
    """Pure rendering of an already-computed, already-sorted row list --
    no pipeline calls, no session_state writes. The permit-detail
    selectbox (key="selected_permit") lives here because it's part of the
    same at-a-glance table, but which result loads into the detail view
    below is decided by streamlit_app.py, not this function."""
    st.subheader(t("portfolio_triage_header"))
    st.caption(f"{len(rows)} {t('portfolio_worst_first')}")

    table_data = [
        {
            t("qg_permit"): r.permit_number,
            t("qg_address"): r.address,
            t("qg_type"): r.permit_type,
            t("qg_status"): r.status_desc,
            t("portfolio_severity_col"): severity_label(r.top_severity) if r.top_severity else "—",
            t("qg_result"): r.headline,
            t("qg_days_in_status"): r.days_in_current_status if r.days_in_current_status is not None else "—",
            t("portfolio_dev_action_col"): t("yes") if r.has_actionable_step else "—",
        }
        for r in rows
    ]
    st.dataframe(table_data, hide_index=True, width="stretch")

    options = [r.permit_number for r in rows]
    st.selectbox(t("portfolio_view_detail_for"), options, key="selected_permit")


_OUTCOME_ICONS: dict[AnalysisOutcome, str] = {
    AnalysisOutcome.NO_MATERIAL_STALL_DETECTED: "✅",
    AnalysisOutcome.INSUFFICIENT_EVIDENCE: "🔍",
    AnalysisOutcome.STALL_DETECTED: "📋",
}


def render_two_panel(rows: list[PortfolioRow]) -> None:
    """Side-by-side comparison cards for the common two-permit case --
    e.g. comparing your own permit against a neighbor's, or tracking two
    active projects at once. streamlit_app.py calls this instead of
    render_table() only when exactly two permit numbers were entered;
    three or more still go to the table, which scales better past two
    items. Every field here is the same already-computed PortfolioRow
    data render_table() uses -- this is a different layout, not a
    different computation.

    'View full detail' sets the same session_state['selected_permit']
    key render_table()'s selectbox sets, so streamlit_app.py's existing
    'load the selected permit's cached result' logic below doesn't need
    to know which of the two layouts produced the selection."""
    st.subheader(t("two_panel_header"))
    cols = st.columns(2)
    for col, row in zip(cols, rows):
        with col:
            with st.container(border=True):
                st.markdown(f"**{row.permit_number}**")
                st.caption(f"{row.address} · {row.permit_type}")
                st.markdown(f"**{t('qg_status')}:** {row.status_desc}")
                if row.days_in_current_status is not None:
                    st.caption(f"{t('qg_days_in_status')}: {row.days_in_current_status} {t('days_suffix')}")

                if row.top_severity is not None:
                    color = SEVERITY_COLORS[row.top_severity]
                    badge = (
                        f'<span style="background-color:{color};color:white;padding:2px 10px;'
                        f'border-radius:4px;font-weight:600">{severity_label(row.top_severity)}</span>'
                    )
                    st.markdown(badge, unsafe_allow_html=True)
                    st.caption(row.headline)
                else:
                    icon = _OUTCOME_ICONS[row.outcome]
                    st.markdown(f"{icon} {row.headline}")

                if st.button(t("view_full_detail"), key=f"two_panel_detail_{row.permit_number}"):
                    st.session_state["selected_permit"] = row.permit_number
                    st.rerun()

