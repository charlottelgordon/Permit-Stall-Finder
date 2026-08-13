"""Tabbed drill-down section -- shown below the results table once one or
more permits are selected (Phase 10 redesign; two-panel layout added in
Phase 11). One tab per selected permit, so a user can hold several open
at once (e.g. their own permit plus a neighbor's, or several units on the
same job). Each tab opens with a blue banner summarizing this permit's
stall findings by severity count, then splits into two panels: a left
panel with the permit's at-a-glance facts (quick_glance.render()) and its
map, and a right panel -- collapsed by default -- holding everything a
developer would open to actually understand and act on those findings:
next-best-action, the finding detail cards, "Permit Journey"
(permit_journey.py), "Other permits at this address" (a new,
in-app-clickable listing -- clicking one adds it as another open tab
rather than linking off-site, since LADBS has no per-permit deep link),
and "Data Limitations" (coverage_gaps.py, renamed). The informational
disclaimer stays outside that collapsed panel, always visible, per
UI_DESIGN.md decision 4 ("never inside an expander").

No pipeline logic of its own: every PermitAnalysisResult either already
sits in results_cache (from the search that populated the results table)
or gets fetched here as run_pipeline() would have anyway -- the same call
every other entry point into a single permit's detail makes.
"""

from __future__ import annotations

import streamlit as st

import portfolio
from errors import GENERIC_ERROR_MESSAGE, safe_error_message
from formatting import summarize_severity_counts
from i18n import plain_status_desc, t, translate_error_message
from sections import (
    coverage_gaps,
    disclaimer,
    location_map,
    next_best_action,
    permit_journey,
    quick_glance,
    stall_findings,
)
from permit_stall_finder.ingestion.permits import fetch_permits_by_address
from permit_stall_finder.orchestration.pipeline import (
    AnalysisOutcome,
    PermitAnalysisResult,
    PipelineExecutionError,
    run_pipeline,
)

_OUTCOME_ICONS = {
    AnalysisOutcome.NO_MATERIAL_STALL_DETECTED: "✅",
    AnalysisOutcome.INSUFFICIENT_EVIDENCE: "🔍",
    AnalysisOutcome.STALL_DETECTED: "📋",
}


def _ensure_cached(conn, permit_number: str, results_cache: dict) -> None:
    """Runs the pipeline for permit_number if it isn't already in
    results_cache -- e.g. one just added via an "Other permits at this
    address" click, which only ever had a raw address-search row, never a
    full PermitAnalysisResult. Stores either the result or a caught
    PipelineExecutionError's safe message, mirroring how streamlit_app.py
    already handles a failed single-permit run."""
    if permit_number in results_cache:
        return
    try:
        with st.spinner(t("spinner_analyzing")):
            results_cache[permit_number] = run_pipeline(conn, permit_number)
    except PipelineExecutionError as exc:
        results_cache[permit_number] = safe_error_message(exc)


def _render_other_permits_at_address(result: PermitAnalysisResult) -> None:
    address = portfolio.address_of(result)
    st.markdown(f"**{t('drill_down_other_permits')}**")
    if address == "—":
        st.caption(t("no_other_permits_found"))
        return
    try:
        matches = fetch_permits_by_address(address)
    except Exception:
        st.caption(t("no_other_permits_found"))
        return

    others = [
        row
        for row in matches
        if row.get("permit_nbr") and row.get("permit_nbr") != result.permit_number
    ]
    if not others:
        st.caption(t("no_other_permits_found"))
        return

    for row in others:
        permit_nbr = row["permit_nbr"]
        permit_type = row.get("permit_type") or "—"
        status_desc = plain_status_desc(row.get("status_desc")) if row.get("status_desc") else "—"
        label_col, action_col = st.columns([4, 1])
        label_col.write(f"**{permit_nbr}** — {permit_type} — {status_desc}")
        # "Hyperlinked" per the redesign spec means in-app clickable,
        # not an external URL -- LADBS has no per-permit deep link
        # (flagged and confirmed during scoping). Clicking adds the
        # permit to the open tab set rather than navigating away.
        if action_col.button(t("open_permit_tab_button"), key=f"open_other_{result.permit_number}_{permit_nbr}"):
            extras = st.session_state.setdefault("extra_drilldown_permits", [])
            if permit_nbr not in extras:
                extras.append(permit_nbr)
            st.rerun()


def _render_findings_banner(result: PermitAnalysisResult) -> None:
    """Blue banner (Phase 11 redesign) -- the tab's single top-level
    read, e.g. "3 severe findings · 1 watch finding". Replaces the
    earlier neutral top_level_result.py banner: same underlying text
    (summarize_severity_counts() falls back to the clean/insufficient-
    evidence headline when there are no detections), just always in the
    blue st.info() treatment, plus a line explaining what a "finding"
    is, since this is now the first thing a user sees in the tab."""
    icon = _OUTCOME_ICONS[result.outcome]
    headline = summarize_severity_counts(result.stall_assessment.detections)
    st.info(f"{icon}  **{headline}**")
    st.caption(t("stall_findings_banner_subtext"))


def _render_one(result: PermitAnalysisResult, kb) -> None:
    _render_findings_banner(result)

    left_col, right_col = st.columns([2, 3])
    with left_col:
        quick_glance.render(result)
        location_map.render(result)

    with right_col:
        with st.expander(t("drill_down_more_detail_header"), expanded=False):
            next_best_action.render(result, kb)
            st.divider()
            stall_findings.render(result.stall_assessment, result.developer_explanations, kb)
            st.divider()
            permit_journey.render(result.journey)
            st.divider()
            _render_other_permits_at_address(result)

            if result.coverage_gaps or result.data_quality_flags:
                st.divider()
                coverage_gaps.render(result.coverage_gaps, result.data_quality_flags)

    disclaimer.render(result.developer_explanations.disclaimer)


def render(conn, permit_numbers: list[str], results_cache: dict, kb) -> None:
    """One tab per permit_number (order preserved, duplicates dropped).
    Ensures each has a cached result (or a cached error message) before
    rendering, running the pipeline on demand for any permit_numbers not
    already in results_cache."""
    ordered_unique: list[str] = []
    seen = set()
    for permit_number in permit_numbers:
        if permit_number not in seen:
            seen.add(permit_number)
            ordered_unique.append(permit_number)

    if not ordered_unique:
        return

    for permit_number in ordered_unique:
        _ensure_cached(conn, permit_number, results_cache)

    st.subheader(t("drill_down_header"))
    tabs = st.tabs(ordered_unique)
    for tab, permit_number in zip(tabs, ordered_unique):
        with tab:
            cached = results_cache.get(permit_number)
            if isinstance(cached, str):
                st.error(translate_error_message(cached))
            elif cached is None:
                st.error(translate_error_message(GENERIC_ERROR_MESSAGE))
            else:
                _render_one(cached, kb)
