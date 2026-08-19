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

import browser_id
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
from sections import my_permits, persona_picker, report_export, results_table, trends_dashboard

from permit_stall_finder import config
from permit_stall_finder.ingestion.permits import fetch_permits_by_address
from permit_stall_finder.storage import starred, user_state

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
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

    /* Design system pass (Linear/Vercel/Raycast-inspired, translated to
       plain CSS custom properties since this is server-rendered Streamlit,
       not a Tailwind build). A cool slate neutral scale carries a faint
       blue bias toward the accent; the existing brand navy stays the one
       interactive accent (systematized into a tint/base/strong scale
       rather than one flat hex reused everywhere); severity colors are a
       separate semantic scale, deliberately not built from the accent
       hue. Orange -- the other half of the existing brand -- is
       restrained to exactly two places on purpose: the logo mark itself,
       and the "starred" state below. It never appears on a primary
       action, nav item, or severity chip. Radius/shadow/hover-lift move
       away from the previous Carbon pass's sharp, flat corners toward
       the softer, elevated card language this pass calls for. */
    :root {
        --n-0: #F7F8FA;
        --n-50: #FFFFFF;
        --n-100: #EEF1F5;
        --n-200: #E1E5EB;
        --n-300: #C9D0DA;
        --n-500: #5B6B80;
        --n-900: #16212E;

        --a-tint: #E7EEF4;
        --a-soft: #C7D8E6;
        --a: #0B3556;
        --a-strong: #052D49;

        --brand-warm: #F5760A;
        --brand-warm-tint: #FDEEE0;

        --sem-watch: #2B7A78;
        --sem-watch-bg: #E6F2F1;
        --sem-elevated: #93650A;
        --sem-elevated-bg: #FBF0DE;
        --sem-severe: #A24638;
        --sem-severe-bg: #FBEAE7;

        --border: var(--n-200);
        --border-strong: var(--n-300);
        --text-primary: var(--n-900);
        --text-secondary: var(--n-500);
        --shadow-color: 16 33 46;

        --radius: 10px;
        --radius-lg: 14px;
    }

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }
    h1, h2, h3, h4, h5, h6,
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3 {
        font-family: 'IBM Plex Sans', sans-serif;
        font-weight: 600;
    }
    /* Type scale kept from the prior pass -- sizes/weights carry
       hierarchy on their own, one family throughout, matching the
       Linear/Vercel convention of varying weight rather than switching
       faces. Streamlit maps st.title -> h1, st.header -> h2,
       st.subheader -> h3; body copy renders inside stMarkdownContainer
       paragraphs, and st.caption renders inside stCaptionContainer. */
    [data-testid="stMarkdownContainer"] h1 {
        font-size: 1.75rem;
        line-height: 2.25rem;
        font-weight: 600;
    }
    [data-testid="stMarkdownContainer"] h2 {
        font-size: 1.25rem;
        line-height: 1.75rem;
        font-weight: 600;
    }
    [data-testid="stMarkdownContainer"] h3 {
        font-size: 1rem;
        line-height: 1.5rem;
        font-weight: 600;
    }
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li {
        font-size: 0.875rem;
        line-height: 1.25rem;
        font-weight: 400;
        color: var(--text-primary);
    }
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p {
        font-size: 0.75rem;
        line-height: 1rem;
        font-weight: 400;
        letter-spacing: 0.32px;
        color: var(--text-secondary);
    }
    div[data-testid="stExpander"] summary {
        font-family: 'IBM Plex Sans', sans-serif;
        font-weight: 600;
        font-size: 0.875rem;
    }
    /* Button shape/sizing/states -- Search, Clear results, Download
       report, the hidden Home trigger, the star toggle. Persona-picker
       cards and the starred state keep their own more-specific selectors
       further down, which win over these defaults where they overlap. */
    div[data-testid="stButton"] button,
    div[data-testid="stFormSubmitButton"] button,
    div[data-testid="stDownloadButton"] button {
        border-radius: var(--radius);
        font-family: 'IBM Plex Sans', sans-serif;
        font-weight: 500;
        font-size: 0.875rem;
        min-height: 2.75rem;
        padding: 0 1.1rem;
        border-color: var(--border-strong);
        transition: background-color 0.15s ease, border-color 0.15s ease,
            color 0.15s ease, box-shadow 0.15s ease, transform 0.15s ease;
    }
    div[data-testid="stButton"] button:hover,
    div[data-testid="stFormSubmitButton"] button:hover,
    div[data-testid="stDownloadButton"] button:hover {
        transform: translateY(-1px);
    }
    div[data-testid="stButton"] button[kind="secondary"]:hover,
    div[data-testid="stDownloadButton"] button:hover {
        border-color: var(--a);
        color: var(--a);
    }
    div[data-testid="stButton"] button[kind="primary"] {
        box-shadow: 0 1px 2px rgba(var(--shadow-color) / 0.12);
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        box-shadow: 0 4px 12px rgba(var(--shadow-color) / 0.18);
    }
    div[data-testid="stButton"] button:focus-visible,
    div[data-testid="stFormSubmitButton"] button:focus-visible,
    div[data-testid="stDownloadButton"] button:focus-visible {
        outline: none;
        box-shadow: 0 0 0 3px var(--a-soft), 0 0 0 1.5px var(--a);
    }
    /* The starred toggle's filled state -- streamlit_app.py gives this
       button a different `key` depending on whether the current search
       is already starred, specifically so this selector can reach it;
       see the star-toggle block below for why. This is the only button
       anywhere in the app that isn't neutral or navy. */
    div[class*="st-key-star_toggle_button_starred"] button {
        background-color: var(--brand-warm-tint) !important;
        color: var(--brand-warm) !important;
        border-color: transparent !important;
    }
    [data-testid="stHeader"] {
        background-color: var(--n-0) !important;
        height: 10.5rem !important;
        border-bottom: 1px solid var(--border);
    }
    [data-testid="stToolbar"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"] {
        display: none;
    }
    div[data-testid="stVerticalBlockBorderWrapper"],
    div[data-testid="stExpander"] {
        border-radius: var(--radius-lg);
        border-color: var(--border) !important;
        background-color: var(--n-50);
        box-shadow: 0 10px 26px -18px rgba(var(--shadow-color) / 0.3);
    }
    div[data-testid="stDataFrame"] {
        border-radius: var(--radius);
        overflow: hidden;
        border: 1px solid var(--border);
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
        height: 10.5rem;
        /* -2.5rem, not scaled with the taller height above: measured live
           (getBoundingClientRect()) that this offset cancels out
           Streamlit's own fixed pre-header spacer, which doesn't change
           with our chosen height -- an earlier guess that it should scale
           with height overshot by exactly the height increase (confirmed
           by the bar rendering 80px above y=0 at -7.5rem before this). */
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
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 0.4rem;
        margin: 0;
    }
    .app-header-bar img {
        height: 7rem;
        width: auto;
        display: block;
    }
    .app-header-tagline {
        margin: 0;
        text-align: center;
        max-width: 30rem;
        font-size: 1rem;
        line-height: 1.4;
        font-weight: 400;
        color: var(--text-secondary);
    }
    /* An in-app pill button, not an underlined text link -- it doesn't
       navigate away from the site (unlike header-external-link below),
       so it shouldn't carry that same "external link" visual signal.
       A house-picture icon was tried first and read as confusing on a
       page whose own subject matter is building permits; a bordered
       button reads unambiguously as a nav control either way. Bordered/
       neutral rather than navy-filled now that the header itself is
       light -- a solid-navy pill directly under a light header reads as
       loud as the old solid-orange header did. */
    .header-home-link {
        display: inline-flex;
        align-items: center;
        font-weight: 500;
        font-size: 0.85rem;
        /* !important on both color and text-decoration: Streamlit's own
           base anchor styling sets a link color (a themed blue, not
           primaryColor) and text-decoration: underline, both with
           higher specificity than a bare class selector here otherwise
           beats -- confirmed via computed-style inspection showing
           rgb(0, 84, 163) text despite this rule saying the intended
           color; text-decoration alone wasn't enough because color is a
           separate overridden property. */
        color: var(--text-primary) !important;
        text-decoration: none !important;
        padding: 0.35rem 0.9rem;
        border: 1.5px solid var(--border-strong);
        border-radius: 999px;
        background-color: var(--n-50);
        transition: border-color 0.15s ease, color 0.15s ease;
    }
    .header-home-link:hover {
        border-color: var(--a);
        color: var(--a) !important;
    }
    .header-external-link {
        display: block;
        /* !important: same Streamlit base-link-color override as
           .header-home-link above -- without it this rendered
           Streamlit's default themed blue instead of the accent. */
        color: var(--a-strong) !important;
        font-weight: 500;
        font-size: 0.85rem;
        text-decoration: none !important;
        /* Always underlined (not just on hover) -- a real link inside
           plain-looking header text otherwise reads as ambiguous about
           whether it's clickable. Hover deepens the color instead of
           revealing the underline, since the underline is no longer the
           hover signal. */
        border-bottom: 1px solid var(--a-strong);
        transition: color 0.15s ease-in-out, border-color 0.15s ease-in-out;
        /* Truncates with an ellipsis on a narrow viewport instead of
           wrapping across multiple lines and overflowing the header's
           fixed height -- needs the min-width: 0 on .app-header-right
           above to actually be allowed to shrink that far. */
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .header-external-link:hover {
        color: var(--a) !important;
        border-bottom-color: var(--a);
    }
    /* Positions the (real, separately-rendered) language toggle into the
       header's bottom-right corner, under the LADBS link -- position:
       fixed rather than absolute, since this container isn't a DOM
       descendant of .app-header-bar and so can't rely on it as a
       positioning ancestor. Values tuned empirically against the actual
       rendered header, same as this header's other positioning math. */
    div[class*="st-key-header_language_toggle_wrap"] {
        /* width: fit-content, not the stVerticalBlock default of 100% --
           without it, "right: 1.25rem" anchors a full-viewport-width box
           (whose own content then still sits at its own left edge), not
           the toggle itself; confirmed via the rendered box's
           getBoundingClientRect() showing width: 900 (full viewport)
           before this fix. */
        position: fixed;
        top: 6.6rem;
        right: 1.25rem;
        width: fit-content;
        z-index: 999992;
    }
    @media (max-width: 640px) {
        /* Centered, not right-anchored -- the mobile header stacks
           everything in one centered column below (see the second
           mobile media query), so there's no right-aligned LADBS link
           for "right: Xrem" to line up under anymore. */
        div[class*="st-key-header_language_toggle_wrap"] {
            top: 10.9rem;
            right: auto;
            left: 50%;
            transform: translateX(-50%);
        }
    }
    /* The real reset button the visible Home link's onclick triggers --
       kept in the DOM (display: none, not left unrendered) since a JS
       .click() still works on a hidden button; it just never needs to
       be seen. */
    div[class*="st-key-header_home_reset_trigger"] {
        display: none;
    }
    @media (max-width: 640px) {
        /* The desktop 3-column grid (Home | logo | LADBS link) has
           nowhere near enough horizontal room for a much bigger logo at
           phone widths -- confirmed live: at 375px the auto-width center
           column demanded more space than the grid had, and the side
           columns rendered overlapping the logo instead of beside it.
           Stacked into one centered column instead, avoiding the
           horizontal squeeze entirely. */
        [data-testid="stHeader"] {
            height: 13rem !important;
        }
        .app-header-bar {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0.4rem;
            height: 13rem;
            margin-top: -2.5rem;
            padding: 0.5rem 0.5rem 0;
        }
        .app-header-left, .app-header-right {
            justify-self: unset;
            min-width: 0;
            max-width: 100%;
        }
        .app-header-bar img {
            height: 3rem;
        }
        .app-header-tagline {
            font-size: 0.8rem;
            max-width: 88vw;
        }
        .header-home-link {
            font-size: 0.75rem;
        }
        .header-external-link {
            font-size: 0.75rem;
            max-width: 88vw;
        }
    }
    /* Lifecycle stepper (sections/lifecycle_stepper.py) -- a compact
       row of numbered dots + connectors at the top of each permit card,
       distinct from the severity chips/finding cards below it (this
       shows overall process position, not stall findings). */
    .lifecycle-stepper {
        display: flex;
        align-items: flex-start;
        width: 100%;
        margin-bottom: 0.25rem;
    }
    .lifecycle-step {
        display: flex;
        flex-direction: column;
        align-items: center;
        flex: 1 1 0;
        min-width: 0;
        text-align: center;
    }
    .lifecycle-step-dot {
        width: 1.6rem;
        height: 1.6rem;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.7rem;
        font-weight: 600;
        border: 2px solid var(--border-strong);
        color: var(--text-secondary);
        background: var(--n-50);
        flex-shrink: 0;
    }
    .lifecycle-step.complete .lifecycle-step-dot {
        background: var(--a-strong);
        border-color: var(--a-strong);
        color: #fff;
    }
    .lifecycle-step.current .lifecycle-step-dot {
        background: var(--n-50);
        border-color: var(--a);
        color: var(--a);
        box-shadow: 0 0 0 3px var(--a-tint);
    }
    .lifecycle-step-label {
        font-size: 0.65rem;
        color: var(--text-secondary);
        margin-top: 0.3rem;
        line-height: 1.2;
    }
    .lifecycle-step.current .lifecycle-step-label {
        color: var(--text-primary);
        font-weight: 500;
    }
    .lifecycle-step-connector {
        flex: 0 1 1.5rem;
        min-width: 0.5rem;
        height: 2px;
        background: var(--border-strong);
        margin-top: 0.79rem;
    }
    .lifecycle-step-connector.complete {
        background: var(--a-strong);
    }
    @media (max-width: 640px) {
        .lifecycle-step-label {
            display: none;
        }
        .lifecycle-step-connector {
            flex: 0 1 0.75rem;
        }
    }
    .persona-picker-heading {
        text-align: center;
        font-weight: 500;
        font-size: 0.95rem;
        margin: 0.5rem 0 1.25rem 0;
        color: var(--text-secondary);
    }
    /* Persona picker cards: neutral bordered cards (matching the rest of
       the app's card language) that lift and pick up the accent border
       on hover, rather than the previous navy-fill-on-hover treatment --
       consistent with every other interactive card in the app now
       (results table rows, stall-finding cards). No orange here: orange
       is restrained to the logo mark and the starred state only, so a
       role-select card doesn't compete with those two meanings. Scoped
       to the "persona_picker_row" container key so it doesn't restyle
       any other button. */
    div[class*="st-key-persona_picker_row"] div[data-testid="stButton"] button {
        background-color: var(--n-50);
        color: var(--text-primary);
        font-weight: 500;
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: 1.1rem 1rem;
        font-size: 0.95rem;
        box-shadow: 0 1px 2px rgba(var(--shadow-color) / 0.06);
        transition: border-color 0.15s ease, box-shadow 0.15s ease,
            transform 0.15s ease;
    }
    div[class*="st-key-persona_picker_row"] div[data-testid="stButton"] button:hover {
        border-color: var(--a);
        box-shadow: 0 10px 26px -18px rgba(var(--shadow-color) / 0.4);
        transform: translateY(-2px);
    }
    div[class*="st-key-persona_picker_row"] div[data-testid="stButton"] button:focus-visible {
        outline: none;
        box-shadow: 0 0 0 3px var(--a-soft), 0 0 0 1.5px var(--a);
    }
    .search-loading-track {
        width: 100%;
        height: 6px;
        border-radius: 3px;
        background: var(--n-100);
        overflow: hidden;
        margin: 0.5rem 0 1rem 0;
    }
    /* Navy-only gradient (no orange) -- consistent with orange being
       restrained to the logo mark and the starred state elsewhere in
       this stylesheet. */
    .search-loading-bar {
        height: 100%;
        width: 40%;
        border-radius: 3px;
        background: linear-gradient(90deg, var(--a-soft), var(--a-strong), var(--a-soft));
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
    .search-loading-gif-wrap {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 0.3rem;
        margin: 0.25rem 0 0.75rem 0;
    }
    .search-loading-gif-wrap img {
        width: 96px;
        height: auto;
    }
    .search-loading-gif-caption {
        font-size: 0.85rem;
        color: var(--text-secondary);
        text-align: center;
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
        border: 1.5px solid var(--border-strong);
        color: var(--text-secondary);
        font-size: 0.85rem;
        font-weight: 600;
        cursor: help;
        user-select: none;
        transition: border-color 0.15s ease, color 0.15s ease;
    }
    .search-tooltip-wrap:hover .search-tooltip-icon {
        border-color: var(--a);
        color: var(--a);
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
        background: var(--a-strong);
        color: #FFFFFF;
        padding: 0.75rem 1rem;
        border-radius: var(--radius);
        font-size: 0.85rem;
        line-height: 1.45;
        text-align: left;
        z-index: 9999;
        box-shadow: 0 12px 32px -16px rgba(var(--shadow-color) / 0.4);
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
#
# @st.cache_data, not a bare module-level read: Streamlit reruns this
# whole script top-to-bottom on every interaction (every button click,
# every keystroke), so without caching this file would be re-read from
# disk and re-base64-encoded on every single rerun, not just once per
# session -- confirmed as a real, measurable cost, not a theoretical one.
@st.cache_data
def _asset_b64(filename: str) -> str:
    return base64.b64encode((Path(__file__).parent / "assets" / filename).read_bytes()).decode()


_logo_b64 = _asset_b64("logo.png")
# Same raw-<img>-as-data-URI approach as the logo above -- a GIF embedded
# this way still animates in the browser (the <img> tag doesn't care that
# the bytes underneath happen to be an animated GIF rather than a static
# PNG), so no extra JS is needed to keep it moving.
_search_loader_gif_b64 = _asset_b64("house_building_loader (3).gif")
st.markdown(
    '<div class="app-header-bar">'
    f'<div class="app-header-left"><a href="javascript:void(0)" class="header-home-link" '
    f'title="{t("header_home_aria_label")}">{t("header_home_aria_label")}</a></div>'
    f'<div class="app-header-center" role="heading" aria-level="1">'
    f'<img src="data:image/png;base64,{_logo_b64}" alt="{APP_NAME}">'
    f'<p class="app-header-tagline">{t("site_welcome_intro")}</p></div>'
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
if "active_view" not in st.session_state:
    st.session_state.active_view = "search"
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
    st.session_state.active_view = "search"

conn = get_connection()
st.session_state.pcla_uid = browser_id.get_or_bootstrap_uid()

# Language toggle -- a real widget, so (unlike the tagline above) it
# can't be embedded in the header's own raw-HTML markup; rendered here,
# then pulled up into the header's bottom-right corner, under the LADBS
# link, the same "position it into the fixed header from outside" idea
# the Home-link bridge uses, but via position: fixed off the viewport
# rather than a negative margin, since this container isn't a DOM
# descendant of .app-header-bar the way that trick needs.
with st.container(key="header_language_toggle_wrap"):
    render_language_toggle()

# The welcome/intro text used to render again here, standalone, below
# the header -- now shown once, as the header's own tagline (see
# app-header-tagline above), never repeated.

# --- Persona gate: the search bar stays hidden until a role is picked --
if not st.session_state.selected_persona:
    persona_picker.render()
else:
    # --- Nav switcher: Search / Trends Dashboard --------------------------
    # Same "gate on session_state, branch what renders" idiom the persona
    # picker above already uses -- plain st.buttons rather than Streamlit's
    # native pages/st.navigation, which would reintroduce the sidebar
    # chrome this app deliberately hides everywhere else (see stHeader/
    # stToolbar/stMainMenu/stAppDeployButton rules in the stylesheet above).
    # My Permits is no longer a separate destination -- its content is now
    # part of the Search view itself (see below), so there's no button for
    # it here.
    nav_search_col, nav_trends_col, _ = st.columns([2, 2, 6])
    with nav_search_col:
        if st.button(t("nav_search"), key="nav_search_button", width="stretch"):
            st.session_state.active_view = "search"
            st.rerun()
    with nav_trends_col:
        if st.button(t("nav_trends"), key="nav_trends_button", width="stretch"):
            st.session_state.active_view = "trends"
            st.rerun()

    # --- Search: one bar, permit number(s) or address ---------------------
    # Deliberately outside the active_view branches below -- both Search
    # and Trends show this same bar at the top now, per explicit request.
    # Submitting a search while on the Trends view switches to the Search
    # view (see the active_view check inside "if permit_numbers:" below),
    # since results only ever render there.
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
            # loading bar plus a small looping gif + caption appear
            # immediately below, so the user never wonders whether the
            # click registered while the network-bound pipeline call below
            # is still running.
            search_button_slot = st.empty()
            search_clicked = search_button_slot.button(
                t("search_button"), type="primary", key="unified_search_button", width="stretch"
            )
        with btn_clear_col:
            clear_clicked = st.button(
                t("clear_results"), key="clear_results_button", width="stretch"
            )

        # Star/unstar the search just run -- tied to the query itself
        # (last_search_kind/value), not to individual result rows:
        # results_table.py's dataframe can't host per-row buttons, and
        # starring targets the whole search per how this feature was
        # scoped. A placeholder, not an inline render: last_search_value
        # only gets set further down (inside "if search_clicked:"), so
        # filling this in immediately here would always be one run
        # stale -- same st.empty()-now/fill-in-later idiom
        # search_button_slot below already uses for exactly that reason.
        star_toggle_slot = st.empty()

        loading_bar_slot = st.empty()
        loading_gif_slot = st.empty()

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
            loading_gif_slot.markdown(
                '<div class="search-loading-gif-wrap">'
                f'<img src="data:image/gif;base64,{_search_loader_gif_b64}" alt="">'
                f'<div class="search-loading-gif-caption">{t("search_loading_caption")}</div>'
                "</div>",
                unsafe_allow_html=True,
            )
            kind, values = search_input.classify(query)
            permit_numbers: list[str] = []
            st.session_state.error = None
            st.session_state.batch_errors = []
            st.session_state.last_search_kind = "permit_query" if kind == "permit_numbers" else "address"
            st.session_state.last_search_value = query

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

                # A search submitted from the Trends view has nowhere to show
                # its results there (only the Search view renders the results
                # table/drill-down below) -- switch views so the user actually
                # sees what they just searched for. Not needed when already on
                # Search: the results render later in this same pass regardless.
                if st.session_state.active_view != "search":
                    st.session_state.active_view = "search"
                    st.rerun()

            # Swap the button and loading bar back to their idle state in
            # place, rather than a full st.rerun(): the results table/
            # drill-down below still render later in this same script pass
            # regardless (table_rows is already set above), so a rerun would
            # only add a redundant round trip -- and would also wipe out the
            # st.info/st.warning messages above (e.g. "no permits found")
            # before the user had a chance to read them.
            loading_bar_slot.empty()
            loading_gif_slot.empty()
            search_button_slot.button(
                t("search_button"), type="primary", key="unified_search_button_done", width="stretch"
            )

    # Filled in here, not where the placeholder was declared above --
    # last_search_kind/value are only current as of *this* point in
    # the run (set inside "if search_clicked:" above), and this runs
    # on every rerun, not just right after a search click, so the star
    # state stays correct across unrelated reruns too (e.g. after the
    # star button's own click).
    if st.session_state.get("last_search_value") and st.session_state.get("pcla_uid"):
        _uid = st.session_state.pcla_uid
        _kind = st.session_state.last_search_kind
        _value = st.session_state.last_search_value
        _currently_starred = starred.is_starred(conn, _uid, _kind, _value)
        _star_label = t("unstar_this_search") if _currently_starred else t("star_this_search")
        # Key carries the starred/unstarred state, not just an id --
        # the stylesheet above targets "st-key-star_toggle_button_starred"
        # specifically to give the filled (starred) state its own
        # restrained-orange color, the only non-neutral/non-navy button
        # anywhere in the app. Streamlit treats a key change as a new
        # widget, which is fine here: nothing depends on this button
        # preserving internal state across the toggle.
        _star_key = f"star_toggle_button_{'starred' if _currently_starred else 'unstarred'}"
        if star_toggle_slot.button(_star_label, key=_star_key):
            if _currently_starred:
                starred.unstar_search(conn, _uid, _kind, _value)
            else:
                starred.star_search(conn, _uid, _kind, _value)
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

    if st.session_state.active_view == "search":
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

        # My Permits, folded into the Search view rather than a separate nav
        # destination -- this is what a visitor sees by default (before
        # searching anything) if they've starred any prior search, and stays
        # available below any ad-hoc search results otherwise.
        st.divider()
        my_permits.render(conn, st.session_state.get("pcla_uid"))

    elif st.session_state.active_view == "trends":
        trends_dashboard.render()
