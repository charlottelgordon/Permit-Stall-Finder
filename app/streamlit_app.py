"""Permit Stall Finder -- Streamlit MVP entrypoint.

Thin presentation layer over orchestration.pipeline.run_pipeline(). This
file and everything under app/ contain no analytical logic: no severity
computation, no cohort math, no knowledge-base matching, no explanation
text. Every fact rendered here already exists on the PermitAnalysisResult
returned by the orchestrator -- see research/UI_DESIGN.md for the full
design and the constraints each section renderer follows.
"""

from __future__ import annotations

import streamlit as st

from db import get_connection, get_knowledge_base
from errors import safe_error_message, validate_permit_number
from sections import coverage_gaps, disclaimer, permit_journey, stall_findings, top_level_result

from permit_stall_finder.orchestration.pipeline import PipelineExecutionError, run_pipeline

st.set_page_config(page_title="Permit Stall Finder", page_icon="🌴", layout="centered")

# Cosmetic only -- a Los Angeles sunset accent bar and slightly warmer card
# styling. Touches no analytical content or component structure; every
# fact still comes from PermitAnalysisResult exactly as the section
# renderers already display it.
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
st.write(
    "Understand the observable journey of an LA building permit, identify unusual delays "
    "or process friction, and see grounded guidance on what may happen next."
)

if "result" not in st.session_state:
    st.session_state.result = None
if "error" not in st.session_state:
    st.session_state.error = None

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
                conn = get_connection()
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
    st.caption(f"Permit {result.permit_number}")

    top_level_result.render(result)
    permit_journey.render(result.journey)
    stall_findings.render(result.stall_assessment, result.developer_explanations, get_knowledge_base())
    coverage_gaps.render(result.coverage_gaps, result.data_quality_flags)
    disclaimer.render(result.developer_explanations.disclaimer)
