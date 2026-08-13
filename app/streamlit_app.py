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

# A real, solid-color header bar carrying the app's own name as an actual
# <h1> heading just below it (rendered further down), rather than the
# earlier gradient bar's ::after pseudo-element title -- that text was
# never a real heading for assistive tech. This CSS only recolors
# Streamlit's own header chrome and removes its default toolbar icons.
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
    }
    .header-guide-link a {
        color: #052D49;
        font-weight: 600;
        text-decoration: none;
    }
    .header-guide-link a:hover {
        text-decoration: underline;
    }
    .onboarding-intro {
        text-align: center;
        max-width: 640px;
        margin: 0.5rem auto 1.5rem auto;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Far right of the header bar: a real, clickable link out to LADBS's own
# Homeowner Step-by-Step guide -- Nielsen Norman's Help and Documentation
# heuristic, pointing at the city's own authoritative walkthrough rather
# than this tool trying to re-explain the permitting process itself.
st.markdown(
    f'<div class="header-guide-link"><a href="{HOMEOWNER_GUIDE_URL}" target="_blank" '
    f'rel="noopener noreferrer">{t("homeowner_guide_link")}</a></div>',
    unsafe_allow_html=True,
)

st.markdown(f"<h1 style='text-align:center'>{APP_NAME}</h1>", unsafe_allow_html=True)

# Language toggle, centered directly below the title.
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
if "has_searched" not in st.session_state:
    st.session_state.has_searched = False

conn = get_connection()

# --- Search: one bar, permit number(s) or address ------------------------
_, search_col, _ = st.columns([1, 3, 1])
with search_col:
    search_row = st.columns([5, 1])
    with search_row[0]:
        raw_query = st.text_input(
            t("unified_search_placeholder"),
            placeholder=t("unified_search_placeholder"),
            key="unified_search_input",
            help=t("unified_search_help"),
            label_visibility="collapsed",
        )
    with search_row[1]:
        # Placeholder-swap loading state (Nielsen Norman heuristic #1,
        # Visibility of System Status): the button becomes a disabled
        # "Searching..." the instant it's clicked, so the user never
        # wonders whether the click registered while the network-bound
        # pipeline call below is still running.
        search_button_slot = st.empty()
        search_clicked = search_button_slot.button(
            t("search_button"), type="primary", key="unified_search_button", width="stretch"
        )

    if st.session_state.pop("pending_pill_search", False):
        search_clicked = True

    clear_clicked = st.button(t("clear_results"), key="clear_results_button")

    # Recent/starred searches, directly below the search bar.
    qa_selection = quick_access.render(conn)
    if qa_selection is not None:
        st.session_state["unified_search_input"] = qa_selection.value
        st.session_state["pending_pill_search"] = True
        st.rerun()

    if not st.session_state.has_searched:
        st.markdown(
            f'<div class="onboarding-intro">{t("onboarding_intro")}</div>',
            unsafe_allow_html=True,
        )

if clear_clicked:
    st.session_state.table_rows = None
    st.session_state.results_cache = {}
    st.session_state.drilldown_permits = []
    st.session_state.extra_drilldown_permits = []
    st.session_state.error = None
    st.session_state.batch_errors = []
    st.session_state.has_searched = False
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
                conn, permit_numbers, sample_size=config.DEFAULT_COHORT_SAMPLE_SIZE
            )
            for permit_number, result in batch.results_by_permit.items():
                st.session_state.results_cache[permit_number] = result
                user_state.record_search(conn, "permit_number", permit_number)

            st.session_state.table_rows = batch.rows
            st.session_state.drilldown_permits = (
                [batch.rows[0].permit_number] if len(batch.rows) == 1 else []
            )
            st.session_state.extra_drilldown_permits = []
            st.session_state.has_searched = True
            st.session_state.batch_errors = batch.errors

            # Force an immediate second pass rather than letting this run
            # finish rendering: the onboarding paragraph above and the
            # results table/drill-down below were already laid out earlier
            # in *this* script pass (Streamlit runs top-to-bottom once per
            # interaction), so has_searched only actually hides the
            # onboarding text starting next pass -- st.rerun() makes that
            # next pass happen immediately instead of waiting for the
            # user's next click.
            st.rerun()

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
