"""Permit Check LA -- Streamlit MVP entrypoint.

Thin presentation layer over orchestration.pipeline.run_pipeline(). This
file and everything under app/ contain no analytical logic: no severity
computation, no cohort math, no knowledge-base matching, no explanation
text. Every fact rendered here already exists on the PermitAnalysisResult
returned by the orchestrator -- see research/UI_DESIGN.md for the original
design and the constraints each section renderer follows.

Phase 10 redesign: a single search bar (search_input.py decides whether
what was typed looks like permit number(s) or an address) replaces the
earlier two-tab layout, and every search -- one permit or many -- lands
in the same unified results table (sections/results_table.py) instead of
branching between a portfolio table and a two-panel comparison layout.
Clicking a row (or, for a single-permit search, landing directly) opens
that permit as a tab in the drill-down section below (drill_down.py);
picking an "other permit at this address" from inside a drill-down tab
opens it as another tab the same way, rather than navigating away.

Recent searches are still recorded to storage/user_state.py on every
successful search (a return user checking the same permit(s) or address
every day for their job), even though nothing in the UI currently reads
that history back -- kept for a possible future quick-access affordance.
"Clear results" resets the search state and re-runs the script.
"""

from __future__ import annotations

import base64
import html
from pathlib import Path

import streamlit as st

import drill_down
import portfolio
import search_input
from db import get_connection, get_knowledge_base
from i18n import (
    APP_NAME,
    render_language_toggle,
    t,
    translate_error_message,
)
from errors import GENERIC_ERROR_MESSAGE, validate_permit_number
from sections import report_export, results_table

from permit_stall_finder import config
from permit_stall_finder.ingestion.permits import fetch_permits_by_address
from permit_stall_finder.storage import user_state

st.set_page_config(page_title=APP_NAME, page_icon="🏗️", layout="wide")

# A real, solid-color header bar carrying the app's own logo just below it
# (rendered further down), rather than the earlier gradient bar's ::after
# pseudo-element title -- that text was never a real heading for assistive
# tech. This CSS only recolors Streamlit's own header chrome and removes
# its default toolbar icons.
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Poppins', sans-serif;
    }
    h1, h2, h3, h4, h5, h6,
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3 {
        font-family: 'Poppins', sans-serif;
        font-weight: 700;
    }
    [data-testid="stHeader"] {
        background-color: #F5760A !important;
        height: 5.5rem !important;
    }
    [data-testid="stToolbar"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"] {
        display: none;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 10px;
    }
    div.block-container {
        padding-top: 1.5rem !important;
    }
    .app-header-bar {
        display: flex;
        align-items: center;
        justify-content: center;
        /* Exactly the header bar's own height (see [data-testid="stHeader"]
           above), with a margin-top of the same magnitude -- normal flow
           would place this row right after the header, at
           document-y = header height; a margin-top equal to that height
           cancels it out exactly, so this box starts at y=0 and spans the
           header's full height 1:1. That's what makes align-items: center
           (for the logo) and the link's own top: 50% (below) land on the
           header's true vertical center, not an approximation. */
        height: 5.5rem;
        margin-top: -2.5rem;
        margin-bottom: 1.75rem;
        padding: 0 1rem;
        /* Streamlit's own header bar (stHeader) is position: fixed with
           z-index 999990, so without this the row renders underneath
           it -- present in the DOM but visually invisible, since the
           negative margin above pulls it up into that same fixed strip. */
        position: relative;
        z-index: 999991;
    }
    .app-header-bar [role="heading"] {
        display: flex;
        align-items: center;
        margin: 0;
    }
    .app-header-bar img {
        height: 4rem;
        width: auto;
        display: block;
    }
    .site-welcome-intro {
        text-align: center;
        max-width: 640px;
        margin: 0.5rem auto 1.5rem auto;
        color: #444;
    }
    .search-loading-track {
        width: 100%;
        height: 6px;
        border-radius: 3px;
        background: #E4E9F2;
        overflow: hidden;
        margin: 0.5rem 0 1rem 0;
    }
    .search-loading-bar {
        height: 100%;
        width: 40%;
        border-radius: 3px;
        background: linear-gradient(90deg, #99AFD7, #052D49, #E08A3C, #99AFD7);
        background-size: 300% 100%;
        animation: search-loading-slide 1.1s ease-in-out infinite,
            search-loading-color 2s linear infinite;
    }
    @keyframes search-loading-slide {
        0% { margin-left: -40%; }
        100% { margin-left: 100%; }
    }
    @keyframes search-loading-color {
        0% { background-position: 0% 50%; }
        100% { background-position: 100% 50%; }
    }
    .search-tooltip-wrap {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        height: 2.6rem;
    }
    .search-tooltip-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 1.5rem;
        height: 1.5rem;
        border-radius: 50%;
        border: 1.5px solid #052D49;
        color: #052D49;
        font-size: 0.85rem;
        font-weight: 700;
        cursor: help;
        user-select: none;
    }
    .search-tooltip-content {
        visibility: hidden;
        opacity: 0;
        position: absolute;
        top: 100%;
        right: 0;
        margin-top: 0.5rem;
        width: 320px;
        max-width: 80vw;
        background: #052D49;
        color: #FFFFFF;
        padding: 0.75rem 1rem;
        border-radius: 8px;
        font-size: 0.85rem;
        line-height: 1.45;
        text-align: left;
        z-index: 9999;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.18);
        transition: opacity 0.15s ease-in-out;
        pointer-events: none;
    }
    .search-tooltip-content p {
        margin: 0 0 0.6rem 0;
    }
    .search-tooltip-content p:last-child {
        margin-bottom: 0;
    }
    .search-tooltip-wrap:hover .search-tooltip-content {
        visibility: visible;
        opacity: 1;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# The header bar itself: just the logo, centered (a div with
# role="heading" aria-level="1" rather than a real <h1> -- Streamlit
# auto-wraps every actual h1-h6 it finds in rendered markdown with its
# own hover "anchor link" chrome, which comes with padding that broke
# this row's vertical centering math and can't be fully overridden; an
# ARIA heading gets assistive tech the same "level-1 heading, announced
# via the image's alt text" treatment without Streamlit's own
# instrumentation). Sits inside the colored bar itself (not a separate
# row below it), so the logo doesn't cost its own line of vertical space.
_logo_b64 = base64.b64encode((Path(__file__).parent / "assets" / "logo.png").read_bytes()).decode()
st.markdown(
    '<div class="app-header-bar">'
    f'<div role="heading" aria-level="1"><img src="data:image/png;base64,{_logo_b64}" alt="{APP_NAME}"></div>'
    "</div>",
    unsafe_allow_html=True,
)

# --- Session state defaults --------------------------------------------
if "table_rows" not in st.session_state:
    st.session_state.table_rows = None
if "results_cache" not in st.session_state:
    st.session_state.results_cache = {}
if "drilldown_permits" not in st.session_state:
    st.session_state.drilldown_permits = []
if "extra_drilldown_permits" not in st.session_state:
    st.session_state.extra_drilldown_permits = []
if "error" not in st.session_state:
    st.session_state.error = None

# One-shot flag from a "Clear results" click (see below): must run
# *before* st.text_input(key="unified_search_input") is instantiated
# further down, since Streamlit disallows writing to a widget's
# session_state key once that widget has already rendered this run --
# the button that sets this flag is itself rendered after the text
# input, so the reset can only safely happen on the *next* pass, right
# at the top, which is what the button's own st.rerun() sets up.
if st.session_state.pop("pending_clear", False):
    st.session_state.table_rows = None
    st.session_state.results_cache = {}
    st.session_state.drilldown_permits = []
    st.session_state.extra_drilldown_permits = []
    st.session_state.error = None
    st.session_state.batch_errors = []
    st.session_state.unified_search_input = ""

conn = get_connection()

# Welcome/intro text, centered under the logo -- shown only before the
# first search (or after "Clear results", which resets table_rows back
# to None the same way), so it doesn't compete with actual results. A
# placeholder rather than an immediate st.markdown(): this position in
# the script runs *before* a same-click search's own processing further
# down sets table_rows, so filling it here would show stale pre-search
# state on the very click that just produced results. welcome_slot gets
# filled in (or left empty) further down, once table_rows reflects
# whatever this render actually ended up with.
welcome_slot = st.empty()

# --- Search: one bar, permit number(s) or address ------------------------
_, search_col, _ = st.columns([1, 3, 1])
with search_col:
    input_col, toggle_col, tip_col = st.columns([9, 2, 1])
    with input_col:
        raw_query = st.text_input(
            t("unified_search_placeholder"),
            placeholder=t("unified_search_placeholder"),
            key="unified_search_input",
            label_visibility="collapsed",
        )
    with toggle_col:
        # Language toggle, moved here (left of the search-bar tooltip)
        # from its own centered row below the header.
        render_language_toggle()
    with tip_col:
        # A custom circular "?" icon with a CSS-only hover tooltip --
        # not text_input's own help= (Streamlit drops that help icon
        # entirely when label_visibility="collapsed" is set, since
        # there's no label row for it to attach to) and not the browser's
        # native title= attribute (unreliable: inconsistent per-browser
        # delay, easy to miss, no hover state at all on touch/mobile).
        # This is a real :hover-driven CSS reveal, so it doesn't depend
        # on native tooltip timing/rendering the way title= did.
        _help_paragraphs = "".join(
            f"<p>{html.escape(p)}</p>" for p in t("unified_search_help").split("\n\n")
        )
        st.markdown(
            '<div class="search-tooltip-wrap">'
            '<div class="search-tooltip-icon">?</div>'
            f'<div class="search-tooltip-content">{_help_paragraphs}</div>'
            "</div>",
            unsafe_allow_html=True,
        )

    # Search + Clear, centered as a pair below the search bar.
    _, btn_search_col, btn_clear_col, _ = st.columns([1, 3, 3, 1])
    with btn_search_col:
        # Placeholder-swap loading state (Nielsen Norman heuristic #1,
        # Visibility of System Status): the button becomes a disabled
        # "Searching..." the instant it's clicked, and an animated
        # loading bar appears immediately below, so the user never
        # wonders whether the click registered while the network-bound
        # pipeline call below is still running.
        search_button_slot = st.empty()
        search_clicked = search_button_slot.button(
            t("search_button"), type="primary", key="unified_search_button", width="stretch"
        )
    with btn_clear_col:
        clear_clicked = st.button(
            t("clear_results"), key="clear_results_button", width="stretch"
        )

    loading_bar_slot = st.empty()

if clear_clicked:
    st.session_state.pending_clear = True
    st.rerun()

if search_clicked:
    query = raw_query.strip()
    if not query:
        st.warning(t("warning_enter_permit_number"))
    else:
        search_button_slot.button(
            t("searching_button"), type="primary", disabled=True, key="unified_search_button_loading"
        )
        loading_bar_slot.markdown(
            '<div class="search-loading-track"><div class="search-loading-bar"></div></div>',
            unsafe_allow_html=True,
        )
        kind, values = search_input.classify(query)
        permit_numbers: list[str] = []
        st.session_state.error = None
        st.session_state.batch_errors = []

        if kind == "permit_numbers":
            permit_numbers = values
        else:
            try:
                matches = fetch_permits_by_address(values[0])
                permit_numbers = [m["permit_nbr"] for m in matches if m.get("permit_nbr")]
                user_state.record_search(conn, "address", values[0])
            except Exception:
                st.session_state.error = translate_error_message(GENERIC_ERROR_MESSAGE)
            if not permit_numbers and st.session_state.error is None:
                st.info(t("info_no_permits_found"))

        if len(permit_numbers) == 1:
            permit_number, validation_error = validate_permit_number(permit_numbers[0])
            if validation_error:
                st.session_state.error = validation_error
                permit_numbers = []
            else:
                permit_numbers = [permit_number]

        if permit_numbers:
            batch = portfolio.run_batch(
                conn, permit_numbers, sample_size=config.DEFAULT_COHORT_SAMPLE_SIZE, progress=False
            )
            for permit_number, result in batch.results_by_permit.items():
                st.session_state.results_cache[permit_number] = result
                user_state.record_search(conn, "permit_number", permit_number)

            st.session_state.table_rows = batch.rows
            st.session_state.drilldown_permits = (
                [batch.rows[0].permit_number] if len(batch.rows) == 1 else []
            )
            st.session_state.extra_drilldown_permits = []
            st.session_state.batch_errors = batch.errors

        # Swap the button and loading bar back to their idle state in
        # place, rather than a full st.rerun(): the results table/
        # drill-down below still render later in this same script pass
        # regardless (table_rows is already set above), so a rerun would
        # only add a redundant round trip -- and would also wipe out the
        # st.info/st.warning messages above (e.g. "no permits found")
        # before the user had a chance to read them.
        loading_bar_slot.empty()
        search_button_slot.button(
            t("search_button"), type="primary", key="unified_search_button_done", width="stretch"
        )

if not st.session_state.table_rows:
    welcome_slot.markdown(
        f'<p class="site-welcome-intro">{t("site_welcome_intro")}</p>',
        unsafe_allow_html=True,
    )

st.divider()

if st.session_state.error:
    st.error(translate_error_message(st.session_state.error))

if st.session_state.get("batch_errors"):
    errors = st.session_state.batch_errors
    st.warning(
        f"{len(errors)} " + t("warning_some_unanalyzed") + " "
        + ", ".join(p for p, _ in errors)
    )

# --- Unified results table + drill-down -----------------------------------
if st.session_state.table_rows:
    # Union, not replace: a fresh search seeds drilldown_permits directly
    # above (auto-opening the single-permit case), and any permit the
    # results table itself reports as checked gets folded in here and
    # stays open across later reruns caused by *other* widgets (an
    # "Other permits at this address" click, an expander toggle, etc.) --
    # those unrelated reruns would otherwise read the dataframe's own
    # selection as unchanged/empty and wrongly look like a deselection.
    # Trade-off: unchecking a row doesn't close its tab -- there's no
    # explicit "close tab" affordance in this redesign yet.
    table_selected = results_table.render(st.session_state.table_rows)
    for permit_number in table_selected:
        if permit_number not in st.session_state.drilldown_permits:
            st.session_state.drilldown_permits.append(permit_number)

    # One combined, print-friendly report covering every permit currently
    # shown in the table above (not just checked rows) -- someone who
    # wants to save/print the full detail rather than read it on screen.
    report_export.render_download_button(
        [r.permit_number for r in st.session_state.table_rows],
        st.session_state.results_cache,
        get_knowledge_base(),
    )

    combined = list(st.session_state.drilldown_permits) + list(
        st.session_state.extra_drilldown_permits
    )
    drill_down.render(conn, combined, st.session_state.results_cache, get_knowledge_base())
