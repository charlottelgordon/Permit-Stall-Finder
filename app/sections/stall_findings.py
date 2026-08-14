"""Sections D+E — stall findings and their developer explanations.

One card per detection, zipped 1:1 with its DeveloperExplanation. This is
safe because explain_assessment() builds developer_explanations.explanations
by iterating stall_assessment.detections directly, in order -- the two
lists are guaranteed the same length and order (see UI_DESIGN.md §3).

Every sentence a card shows is either a structured field displayed as-is
(severity, elapsed_days, percentile_rank, ...) or one of Agent 3's
pre-composed section strings. This module never concatenates numbers into
new prose of its own (UI_DESIGN.md decision "no UI-composed analytical
sentences from raw numbers").

Phase 18: each card is now one single st.expander, collapsed by default,
labeled with a severity dot + category + severity word + whether this
specific finding is still ongoing (e.g. "🔴 Gap between inspections —
SEVERE · Completed") -- so a user sees every finding's headline,
severity, and ongoing/concluded status at a glance and opens only the
ones they care about. Streamlit doesn't allow expanders nested inside
expanders, so everything that used to be its own small expander inside
the card (What the data shows / What this usually means / Steps.../
Source & grounding) is now plain content once a card itself is opened
-- there's nothing left to additionally collapse one level down. The
metrics row also switched from st.metric() (a large, bold stat display)
to plain markdown text at normal body size.

"What the data shows" is no longer rendered here at all (removed as
redundant with the metrics row above it) -- explanation.
what_the_data_shows still exists and is still shown in the downloadable
report (report_export.py), just not on this on-screen card. Where that
removed prose named a specific inspection (e.g. "between two recorded
inspections (Special/Order Compliance -> Interior/Exterior Lathing)"),
the same information is now a small caption directly under the
"Elapsed days" stat instead, read from detection.stage_label -- a
structured field, not text parsed out of prose (see
_stage_context_caption()).

Cards are ordered ongoing-first, already-concluded-last (see
_is_ongoing()/render()'s sort) -- someone checking in on an active
project cares most about what's still actively stalled right now, not
a gap between two inspections that both already happened.

Each card's own "What we cannot tell from this data" section
(explanation.limitations, per-finding) is likewise no longer rendered
here -- it repeated the same handful of structural caveats on every
card (this tool can't attribute cause or fault) rather than saying
anything specific to that one finding. render() now shows a single
fixed disclaimer caption once, below every card, covering the same
ground (see t("findings_cause_disclaimer")). report_export.py is
untouched and still lists explanation.limitations per finding in the
downloadable report.

"Learn more about this finding" and "Source & grounding" -- two
sections that both listed the same knowledge-base entry's sources at
different levels of detail -- are now one combined section
(_render_sources_section()), under the "Source & grounding" heading,
using the fuller title+publisher+verification-status listing
throughout. _render_card() places it last, below Caveats, since it's
supporting evidence for the finding rather than part of the finding's
own explanation. Its own "Caveats on this guidance" sub-part (the KB
entry's caveats, distinct from detection.caveats above it) is a single
st.caption() paragraph now, not a bulleted list -- smaller text,
several caveats read as one continuous note rather than a formal list.

render()'s mixed_grounding_caption line (a caption below the "Where
this project has stalled" header noting that some findings are
KB-backed and some aren't) is removed -- each card already states its
own grounding status individually (a GROUNDED card via
_render_sources_section(), a NO_ENTRY_AVAILABLE one via its own
heading below), so the blanket caption above the cards was telling the
user something every card already tells them itself.

_render_card() short-circuits after the "No authoritative guidance
available" block for a NO_ENTRY_AVAILABLE explanation, skipping Steps
you can take / Steps that depend on the city / Source & grounding
entirely rather than rendering each of those as its own "no
guidance"/"no entry" restatement -- explain_detection() guarantees all
three are empty whenever there's no KB entry (see
developer_explainer.py), so showing them added nothing past the first
sentence. detection.caveats (a structural field, distinct from KB
grounding) still renders when present, since those aren't guaranteed
empty in this case.
"""

from __future__ import annotations

import streamlit as st

from formatting import kb_entry_by_id
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
    IntervalState,
    LifecycleStage,
    Severity,
    StallAssessment,
    StallCategory,
)

_SEVERITY_DOT = {
    Severity.SEVERE: "🔴",
    Severity.ELEVATED: "🟠",
    Severity.WATCH: "🟡",
    Severity.UNSCORED: "⚪",
}


def _is_ongoing(detection: DelayStallDetection | FrictionStallDetection) -> bool:
    """Whether this specific finding's own measurement window is still
    open right now, not whether the permit as a whole is ongoing.
    DelayStallDetection carries this directly as interval_state (e.g.
    INTER_INSPECTION_GAP is always a COMPLETED, already-concluded gap
    between two past inspections -- never ongoing, by definition of
    what that category measures). FrictionStallDetection carries the
    analogous concept as lifecycle_stage: whether the permit's own
    lifecycle had already ended when the friction count was measured."""
    if isinstance(detection, DelayStallDetection):
        return detection.interval_state == IntervalState.ONGOING
    return detection.lifecycle_stage == LifecycleStage.ONGOING


def _card_label(detection: DelayStallDetection | FrictionStallDetection) -> str:
    dot = _SEVERITY_DOT[detection.severity]
    ongoing_label = t("card_label_ongoing") if _is_ongoing(detection) else t("card_label_completed")
    return (
        f"{dot} {category_label(detection.category)} — {severity_label(detection.severity).upper()} "
        f"· {ongoing_label}"
    )


def _stage_context_caption(detection: DelayStallDetection | FrictionStallDetection) -> str | None:
    """Small text under the "Elapsed days" stat naming exactly which
    inspection(s) this gap sits between/since -- reads detection.
    stage_label directly (a structured field Agent 2 already set, not
    parsed out of the now-removed "What the data shows" prose that used
    to be the only place this showed up). Only these two categories set
    stage_label to something genuinely inspection-specific worth
    surfacing this way -- ISSUANCE_TO_FIRST_INSPECTION_GAP and
    NO_INSPECTION_SINCE_ISSUANCE set it to an internal category tag, not
    a name (confirmed by reading stall_detector.py directly); PRE_
    ISSUANCE_STATUS_DWELL's stage_label is the current status_desc,
    already shown in quick_glance.py's own "Permit status" block, so
    repeating it here would be exactly the duplication this whole app
    has otherwise been careful to avoid. FrictionStallDetection has no
    stage_label at all -- returns None for it unconditionally."""
    if not isinstance(detection, DelayStallDetection):
        return None
    if detection.category == StallCategory.INTER_INSPECTION_GAP:
        return t("stage_context_between").format(stage=detection.stage_label.replace(" -> ", " → "))
    if detection.category == StallCategory.INACTIVITY_SINCE_LAST_INSPECTION:
        return t("stage_context_most_recent").format(stage=detection.stage_label)
    return None


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
        stage_context = _stage_context_caption(detection)
        if stage_context:
            cols[0].caption(stage_context)
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


def _render_sources_section(explanation: DeveloperExplanation, kb: KnowledgeBase) -> None:
    """"Learn more about this finding" and "Source & grounding" combined --
    both used to list the same knowledge-base entry's sources, just at two
    different levels of detail (plain title links vs. title+publisher+
    verification-status+retrieved-date). One section now, under a single
    heading, using the fuller listing throughout; render() places this
    last in every card since it's supporting evidence, not part of the
    finding's own explanation."""
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
        st.caption(" ".join(entry.caveats))


def _render_card(
    detection: DelayStallDetection | FrictionStallDetection,
    explanation: DeveloperExplanation,
    kb: KnowledgeBase,
) -> None:
    with st.expander(_card_label(detection), expanded=False):
        _render_metrics(detection)
        st.divider()

        if explanation.grounding_status == GroundingStatus.NO_ENTRY_AVAILABLE:
            # Steps you can take / Steps that depend on the city / Source &
            # grounding are guaranteed empty whenever there's no KB entry
            # (explain_detection() always returns [], [], None for these --
            # see developer_explainer.py) -- each would just be its own
            # "no guidance/no entry" restatement of the same fact this
            # heading already states once. Say it once and stop.
            st.markdown(f"**{t('no_entry_heading')}**")
            st.write(explanation.what_this_usually_means)

            if detection.caveats:
                st.divider()
                st.markdown(f"**{t('caveats')}**")
                for caveat in detection.caveats:
                    st.markdown(f"- {caveat}")
            return

        st.markdown(f"**{t('what_this_usually_means')}**")
        st.write(explanation.what_this_usually_means)
        st.divider()

        st.markdown(f"**{t('steps_you_can_take')}**")
        _render_steps_content(explanation.developer_actionable_steps, t("no_developer_steps"))
        st.divider()

        st.markdown(f"**{t('steps_depend_on_city')}**")
        _render_steps_content(explanation.city_dependent_steps, t("no_city_steps"))

        if detection.caveats:
            st.divider()
            st.markdown(f"**{t('caveats')}**")
            for caveat in detection.caveats:
                st.markdown(f"- {caveat}")

        st.divider()
        _render_sources_section(explanation, kb)


def render(
    stall_assessment: StallAssessment,
    developer_explanations: DeveloperExplanationSet,
    kb: KnowledgeBase,
) -> None:
    if not stall_assessment.detections:
        return

    st.subheader(t("stall_findings_header"))

    # Ongoing findings first, already-concluded ones last (e.g. a
    # finished INTER_INSPECTION_GAP -- a gap between two inspections
    # that already both happened -- sinks below anything still actively
    # stalled right now). A stable sort on detection/explanation pairs
    # together, not on detections alone, so explanations stay correctly
    # paired with their own detection (the two lists are guaranteed
    # same-length/order per this module's own docstring, but only if
    # kept in lockstep through any reordering here too); within each
    # group, the original pipeline order is preserved.
    pairs = sorted(
        zip(stall_assessment.detections, developer_explanations.explanations),
        key=lambda pair: not _is_ongoing(pair[0]),
    )
    for detection, explanation in pairs:
        _render_card(detection, explanation, kb)

    st.caption(t("findings_cause_disclaimer"))
