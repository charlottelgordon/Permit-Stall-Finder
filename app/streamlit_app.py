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
import streamlit.components.v1 as components

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
from sections import persona_picker, report_export, results_table

from permit_stall_finder import config
from permit_stall_finder.ingestion.permits import fetch_permits_by_address
from permit_stall_finder.storage import user_state

st.set_page_config(
    page_title=APP_NAME,
    page_icon=str(Path(__file__).parent / "assets" / "favicon.jpeg"),
    layout="wide",
)

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
        /* The navy band between the orange header strip and the page
           body -- a border-bottom rather than a separate element so it's
           guaranteed to sit exactly flush with the header's own edge,
           full width, with no extra flow-space math needed. */
        border-bottom: 6px solid #052D49;
    }
    [data-testid="stToolbar"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"] {
        display: none;
    }
    div[data-testid="stVerticalBlockBorderWrapper"],
    div[data-testid="stExpander"] {
        border-radius: 10px;
        /* Cards sit white on top of the page's warmer off-white
           background (see .streamlit/config.toml's backgroundColor) so
           they read as distinct surfaces rather than blending in. */
        background-color: #FFFFFF;
    }
    div.block-container {
        padding-top: 1.5rem !important;
    }
    .app-header-bar {
        /* Grid, not flex: a 3-column left/center/right split keeps the
           logo truly centered regardless of how wide the home icon vs.
           the LADBS link are -- flex's justify-content: space-between
           would instead shift the center item off-true whenever the two
           side items differ in width. */
        display: grid;
        /* minmax(0, 1fr), not a bare 1fr -- grid items default to
           min-width: auto, which refuses to shrink a column below its
           content's natural width. Without the explicit 0 floor here,
           the right column couldn't shrink below the LADBS link's full
           text width on a narrow viewport, and the text wrapped across
           multiple lines instead, overflowing the header's fixed height
           (confirmed on a 375px-wide mobile viewport). */
        grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
        align-items: center;
        /* Exactly the header bar's own height (see [data-testid="stHeader"]
           above), with a margin-top of the same magnitude -- normal flow
           would place this row right after the header, at
           document-y = header height; a margin-top equal to that height
           cancels it out exactly, so this box starts at y=0 and spans the
           header's full height 1:1. That's what makes align-items: center
           land the logo/icon/link on the header's true vertical center,
           not an approximation. */
        height: 5.5rem;
        margin-top: -2.5rem;
        margin-bottom: 1.75rem;
        padding: 0 1.25rem;
        /* Streamlit's own header bar (stHeader) is position: fixed with
           z-index 999990, so without this the row renders underneath
           it -- present in the DOM but visually invisible, since the
           negative margin above pulls it up into that same fixed strip. */
        position: relative;
        z-index: 999991;
    }
    .app-header-left {
        justify-self: start;
        min-width: 0;
    }
    .app-header-right {
        justify-self: end;
        min-width: 0;
        max-width: 100%;
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
    /* An in-app pill button, not an underlined text link -- it doesn't
       navigate away from the site (unlike header-external-link below),
       so it shouldn't carry that same "external link" visual signal.
       A house-picture icon was tried first and read as confusing on a
       page whose own subject matter is building permits; a bordered
       button reads unambiguously as a nav control either way. */
    .header-home-link {
        display: inline-flex;
        align-items: center;
        font-weight: 600;
        font-size: 0.85rem;
        /* !important on both color and text-decoration: Streamlit's own
           base anchor styling sets a link color (a themed blue, not
           primaryColor) and text-decoration: underline, both with
           higher specificity than a bare class selector here otherwise
           beats -- confirmed via computed-style inspection showing
           rgb(0, 84, 163) text despite this rule saying #FFFFFF. Same
           class of bug the site-welcome-intro margin fix above ran
           into; text-decoration alone wasn't enough because color is a
           separate overridden property. */
        color: #FFFFFF !important;
        text-decoration: none !important;
        padding: 0.35rem 0.9rem;
        border: 1.5px solid #052D49;
        border-radius: 999px;
        background-color: #052D49;
        transition: background-color 0.15s ease-in-out, color 0.15s ease-in-out;
    }
    .header-home-link:hover {
        background-color: #0A4066;
        color: #FFFFFF !important;
    }
    .header-external-link {
        display: block;
        /* !important: same Streamlit base-link-color override as
           .header-home-link above -- without it this rendered
           Streamlit's default themed blue instead of navy. */
        color: #052D49 !important;
        font-weight: 600;
        font-size: 0.9rem;
        text-decoration: none !important;
        border-bottom: 1px solid transparent;
        transition: border-color 0.15s ease-in-out;
        /* Truncates with an ellipsis on a narrow viewport instead of
           wrapping across multiple lines and overflowing the header's
           fixed height -- needs the min-width: 0 on .app-header-right
           above to actually be allowed to shrink that far. */
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .header-external-link:hover {
        border-bottom-color: #052D49;
    }
    /* The real reset button the visible Home link's onclick triggers --
       kept in the DOM (display: none, not left unrendered) since a JS
       .click() still works on a hidden button; it just never needs to
       be seen. */
    div[class*="st-key-header_home_reset_trigger"] {
        display: none;
    }
    @media (max-width: 640px) {
        .app-header-bar {
            padding: 0 0.5rem;
        }
        .app-header-bar img {
            height: 2.75rem;
        }
        .header-home-link,
        .header-external-link {
            font-size: 0.65rem;
        }
    }
    .site-welcome-intro {
        /* !important on the margins: Streamlit's own default <p> margin
           reset (inside its markdown-container wrapper) otherwise wins
           over a bare class selector and zeroes out the auto left/right
           margins that center this block -- max-width alone still
           applies fine, so this looked like a "why is it centered-width
           but not centered-position" bug until inspecting computed
           styles showed margin-left/right coming back as 0px. */
        text-align: center;
        max-width: 640px;
        margin-top: 0.5rem !important;
        margin-bottom: 1.5rem !important;
        margin-left: auto !important;
        margin-right: auto !important;
        color: #444;
    }
    .persona-picker-heading {
        text-align: center;
        font-weight: 700;
        font-size: 1.4rem;
        margin: 0.5rem 0 1.25rem 0;
        color: #052D49;
    }
    /* Persona picker buttons: white cards (matching the rest of the
       app's card treatment -- see stVerticalBlockBorderWrapper/
       stExpander above) with a navy border and a thin orange accent
       bar along the bottom, rather than a solid orange fill -- a wall
       of solid orange directly under the already-orange header bar
       was flat and visually loud. Hover inverts to a solid navy fill,
       which reuses the app's own primary-button color (the Search
       button) so the "this is clickable" signal is consistent with
       the rest of the page. Scoped to the "persona_picker_row"
       container key so it doesn't restyle any other button. */
    div[class*="st-key-persona_picker_row"] div[data-testid="stButton"] button {
        background-color: #FFFFFF;
        color: #052D49;
        font-weight: 600;
        border: 1.5px solid #052D49;
        border-bottom: 4px solid #F5760A;
        border-radius: 8px;
        padding: 1rem 1.25rem;
        font-size: 1rem;
        box-shadow: 0 1px 4px rgba(5, 45, 73, 0.1);
        transition: background-color 0.15s ease-in-out, color 0.15s ease-in-out,
            transform 0.15s ease-in-out;
    }
    div[class*="st-key-persona_picker_row"] div[data-testid="stButton"] button:hover {
        background-color: #052D49;
        color: #FFFFFF;
        border-color: #052D49;
        border-bottom-color: #F5760A;
        transform: translateY(-1px);
    }
    div[class*="st-key-persona_picker_row"] div[data-testid="stButton"] button:focus-visible {
        outline: 2px solid #052D49;
        outline-offset: 2px;
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
    f'<div class="app-header-left"><a href="javascript:void(0)" class="header-home-link" '
    f'title="{t("header_home_aria_label")}">{t("header_home_aria_label")}</a></div>'
    f'<div class="app-header-center" role="heading" aria-level="1">'
    f'<img src="data:image/png;base64,{_logo_b64}" alt="{APP_NAME}"></div>'
    '<div class="app-header-right">'
    f'<a href="https://dbs.lacity.gov/services/plan-review-permitting/building-permits" '
    f'target="_blank" rel="noopener noreferrer" class="header-external-link">{t("header_ladbs_link")}</a></div>'
    "</div>",
    unsafe_allow_html=True,
)
# The visible "Home" element above is a styled <a>, kept exactly where
# it already was (avoids re-deriving the header's overlay-into-the-
# fixed-orange-bar positioning math for a second element) -- but
# href="javascript:void(0)" means clicking it does no real browser
# navigation at all, so it can never open a new tab. It has no
# onclick= attribute (Streamlit strips inline event-handler attributes
# from markdown HTML as an XSS protection, confirmed by inspecting the
# rendered DOM -- unsafe_allow_html=True does not exempt them); the
# script block below wires up a real click handler from outside that
# sanitized HTML instead. The hidden button is what actually resets
# state on click -- kept in the DOM via display: none (not left
# unrendered), since a JS click still works on a hidden button.
with st.container(key="header_home_reset_trigger"):
    home_clicked = st.button("Home", key="header_home_reset_button")
if home_clicked:
    st.session_state.pending_home_reset = True
    st.rerun()

# Bridges the visible Home link's click to the hidden button above --
# same zero-size-iframe-reaching-into-window.parent.document technique
# i18n.py's _sync_html_lang() already uses for exactly this "Streamlit
# doesn't expose an API for this" situation. Re-injected on every
# script run (like that one is) so the handler survives the header
# markdown being replaced on each rerun; assigning .onclick directly
# (rather than addEventListener) means a fresh assignment always
# replaces the prior one instead of stacking duplicate handlers.
components.html(
    """
    <script>
    try {
        const homeLink = window.parent.document.querySelector('.header-home-link');
        const hiddenBtn = window.parent.document.querySelector(
            'div[class*="st-key-header_home_reset_trigger"] button'
        );
        if (homeLink && hiddenBtn) {
            homeLink.onclick = function(e) {
                e.preventDefault();
                hiddenBtn.click();
            };
        }
    } catch (e) {}
    </script>
    """,
    height=0,
    width=0,
)

# --- Session state defaults --------------------------------------------
if "selected_persona" not in st.session_state:
    st.session_state.selected_persona = None
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

# One-shot flags from a "Clear results" click or the Home button (see
# below): must run *before* st.text_input(key="unified_search_input") is
# instantiated further down, since Streamlit disallows writing to a
# widget's session_state key once that widget has already rendered this
# run -- both buttons that set these flags render after the text input,
# so the reset can only safely happen on the *next* pass, right at the
# top, which is what each button's own st.rerun() sets up. Home does
# everything Clear does, plus also reopening the role picker.
_pending_clear = st.session_state.pop("pending_clear", False)
_pending_home_reset = st.session_state.pop("pending_home_reset", False)
if _pending_clear or _pending_home_reset:
    st.session_state.table_rows = None
    st.session_state.results_cache = {}
    st.session_state.drilldown_permits = []
    st.session_state.extra_drilldown_permits = []
    st.session_state.error = None
    st.session_state.batch_errors = []
    st.session_state.unified_search_input = ""
if _pending_home_reset:
    st.session_state.selected_persona = None

conn = get_connection()

# Language toggle, right-aligned above the welcome text (moved off the
# search row -- next to the tooltip there, it was crowding that row's
# spacing).
_, toggle_col = st.columns([5, 1])
with toggle_col:
    render_language_toggle()

# Welcome/intro text, centered under the logo -- always visible
# (Phase: kept even after a search, per explicit request -- toggling it
# on/off based on search state made the top of the page change on every
# search, which read as jarring rather than helpful).
st.markdown(
    f'<p class="site-welcome-intro">{t("site_welcome_intro")}</p>',
    unsafe_allow_html=True,
)

# --- Persona gate: the search bar stays hidden until a role is picked --
if not st.session_state.selected_persona:
    persona_picker.render()
else:
    # --- Search: one bar, permit number(s) or address ---------------------
    _, search_col, _ = st.columns([1, 3, 1])
    with search_col:
        input_col, tip_col = st.columns([9, 1])
        with input_col:
            raw_query = st.text_input(
                t("unified_search_placeholder"),
                placeholder=t("unified_search_placeholder"),
                key="unified_search_input",
                label_visibility="collapsed",
            )
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
                t("searching_button"),
                type="primary",
                disabled=True,
                key="unified_search_button_loading",
                width="stretch",
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
