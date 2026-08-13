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

Phase 15: each card is now a bordered container that's always visible
(title, severity badge, metrics, and the interval/benchmark caption --
no click required), followed by a "Learn more about this finding" link
list (moved here from next_best_action.py's old aggregated list) and then
one small expander per explanatory piece -- What the data shows / What
this usually means / Steps you can take / Steps that depend on the city /
What we cannot tell -- each collapsed by default, styled the same way
"Source & grounding" already was. There's no longer one outer expander
wrapping every card (drill_down.py calls render() directly into the right
panel now), so a user can scan every finding's headline + numbers at a
glance and only open the specific explanation they want.
"""

from __future__ import annotations

import streamlit as st

from formatting import SEVERITY_COLORS, has_mixed_grounding, kb_entry_by_id
from i18n import (
    benchmark_semantics_label,
    category_label,
    cohort_basis_caption,
    count_vs_typical_phrase,
    days_vs_typical_phrase,
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
    # Every number below is exactly what Agent 2 already computed
    # (elapsed_days, percentile_rank, excess_days_vs_median /
    # excess_count_vs_median, cohort.n, cohort.confidence) -- only the
    # words around them changed, from statistical terms (percentile,
    # median, n, confidence tier) to plain comparisons a non-technical
    # user can read at a glance. See i18n.py's unusualness_phrase(),
    # days_vs_typical_phrase(), count_vs_typical_phrase(), and
    # cohort_basis_caption() for the exact wording.
    cols = st.columns(3)
    if isinstance(detection, DelayStallDetection):
        cols[0].metric(t("elapsed_days_metric"), f"{detection.elapsed_days} {t('days_suffix')}")
        if detection.percentile_rank is not None:
            cols[1].metric(t("how_unusual_metric"), unusualness_phrase(detection.percentile_rank))
        if detection.excess_days_vs_median is not None:
            cols[2].metric(t("extra_time_metric"), days_vs_typical_phrase(detection.excess_days_vs_median))
        st.caption(
            f"{interval_state_label(detection.interval_state)} · "
            f"{benchmark_semantics_label(detection.cohort.benchmark_semantics)} "
            f"({cohort_basis_caption(detection.cohort.n, detection.cohort.confidence)})"
        )
    else:
        cols[0].metric(t("observed_count_metric"), detection.observed_count)
        if detection.percentile_rank is not None:
            cols[1].metric(t("how_unusual_metric"), unusualness_phrase(detection.percentile_rank))
        if detection.excess_count_vs_median is not None:
            cols[2].metric(t("extra_count_metric"), count_vs_typical_phrase(detection.excess_count_vs_median))
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
    finding's own grounded explanation, as plain links. Moved here from
    next_best_action.py's old aggregated cross-finding list (Phase 15)
    so a user reads a finding's sources right next to that finding,
    rather than having to cross-reference back to a list elsewhere."""
    if explanation.grounding_status != GroundingStatus.GROUNDED:
        return
    entry = kb_entry_by_id(kb, explanation.knowledge_base_entry_id)
    if entry is None or not entry.sources:
        return
    st.markdown(f"**{t('learn_more_this_finding')}**")
    for source in entry.sources:
        st.markdown(f"- [{source.title}]({source.url})")


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
        # Always visible, no click required: title, severity, the
        # metrics row, and its interval/benchmark caption.
        st.markdown(
            f"#### {category_label(detection.category)}  {_severity_badge(detection)}",
            unsafe_allow_html=True,
        )
        _render_metrics(detection)

        _render_learn_more(explanation, kb)

        what_means_heading = (
            t("no_entry_heading")
            if explanation.grounding_status == GroundingStatus.NO_ENTRY_AVAILABLE
            else t("what_this_usually_means")
        )

        with st.expander(t("what_data_shows")):
            st.write(explanation.what_the_data_shows)

        with st.expander(what_means_heading):
            st.write(explanation.what_this_usually_means)

        with st.expander(t("steps_you_can_take")):
            _render_steps_content(explanation.developer_actionable_steps, t("no_developer_steps"))

        with st.expander(t("steps_depend_on_city")):
            _render_steps_content(explanation.city_dependent_steps, t("no_city_steps"))

        if explanation.limitations:
            with st.expander(t("cannot_tell")):
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
