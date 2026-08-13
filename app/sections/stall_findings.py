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

Phase 18: each card is now one single st.expander, collapsed by default,
labeled with just a severity dot + category + severity word (e.g. "🔴
Gap between inspections — SEVERE") -- so a user sees every finding's
headline and severity at a glance and opens only the ones they care
about. Streamlit doesn't allow expanders nested inside expanders, so
everything that used to be its own small expander inside the card
(What the data shows / What this usually means / Steps.../ Source &
grounding) is now plain content once a card itself is opened -- there's
nothing left to additionally collapse one level down. The metrics row
also switched from st.metric() (a large, bold stat display) to plain
markdown text at normal body size.
"""

from __future__ import annotations

import streamlit as st

from formatting import has_mixed_grounding, kb_entry_by_id
from i18n import (
    benchmark_semantics_label,
    category_label,
    cohort_basis_caption,
    count_vs_typical_phrase,
    days_vs_typical_phrase,
    extra_count_metric_label,
    extra_time_metric_label,
    grounding_strength_label,
    interval_state_label,
    severity_label,
    t,
    unusualness_phrase,
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
    Severity,
    StallAssessment,
)

_SEVERITY_DOT = {
    Severity.SEVERE: "🔴",
    Severity.ELEVATED: "🟠",
    Severity.WATCH: "🟡",
    Severity.UNSCORED: "⚪",
}


def _card_label(detection: DelayStallDetection | FrictionStallDetection) -> str:
    dot = _SEVERITY_DOT[detection.severity]
    return f"{dot} {category_label(detection.category)} — {severity_label(detection.severity).upper()}"


def _render_metrics(detection: DelayStallDetection | FrictionStallDetection) -> None:
    # Every number below is exactly what Agent 2 already computed
    # (elapsed_days, percentile_rank, excess_days_vs_median /
    # excess_count_vs_median, cohort.n, cohort.confidence) -- only the
    # words around them changed, from statistical terms (percentile,
    # median, n, confidence tier) to plain comparisons a non-technical
    # user can read at a glance. See i18n.py's unusualness_phrase(),
    # days_vs_typical_phrase(), count_vs_typical_phrase(), and
    # cohort_basis_caption() for the exact wording. Plain st.markdown
    # rather than st.metric() -- normal body-text size, not a big stat
    # display.
    cols = st.columns(3)
    if isinstance(detection, DelayStallDetection):
        cols[0].markdown(f"**{t('elapsed_days_metric')}**  \n{detection.elapsed_days} {t('days_suffix')}")
        if detection.percentile_rank is not None:
            cols[1].markdown(f"**{t('how_unusual_metric')}**  \n{unusualness_phrase(detection.percentile_rank)}")
        if detection.excess_days_vs_median is not None:
            label = extra_time_metric_label(detection.cohort.benchmark_semantics)
            phrase = days_vs_typical_phrase(detection.excess_days_vs_median, detection.cohort.benchmark_semantics)
            cols[2].markdown(f"**{label}**  \n{phrase}")
        st.caption(
            f"{interval_state_label(detection.interval_state)} · "
            f"{benchmark_semantics_label(detection.cohort.benchmark_semantics)} "
            f"({cohort_basis_caption(detection.cohort.n, detection.cohort.confidence)})"
        )
    else:
        cols[0].markdown(f"**{t('observed_count_metric')}**  \n{detection.observed_count}")
        if detection.percentile_rank is not None:
            cols[1].markdown(f"**{t('how_unusual_metric')}**  \n{unusualness_phrase(detection.percentile_rank)}")
        if detection.excess_count_vs_median is not None:
            label = extra_count_metric_label(detection.cohort.benchmark_semantics)
            phrase = count_vs_typical_phrase(detection.excess_count_vs_median, detection.cohort.benchmark_semantics)
            cols[2].markdown(f"**{label}**  \n{phrase}")
        st.caption(
            f"{benchmark_semantics_label(detection.cohort.benchmark_semantics)} "
            f"({cohort_basis_caption(detection.cohort.n, detection.cohort.confidence)})"
        )


def _render_steps_content(steps: list[NextStep], placeholder: str) -> None:
    if not steps:
        st.caption(placeholder)
        return
    for step in steps:
        st.markdown(f"- {step.text} _( {grounding_strength_label(step.grounding_strength)} )_")


def _render_learn_more(explanation: DeveloperExplanation, kb: KnowledgeBase) -> None:
    """"Learn more about this finding" -- every source behind this one
    finding's own grounded explanation, as plain links."""
    if explanation.grounding_status != GroundingStatus.GROUNDED:
        return
    entry = kb_entry_by_id(kb, explanation.knowledge_base_entry_id)
    if entry is None or not entry.sources:
        return
    st.markdown(f"**{t('learn_more_this_finding')}**")
    for source in entry.sources:
        st.markdown(f"- [{source.title}]({source.url})")


def _render_source_grounding(explanation: DeveloperExplanation, kb: KnowledgeBase) -> None:
    st.markdown(f"**{t('source_and_grounding')}**")
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
    with st.expander(_card_label(detection), expanded=False):
        _render_metrics(detection)
        _render_learn_more(explanation, kb)

        what_means_heading = (
            t("no_entry_heading")
            if explanation.grounding_status == GroundingStatus.NO_ENTRY_AVAILABLE
            else t("what_this_usually_means")
        )

        st.markdown(f"**{t('what_data_shows')}**")
        st.write(explanation.what_the_data_shows)

        st.markdown(f"**{what_means_heading}**")
        st.write(explanation.what_this_usually_means)

        st.markdown(f"**{t('steps_you_can_take')}**")
        _render_steps_content(explanation.developer_actionable_steps, t("no_developer_steps"))

        st.markdown(f"**{t('steps_depend_on_city')}**")
        _render_steps_content(explanation.city_dependent_steps, t("no_city_steps"))

        if explanation.limitations:
            st.markdown(f"**{t('cannot_tell')}**")
            for item in explanation.limitations:
                st.markdown(f"- {item}")

        if detection.caveats:
            st.markdown(f"**{t('caveats')}**")
            for caveat in detection.caveats:
                st.markdown(f"- {caveat}")

        st.divider()
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
