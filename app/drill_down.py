"""Tabbed drill-down section -- shown below the results table once one or
more permits are selected (Phase 10 redesign). One tab per selected
permit, so a user can hold several open at once (e.g. their own permit
plus a neighbor's, or several units on the same job). Each tab repeats
that permit's at-a-glance facts (quick_glance.render(), the same strip
the old single-permit view showed first) and then the map / neutral
top-level read / next-best-action / findings content that view already
had, plus three expandable sections this redesign adds: "Permit Journey"
(reuses permit_journey.py), "Other permits at this address" (a new,
in-app-clickable listing -- clicking one adds it as another open tab
rather than linking off-site, since LADBS has no per-permit deep link),
and "Data Limitations" (reuses coverage_gaps.py, renamed).

No pipeline logic of its own: every PermitAnalysisResult either already
sits in results_cache (from the search that populated the results table)
or gets fetched here as run_pipeline() would have anyway -- the same call
every other entry point into a single permit's detail makes.
"""

from __future__ import annotations

import streamlit as st

import portfolio
from errors import GENERIC_ERROR_MESSAGE, safe_error_message
from i18n import plain_status_desc, t, translate_error_message
from sections import (
    coverage_gaps,
    disclaimer,
    location_map,
    next_best_action,
    permit_journey,
    quick_access,
    quick_glance,
    stall_findings,
    top_level_result,
)
from permit_stall_finder.ingestion.permits import fetch_permits_by_address
from permit_stall_finder.orchestration.pipeline import PermitAnalysisResult, PipelineExecutionError, run_pipeline


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
    with st.expander(t("drill_down_other_permits")):
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


def _render_one(conn, result: PermitAnalysisResult, kb) -> None:
    quick_glance.render(result)
    st.caption(f"{t('permit_caption')} {result.permit_number}")
    quick_access.render_star_toggle(conn, "permit_number", result.permit_number)

    location_map.render(result)
    top_level_result.render(result)
    next_best_action.render(result, kb)
    stall_findings.render(result.stall_assessment, result.developer_explanations, kb)

    with st.expander(t("drill_down_permit_journey")):
        permit_journey.render(result.journey)

    _render_other_permits_at_address(result)

    if result.coverage_gaps or result.data_quality_flags:
        with st.expander(t("drill_down_data_limitations")):
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
                _render_one(conn, cached, kb)
