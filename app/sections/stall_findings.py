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

from formatting import SEVERITY_COLORS, has_mixed_grounding, kb_entry_by_id
from i18n import (
    benchmark_semantics_label,
    category_label,
    grounding_strength_label,
    interval_state_label,
    severity_label,
    t,
    verification_status_label,
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

# _NO_DEVELOPER_STEPS / _NO_CITY_STEPS / _NO_ENTRY_HEADING replaced by i18n.t() lookups below.


def _severity_badge(detection: DelayStallDetection | FrictionStallDetection) -> str:
    color = SEVERITY_COLORS[detection.severity]
    label = severity_label(detection.severity)
    return (
        f'<span style="background-color:{color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.85em;font-weight:600">{label}</span>'
    )


def _render_metrics(detection: DelayStallDetection | FrictionStallDetection) -> None:
    cols = st.columns(3)
    if isinstance(detection, DelayStallDetection):
        cols[0].metric(t("elapsed_days_metric"), detection.elapsed_days)
        if detection.percentile_rank is not None:
            cols[1].metric(t("percentile_rank_metric"), f"{detection.percentile_rank:.0f}")
        if detection.excess_days_vs_median is not None:
            cols[2].metric(t("excess_vs_median_metric"), f"{detection.excess_days_vs_median:+.0f} {t('days_suffix')}")
        st.caption(
            f"{interval_state_label(detection.interval_state)} · "
            f"{benchmark_semantics_label(detection.cohort.benchmark_semantics)} "
            f"(n={detection.cohort.n}, {detection.cohort.confidence.value})"
        )
    else:
        cols[0].metric(t("observed_count_metric"), detection.observed_count)
        if detection.percentile_rank is not None:
            cols[1].metric(t("percentile_rank_metric"), f"{detection.percentile_rank:.0f}")
        if detection.excess_count_vs_median is not None:
            cols[2].metric(t("excess_vs_median_metric"), f"{detection.excess_count_vs_median:+.1f}")
        st.caption(
            f"{benchmark_semantics_label(detection.cohort.benchmark_semantics)} "
            f"(n={detection.cohort.n}, {detection.cohort.confidence.value})"
        )


def _render_steps(heading: str, steps: list[NextStep], placeholder: str) -> None:
    st.markdown(f"**{heading}**")
    if not steps:
        st.caption(placeholder)
        return
    for step in steps:
        st.markdown(f"- {step.text} _( {grounding_strength_label(step.grounding_strength)} )_")


def _render_source_grounding(explanation: DeveloperExplanation, kb: KnowledgeBase) -> None:
    with st.expander(t("source_and_grounding")):
        entry = kb_entry_by_id(kb, explanation.knowledge_base_entry_id)
        if entry is None:
            st.caption(t("no_kb_entry"))
            return
        st.caption(f"Knowledge-base entry {entry.entry_id} · v{entry.kb_version} · last reviewed {entry.last_reviewed.isoformat()}")
        for source in entry.sources:
            st.markdown(f"- [{source.title}]({source.url}) — {source.publisher}")
            st.caption(
                f"{verification_status_label(source.verification_status)} "
                f"(retrieved {source.retrieved_date.isoformat()})"
            )
        if entry.caveats:
            st.markdown(f"**{t('caveats_on_guidance')}**")
            for caveat in entry.caveats:
                st.markdown(f"- {caveat}")


def _render_card(
    detection: DelayStallDetection | FrictionStallDetection,
    explanation: DeveloperExplanation,
    kb: KnowledgeBase,
) -> None:
    with st.container(border=True):
        st.markdown(
            f"#### {category_label(detection.category)}  {_severity_badge(detection)}",
            unsafe_allow_html=True,
        )

        _render_metrics(detection)

        st.markdown(f"**{t('what_data_shows')}**")
        st.write(explanation.what_the_data_shows)

        if explanation.grounding_status == GroundingStatus.NO_ENTRY_AVAILABLE:
            st.markdown(f"**{t('no_entry_heading')}**")
            st.write(explanation.what_this_usually_means)
        else:
            st.markdown(f"**{t('what_this_usually_means')}**")
            st.write(explanation.what_this_usually_means)

        _render_steps(
            t("steps_you_can_take"), explanation.developer_actionable_steps, t("no_developer_steps")
        )
        _render_steps(
            t("steps_depend_on_city"), explanation.city_dependent_steps, t("no_city_steps")
        )

        if explanation.limitations:
            st.markdown(f"**{t('cannot_tell')}**")
            for item in explanation.limitations:
                st.markdown(f"- {item}")

        if detection.caveats:
            st.markdown(f"**{t('caveats')}**")
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

    st.subheader(t("stall_findings_header"))

    if has_mixed_grounding(developer_explanations.explanations):
        st.caption(t("mixed_grounding_caption"))

    for detection, explanation in zip(stall_assessment.detections, developer_explanations.explanations):
        _render_card(detection, explanation, kb)
