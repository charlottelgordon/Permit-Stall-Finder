"""Permit Stall Finder -- Streamlit MVP entrypoint.

Thin presentation layer over orchestration.pipeline.run_pipeline(). This
file and everything under app/ contain no analytical logic: no severity
computation, no cohort math, no knowledge-base matching, no explanation
text. Every fact rendered here already exists on the PermitAnalysisResult
returned by the orchestrator -- see research/UI_DESIGN.md for the original
design and the constraints each section renderer follows.

Persona switcher, portfolio triage (portfolio.py), and the quick-glance
card (sections/quick_glance.py) were added after that original milestone,
for personas who need to scan many permits (general contractor, permit
expediter) rather than read one closely (property owner, architect). They
follow the exact same rule as everything else here: they only decide
*which* already-existing view opens first, *which* permits get analyzed,
and *how already-computed facts are laid out* -- never a new
interpretation of any permit's data.
"""

from __future__ import annotations

import streamlit as st

import portfolio
from db import get_connection, get_knowledge_base
from errors import safe_error_message, validate_permit_number
from personas import PERSONAS, get_persona
from sections import (
    coverage_gaps,
    disclaimer,
    next_best_action,
    permit_journey,
    quick_glance,
    stall_findings,
    top_level_result,
)

from permit_stall_finder import config
from permit_stall_finder.orchestration.pipeline import PipelineExecutionError, run_pipeline

st.set_page_config(page_title="Permit Stall Finder", page_icon="🌴", layout="wide")

# Cosmetic only -- a Los Angeles sunset accent bar and slightly warmer card
# styling. Touches no analytical content or component structure; every
# fact still comes from PermitAnalysisResult exactly as the section
# renderers already display it. layout="wide" (changed from "centered")
# supports the persona row and quick-glance card sitting in a single
# horizontal strip without wrapping.
st.markdown(
    """
    <style>
    [data-testid="stHeader"] {
        background: linear-gradient(90deg, #D9683C 0%, #E0975A 30%, #C8637A 60%, #6E7FA3 100%) !important;
        height: 6px !important;
    }
    [data-testid="stToolbar"], [data-testid="stMainMenu"], [data-testid="stAppDeployButton"] {
        display: none;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 10px;
    }
    h1 {
        letter-spacing: -0.02em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Permit Stall Finder")

# --- Session state defaults --------------------------------------------
# persona_id starts as None -- deliberately nothing is pre-selected. The
# role gate below asks the question explicitly on first load rather than
# silently defaulting to one persona's view.
if "persona_id" not in st.session_state:
    st.session_state.persona_id = None
if "view" not in st.session_state:
    st.session_state.view = None
if "result" not in st.session_state:
    st.session_state.result = None
if "error" not in st.session_state:
    st.session_state.error = None

# --- First-load role gate -------------------------------------------------
# On first load, the user is asked which role describes them, and that
# choice decides which view (single-permit deep dive vs. portfolio triage)
# they land in -- rather than silently defaulting to one. This is a
# one-time gate: once persona_id is set, the compact switcher just below
# lets them change roles at any time without seeing this screen again.
# Presentation-only, same as the switcher -- never changes what any agent
# computes, only which already-existing view opens.
if st.session_state.persona_id is None:
    st.subheader("What best describes you?")
    st.caption(
        "This decides which view opens first -- single-permit deep dive or portfolio "
        "triage. You can switch anytime from the bar at the top of the page."
    )
    gate_cols = st.columns(len(PERSONAS))
    for col, persona in zip(gate_cols, PERSONAS):
        with col:
            with st.container(border=True):
                st.markdown(f"### {persona.icon}")
                st.markdown(f"**{persona.label}**")
                st.caption(persona.tagline)
                if st.button("Select", key=f"gate_{persona.persona_id}"):
                    st.session_state.persona_id = persona.persona_id
                    st.session_state.view = persona.default_view
                    st.rerun()
    st.stop()

# --- Persona switcher ----------------------------------------------------
# Presentation-only: selects which existing view opens by default and a
# short framing caption. Never changes what any agent computes. Clicking a
# persona icon resets the view to that persona's default and clears any
# previously loaded result, so switching personas always starts from a
# clean read rather than showing a stale result under a new framing.
persona_cols = st.columns(len(PERSONAS))
for col, persona in zip(persona_cols, PERSONAS):
    is_active = persona.persona_id == st.session_state.persona_id
    if col.button(
        f"{persona.icon} {persona.label}",
        key=f"persona_{persona.persona_id}",
        type="primary" if is_active else "secondary",
    ):
        st.session_state.persona_id = persona.persona_id
        st.session_state.view = persona.default_view
        st.session_state.result = None
        st.session_state.error = None

active_persona = get_persona(st.session_state.persona_id)
st.caption(active_persona.tagline)

# Manual override -- any persona can still switch views; the persona icon
# only sets where they land by default.
view_options = ["single", "portfolio"]
st.session_state.view = st.radio(
    "View",
    options=view_options,
    format_func=lambda v: "Single permit" if v == "single" else "Portfolio triage",
    index=view_options.index(st.session_state.view),
    horizontal=True,
    label_visibility="collapsed",
)

st.divider()

conn = get_connection()

# --- Portfolio triage view -----------------------------------------------
if st.session_state.view == "portfolio":
    portfolio.render(conn, sample_size=config.DEFAULT_COHORT_SAMPLE_SIZE)

    selected_permit = st.session_state.get("selected_permit")
    cached_results = st.session_state.get("portfolio_results") or {}
    if selected_permit and selected_permit in cached_results:
        # Reuses the PermitAnalysisResult already computed during the
        # portfolio batch run above -- never re-runs the pipeline just to
        # render the same permit's detail view a second time.
        st.session_state.result = cached_results[selected_permit]
        st.session_state.error = None

# --- Single-permit view ---------------------------------------------------
else:
    st.write(
        "Understand the observable journey of an LA building permit, identify unusual delays "
        "or process friction, and see grounded guidance on what may happen next."
    )
    with st.form("permit_form"):
        raw_input = st.text_input("LA building permit number", placeholder="e.g. 21030-20000-00256")
        submitted = st.form_submit_button("Analyse Permit")

    if submitted:
        permit_number, validation_error = validate_permit_number(raw_input)
        if validation_error:
            st.session_state.result = None
            st.session_state.error = validation_error
        else:
            try:
                with st.spinner("Analysing permit..."):
                    result = run_pipeline(conn, permit_number)
                st.session_state.result = result
                st.session_state.error = None
            except PipelineExecutionError as exc:
                st.session_state.result = None
                st.session_state.error = safe_error_message(exc)

if st.session_state.error:
    st.error(st.session_state.error)

result = st.session_state.result
if result is not None:
    # Always visible, no scrolling required: the quick-glance strip, the
    # neutral top-level read, and a concrete next action. Deeper material
    # (full journey, per-finding explanation cards, coverage/data-quality
    # notes) sits behind an explicit show/hide toggle -- collapsed by
    # default -- rather than always rendering a long page. The disclaimer
    # itself stays outside the toggle and always renders, per
    # UI_DESIGN.md's "never hide the disclaimer" decision.
    quick_glance.render(result)
    st.caption(f"Permit {result.permit_number}")

    top_level_result.render(result)
    next_best_action.render(result, get_knowledge_base())

    show_full_analysis = st.toggle(
        "Show full analysis (permit journey, finding-by-finding explanations, coverage notes)",
        value=False,
    )
    if show_full_analysis:
        permit_journey.render(result.journey)
        stall_findings.render(result.stall_assessment, result.developer_explanations, get_knowledge_base())
        coverage_gaps.render(result.coverage_gaps, result.data_quality_flags)

    disclaimer.render(result.developer_explanations.disclaimer)

