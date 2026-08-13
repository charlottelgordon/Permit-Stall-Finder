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

Starred items and recent searches (storage/user_state.py, laid out by
sections/quick_access.py) exist for a return user who checks the same
permit(s) or address every day for their job, and now sit directly below
the search bar as a row of pills. A pill click sets the search bar's own
session_state value and re-runs the script (the standard Streamlit
pattern for programmatically driving a widget you've already rendered
this pass -- you can't reassign a widget's session_state key after it's
already run in the *same* pass, but setting it and calling st.rerun()
means the very next pass's instantiation of that same widget picks the
new value up naturally), with a one-shot "pending_pill_search" flag so
that rerun also re-triggers the search immediately -- a pill click
behaves exactly like typing that value and clicking Search. "Clear
results" follows the same rerun pattern in reverse.
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
    HOMEOWNER_GUIDE_URL,
    render_language_toggle,
    t,
    translate_error_message,
)
from errors import GENERIC_ERROR_MESSAGE, validate_permit_number
from sections import quick_access, results_table

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
        background-color: #99AFD7 !important;
        height: 3.25rem !important;
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
    .header-guide-link {
        text-align: right;
        margin-top: -2.9rem;
        margin-bottom: 1.75rem;
        padding-right: 0.5rem;
        /* Streamlit's own header bar (stHeader) is position: fixed with
           z-index 999990, so without this the link renders underneath
           it -- present in the DOM but visually invisible, since the
           negative margin above pulls it up into that same fixed strip. */
        position: relative;
        z-index: 999991;
    }
    .header-guide-link a {
        display: inline-block;
        background-color: #FFFFFF;
        color: #052D49;
        font-weight: 600;
        text-decoration: none;
        padding: 0.4rem 0.9rem;
        border-radius: 6px;
        border: 1px solid #052D49;
    }
    .header-guide-link a:hover {
        background-color: #052D49;
        color: #FFFFFF;
    }
    .app-logo-heading {
        text-align: center;
        margin: 0;
    }
    .app-logo-heading img {
        max-width: 420px;
        width: 100%;
        height: auto;
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
    .search-tooltip-icon {
        display: flex;
        align-items: center;
        justify-content: center;
        height: 2.6rem;
        font-size: 1.2rem;
        cursor: help;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Far right of the header bar: a real, clickable button out to LADBS's own
# Homeowner Step-by-Step guide -- Nielsen Norman's Help and Documentation
# heuristic, pointing at the city's own authoritative walkthrough rather
# than this tool trying to re-explain the permitting process itself.
st.markdown(
    f'<div class="header-guide-link"><a href="{HOMEOWNER_GUIDE_URL}" target="_blank" '
    f'rel="noopener noreferrer">{t("homeowner_guide_link")}</a></div>',
    unsafe_allow_html=True,
)

# App logo, centered, wrapped in a real <h1> so assistive tech still gets
# a heading (announced via the image's alt text) even though the visible
# content is now an image rather than text.
_logo_b64 = base64.b64encode((Path(__file__).parent / "assets" / "logo.png").read_bytes()).decode()
st.markdown(
    f'<h1 class="app-logo-heading"><img src="data:image/png;base64,{_logo_b64}" alt="{APP_NAME}"></h1>',
    unsafe_allow_html=True,
)

# Language toggle, centered directly below the logo.
_, toggle_col, _ = st.columns([2, 1, 2])
with toggle_col:
    render_language_toggle()

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

conn = get_connection()

# --- Search: one bar, permit number(s) or address ------------------------
_, search_col, _ = st.columns([1, 3, 1])
with search_col:
    input_col, tip_col = st.columns([11, 1])
    with input_col:
        raw_query = st.text_input(
            t("unified_search_placeholder"),
            placeholder=t("unified_search_placeholder"),
            key="unified_search_input",
            label_visibility="collapsed",
        )
    with tip_col:
        # A manual tooltip icon rather than text_input's own help=
        # parameter: Streamlit drops the help icon entirely when
        # label_visibility="collapsed" is set (no label row for it to
        # attach to), so help= silently never rendered anything here.
        # This uses the browser's own native title-attribute tooltip
        # instead, positioned to the right of the search bar. The help
        # text's own blank line (between the permit-number and address
        # paragraphs) is swapped for &#10; -- a literal newline inside an
        # HTML attribute reads as a blank line to Streamlit's CommonMark
        # parser, which terminates an inline HTML block at the first
        # blank line and dumps the rest as a stray paragraph instead of
        # parsing it as part of the tag.
        tooltip_text = html.escape(t("unified_search_help")).replace("\n", "&#10;")
        st.markdown(
            f'<div class="search-tooltip-icon" title="{tooltip_text}">❓</div>',
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

    if st.session_state.pop("pending_pill_search", False):
        search_clicked = True

    # Starred searches, directly below the search bar.
    qa_selection = quick_access.render(conn)
    if qa_selection is not None:
        st.session_state["unified_search_input"] = qa_selection.value
        st.session_state["pending_pill_search"] = True
        st.rerun()

if clear_clicked:
    st.session_state.table_rows = None
    st.session_state.results_cache = {}
    st.session_state.drilldown_permits = []
    st.session_state.extra_drilldown_permits = []
    st.session_state.error = None
    st.session_state.batch_errors = []
    st.session_state.unified_search_input = ""
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

    combined = list(st.session_state.drilldown_permits) + list(
        st.session_state.extra_drilldown_permits
    )
    drill_down.render(conn, combined, st.session_state.results_cache, get_knowledge_base())
