"""Permit Stall Finder -- Streamlit MVP entrypoint.

Thin presentation layer over orchestration.pipeline.run_pipeline(). This
file and everything under app/ contain no analytical logic: no severity
computation, no cohort math, no knowledge-base matching, no explanation
text. Every fact rendered here already exists on the PermitAnalysisResult
returned by the orchestrator -- see research/UI_DESIGN.md for the original
design and the constraints each section renderer follows.

There is no persona/role gate: the landing page offers one unified way in
-- paste permit number(s), or search by address -- and the number of
permit numbers that resolve decides whether the user lands in the
single-permit deep-dive view or the portfolio.py triage table. A single
permit number always goes straight to the deep dive; two or more always
go to the table, with a selector to drill into any one of them. This
replaces an earlier persona-gated version of this file that asked "what
best describes you?" on first load -- removed because sorting by intent
(how many permits do you actually have in hand right now) is a more
direct signal than sorting by declared role.

Starred items and recent searches (storage/user_state.py, laid out by
sections/quick_access.py) exist for the same return user this whole page
is designed around: someone who checks the same permit(s) or address
every day for their job. Clicking a starred/recent pill below sets the
matching widget's session_state value *before* that widget is
instantiated later in this same script run -- the same pattern Streamlit
apps use to programmatically pre-fill a widget -- so a pill click behaves
exactly like the user having typed that value and clicked the tab's own
search/analyze button, with no extra st.rerun() required for the numbers
case. The "Clear results" button follows the same pre-widget-instantiation
rule in reverse: it blanks those same session_state keys and *does* call
st.rerun(), since clearing needs to also wipe already-rendered result
state below.
"""

from __future__ import annotations

import streamlit as st

import portfolio
from db import get_connection, get_knowledge_base
from i18n import get_language, render_language_toggle, t, translate_error_message
from errors import safe_error_message, validate_permit_number
from sections import (
    address_search,
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

from permit_stall_finder import config
from permit_stall_finder.orchestration.pipeline import PipelineExecutionError, run_pipeline
from permit_stall_finder.storage import user_state

st.set_page_config(page_title="Permit Stall Finder", page_icon="🌴", layout="wide")

# Cosmetic only -- a gradient accent bar that also carries the app's own
# title, instead of a separate thin decorative bar plus a full st.title()
# heading underneath it. Folding the title into the gradient bar (via a
# pure-CSS ::after label, since Streamlit's header has no built-in text
# slot) reclaims the vertical space a second heading row would cost --
# consistent with this page's "no scrolling" layout goal. Touches no
# analytical content or component structure; every fact still comes from
# PermitAnalysisResult exactly as the section renderers already display
# it. layout="wide" supports the quick-glance card and portfolio table
# sitting in a single horizontal strip without wrapping.
#
# Palette and type are Patreon-inspired: the gradient runs from Patreon's
# "Fiery Coral" (#FF424D) to their "Blue Whale" navy (#052D49) -- the same
# warm/creative-meets-solid/professional pairing Patreon's own brand uses,
# which is also just a good match for "cool and trustworthy." The title
# text sits on this gradient as branding/logotype (WCAG's contrast rule
# has an explicit exemption for logotype text), which is why it can use
# plain white regardless of where it lands on the gradient -- unlike the
# app's actual buttons and links, which use the flat, high-contrast navy
# from .streamlit/config.toml's primaryColor instead of the coral, since
# white-on-coral only clears ~3.4:1 contrast (below the 4.5:1 minimum for
# real UI text). Poppins (a free geometric sans from Google Fonts) stands
# in for Patreon's own GT Walsheim Bold, which is a paid commercial
# typeface not available to load from a CDN.
#
# position: relative (overriding Streamlit's default position: fixed) so
# the header scrolls away with the rest of the page instead of staying
# pinned/frozen at the top of the viewport. Once it's back in normal flow,
# margin-bottom on the header (rather than the earlier block-container
# padding-top hack, which existed only to keep content from hiding under
# a fixed header) is what creates breathing room before the page content.
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
        background: linear-gradient(90deg, #FF424D 0%, #F96854 35%, #6B4A63 65%, #052D49 100%) !important;
        height: 3.25rem !important;
        position: relative !important;
        overflow: visible !important;
        margin-bottom: 1.75rem;
    }
    [data-testid="stHeader"]::after {
        content: "🌴 Permit Stall Finder";
        position: absolute;
        left: 0;
        top: 0;
        width: 100%;
        height: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-family: 'Poppins', sans-serif;
        font-size: 1.35rem;
        font-weight: 700;
        letter-spacing: -0.01em;
        white-space: nowrap;
        pointer-events: none;
    }
    [data-testid="stToolbar"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"] {
        display: none;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 10px;
    }
    div.block-container {
        padding-top: 1rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Language toggle -- EN/ES. Placed above the intro sentence so it's the
# first interactive control on the page; changing it reruns the script,
# and every t()/label lookup elsewhere on the page reads the choice back
# out of st.session_state on that same rerun.
render_language_toggle()

st.write(t("page_intro"))

# --- Session state defaults --------------------------------------------
if "result" not in st.session_state:
    st.session_state.result = None
if "error" not in st.session_state:
    st.session_state.error = None
if "portfolio_rows" not in st.session_state:
    st.session_state.portfolio_rows = None
if "portfolio_results" not in st.session_state:
    st.session_state.portfolio_results = None

conn = get_connection()

# --- Quick access: starred + recent, for a return user checking the same
# permit(s) or address every day -- and a Clear results button next to it
# so the same daily user can also blank today's search without a page
# reload. Both act by setting/clearing session_state keys *before* the
# widgets that own those keys are instantiated further down this script,
# rather than mutating already-rendered widgets. -------------------------
qa_selection = quick_access.render(conn)

clear_col, _ = st.columns([1, 5])
if clear_col.button(t("clear_results"), key="clear_results_button"):
    st.session_state.result = None
    st.session_state.error = None
    st.session_state.portfolio_rows = None
    st.session_state.portfolio_results = None
    st.session_state.address_matches = None
    st.session_state.permit_numbers_input = ""
    st.session_state.address_query_input = ""
    for key in list(st.session_state.keys()):
        if key.startswith("address_match_"):
            del st.session_state[key]
    st.rerun()

triggered = False
permit_numbers: list[str] = []
auto_run_address = False

if qa_selection is not None:
    if qa_selection.kind == "permit_number":
        # Pre-fills the text area for visibility, but also runs the
        # pipeline directly this same rerun -- a starred/recent permit
        # pill is meant to be a one-click re-run, not a one-click
        # pre-fill-then-still-have-to-click-Analyze.
        st.session_state["permit_numbers_input"] = qa_selection.value
        triggered = True
        permit_numbers = [qa_selection.value]
    else:
        st.session_state["address_query_input"] = qa_selection.value
        auto_run_address = True

# --- Search: permit number(s), or address -------------------------------
# Both tabs' code runs every rerun (Streamlit tabs are a display toggle,
# not conditional execution) but only the tab whose button was actually
# clicked this run can set triggered=True, since only one widget click
# drives any given rerun.
tab_numbers, tab_address = st.tabs([t("tab_permit_number"), t("tab_address")])

with tab_numbers:
    raw_text = st.text_area(
        t("permit_numbers_label"),
        placeholder="21030-20000-00256\n25016-10000-32699",
        height=100,
        label_visibility="collapsed",
        key="permit_numbers_input",
        help=t("permit_number_help"),
    )
    # A placeholder (rather than a bare st.button) so the button can be
    # swapped for a disabled "Analyzing..." version the instant it's
    # clicked -- Nielsen Norman's Visibility of System Status heuristic:
    # the user should never wonder whether their click registered while
    # the (network-bound) pipeline call below is still running.
    analyze_button_slot = st.empty()
    if analyze_button_slot.button(t("analyze_button"), type="primary", key="analyze_numbers_button"):
        parsed = portfolio.parse_permit_numbers(raw_text)
        if not parsed:
            st.warning(t("warning_enter_permit_number"))
        else:
            analyze_button_slot.button(
                t("analyzing_button"), type="primary", disabled=True, key="analyze_numbers_button_loading"
            )
            triggered = True
            permit_numbers = parsed

with tab_address:
    address_submitted, address_permit_numbers = address_search.render(conn, auto_run=auto_run_address)
    if address_submitted:
        triggered = True
        permit_numbers = address_permit_numbers

# --- Run the pipeline: one permit goes straight to the deep dive, two or
# more go to the portfolio table. This is the only place that decision is
# made, regardless of which tab the permit numbers came from. -----------
if triggered:
    st.session_state.error = None
    if len(permit_numbers) == 1:
        permit_number, validation_error = validate_permit_number(permit_numbers[0])
        if validation_error:
            st.session_state.result = None
            st.session_state.error = validation_error
        else:
            try:
                with st.spinner(t("spinner_analyzing")):
                    result = run_pipeline(conn, permit_number)
                st.session_state.result = result
                st.session_state.portfolio_rows = None
                st.session_state.portfolio_results = None
                user_state.record_search(conn, "permit_number", permit_number)
            except PipelineExecutionError as exc:
                st.session_state.result = None
                st.session_state.error = safe_error_message(exc)
    else:
        batch = portfolio.run_batch(conn, permit_numbers, sample_size=config.DEFAULT_COHORT_SAMPLE_SIZE)
        st.session_state.result = None
        st.session_state.portfolio_rows = batch.rows
        st.session_state.portfolio_results = batch.results_by_permit
        for permit_number in batch.results_by_permit:
            user_state.record_search(conn, "permit_number", permit_number)
        if batch.errors:
            st.warning(
                f"{len(batch.errors)} " + t("warning_some_unanalyzed") + " "
                + ", ".join(p for p, _ in batch.errors)
            )

st.divider()

# --- Portfolio table, if a batch has been run ----------------------------
if st.session_state.portfolio_rows:
    portfolio.render_table(st.session_state.portfolio_rows)

    selected_permit = st.session_state.get("selected_permit")
    cached_results = st.session_state.portfolio_results or {}
    if selected_permit and selected_permit in cached_results:
        # Reuses the PermitAnalysisResult already computed during the
        # batch run above -- never re-runs the pipeline just to render the
        # same permit's detail view a second time.
        st.session_state.result = cached_results[selected_permit]
        st.session_state.error = None

if st.session_state.error:
    st.error(translate_error_message(st.session_state.error))

result = st.session_state.result
if result is not None:
    # Always visible, no scrolling required: the quick-glance strip, the
    # map, the neutral top-level read, and a concrete next action. Deeper
    # material (full journey, per-finding explanation cards,
    # coverage/data-quality notes) sits behind an explicit show/hide
    # toggle -- collapsed by default -- rather than always rendering a
    # long page. The disclaimer itself stays outside the toggle and always
    # renders, per UI_DESIGN.md's "never hide the disclaimer" decision.
    quick_glance.render(result)
    st.caption(f"{t('permit_caption')} {result.permit_number}")
    quick_access.render_star_toggle(conn, "permit_number", result.permit_number)

    location_map.render(result)
    top_level_result.render(result)
    next_best_action.render(result, get_knowledge_base())

    show_full_analysis = st.toggle(
        t("show_full_analysis"),
        value=False,
    )
    if show_full_analysis:
        permit_journey.render(result.journey)
        stall_findings.render(result.stall_assessment, result.developer_explanations, get_knowledge_base())
        coverage_gaps.render(result.coverage_gaps, result.data_quality_flags)

    disclaimer.render(result.developer_explanations.disclaimer)

