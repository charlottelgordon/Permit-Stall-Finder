"""Sections D+E — stall findings and their developer explanations.

One card per detection, zipped 1:1 with its DeveloperExplanation. This is
safe because explain_assessment() builds developer_explanations.explanations
by iterating stall_assessment.detections directly, in order -- the two
lists are guaranteed the same length and order (see UI_DESIGN.md §3).

Every sentence a card shows is either a structured field displayed as-is
(severity, elapsed_days, percentile_rank, ...) or one of Agent 3's five
pre-composed section strings. This module never concatenates numbers into
new prose of its own (UI_DESIGN.md decision "no UI-composed analytical
sentences from raw numbers").
"""

from __future__ import annotations

import streamlit as st

from formatting import (
    BENCHMARK_SEMANTICS_LABELS,
    CATEGORY_LABELS,
    GROUNDING_STRENGTH_LABELS,
    INTERVAL_STATE_LABELS,
    SEVERITY_COLORS,
    SEVERITY_LABELS,
    VERIFICATION_STATUS_LABELS,
    has_mixed_grounding,
    kb_entry_by_id,
)
from permit_stall_finder.knowledge_base.loader import KnowledgeBase
from permit_stall_finder.schema.developer_explanation import (
    DeveloperExplanation,
    DeveloperExplanationSet,
    GroundingStatus,
    NextStep,
)
from permit_stall_finder.schema.stall_detection import (
    DelayStallDetection,
    FrictionStallDetection,
    StallAssessment,
)

_NO_DEVELOPER_STEPS = "No developer-actionable guidance is available for this specific pattern."
_NO_CITY_STEPS = "No city-dependent guidance is available for this specific pattern."
_NO_ENTRY_HEADING = "No authoritative guidance available"


def _severity_badge(detection: DelayStallDetection | FrictionStallDetection) -> str:
    color = SEVERITY_COLORS[detection.severity]
    label = SEVERITY_LABELS[detection.severity]
    return (
        f'<span style="background-color:{color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.85em;font-weight:600">{label}</span>'
    )


def _render_metrics(detection: DelayStallDetection | FrictionStallDetection) -> None:
    cols = st.columns(3)
    if isinstance(detection, DelayStallDetection):
        cols[0].metric("Elapsed days", detection.elapsed_days)
        if detection.percentile_rank is not None:
            cols[1].metric("Percentile rank", f"{detection.percentile_rank:.0f}")
        if detection.excess_days_vs_median is not None:
            cols[2].metric("Excess vs. median", f"{detection.excess_days_vs_median:+.0f} days")
        st.caption(
            f"{INTERVAL_STATE_LABELS[detection.interval_state]} · "
            f"{BENCHMARK_SEMANTICS_LABELS[detection.cohort.benchmark_semantics]} "
            f"(n={detection.cohort.n}, {detection.cohort.confidence.value})"
        )
    else:
        cols[0].metric("Observed count", detection.observed_count)
        if detection.percentile_rank is not None:
            cols[1].metric("Percentile rank", f"{detection.percentile_rank:.0f}")
        if detection.excess_count_vs_median is not None:
            cols[2].metric("Excess vs. median", f"{detection.excess_count_vs_median:+.1f}")
        st.caption(
            f"{BENCHMARK_SEMANTICS_LABELS[detection.cohort.benchmark_semantics]} "
            f"(n={detection.cohort.n}, {detection.cohort.confidence.value})"
        )


def _render_steps(heading: str, steps: list[NextStep], placeholder: str) -> None:
    st.markdown(f"**{heading}**")
    if not steps:
        st.caption(placeholder)
        return
    for step in steps:
        st.markdown(f"- {step.text} _( {GROUNDING_STRENGTH_LABELS[step.grounding_strength]} )_")


def _render_source_grounding(explanation: DeveloperExplanation, kb: KnowledgeBase) -> None:
    with st.expander("Source & grounding"):
        entry = kb_entry_by_id(kb, explanation.knowledge_base_entry_id)
        if entry is None:
            st.caption("No knowledge-base entry is associated with this explanation.")
            return
        st.caption(f"Knowledge-base entry {entry.entry_id} · v{entry.kb_version} · last reviewed {entry.last_reviewed.isoformat()}")
        for source in entry.sources:
            st.markdown(f"- [{source.title}]({source.url}) — {source.publisher}")
            st.caption(
                f"{VERIFICATION_STATUS_LABELS[source.verification_status]} "
                f"(retrieved {source.retrieved_date.isoformat()})"
            )
        if entry.caveats:
            st.markdown("**Caveats on this guidance**")
            for caveat in entry.caveats:
                st.markdown(f"- {caveat}")


def _render_card(
    detection: DelayStallDetection | FrictionStallDetection,
    explanation: DeveloperExplanation,
    kb: KnowledgeBase,
) -> None:
    with st.container(border=True):
        st.markdown(
            f"#### {CATEGORY_LABELS[detection.category]}  {_severity_badge(detection)}",
            unsafe_allow_html=True,
        )

        _render_metrics(detection)

        st.markdown("**What the data shows**")
        st.write(explanation.what_the_data_shows)

        if explanation.grounding_status == GroundingStatus.NO_ENTRY_AVAILABLE:
            st.markdown(f"**{_NO_ENTRY_HEADING}**")
            st.write(explanation.what_this_usually_means)
        else:
            st.markdown("**What this usually means**")
            st.write(explanation.what_this_usually_means)

        _render_steps(
            "Steps you can take", explanation.developer_actionable_steps, _NO_DEVELOPER_STEPS
        )
        _render_steps(
            "Steps that depend on the city", explanation.city_dependent_steps, _NO_CITY_STEPS
        )

        if explanation.limitations:
            st.markdown("**What we cannot tell from this data**")
            for item in explanation.limitations:
                st.markdown(f"- {item}")

        if detection.caveats:
            st.markdown("**Caveats**")
            for caveat in detection.caveats:
                st.markdown(f"- {caveat}")

        _render_source_grounding(explanation, kb)


def render(
    stall_assessment: StallAssessment,
    developer_explanations: DeveloperExplanationSet,
    kb: KnowledgeBase,
) -> None:
    if not stall_assessment.detections:
        return

    st.subheader("Stall findings")

    if has_mixed_grounding(developer_explanations.explanations):
        st.caption(
            "Some findings below are backed by an authoritative knowledge-base entry; "
            "others are not -- this is noted individually on each finding."
        )

    for detection, explanation in zip(stall_assessment.detections, developer_explanations.explanations):
        _render_card(detection, explanation, kb)
