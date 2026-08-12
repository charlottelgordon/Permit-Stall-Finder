"""Agent 3 — Developer Explainer.

Consumes Agent 2's StallAssessment -- nothing else -- and produces a
DeveloperExplanationSet: one DeveloperExplanation per detection, five
sections each, plus Agent 2's coverage_gaps passed through unchanged.

Never recalculates severity, cohort statistics, or percentile ranks --
every number in a DeveloperExplanation is copied from the StallDetection
that produced it. Never invents a cause: section 2 (what this usually
means) comes only from a knowledge_base.loader.lookup() result; when no
entry matches, GroundingStatus.NO_ENTRY_AVAILABLE is returned with the
fixed fallback text, not a best guess.
"""

from __future__ import annotations

from datetime import datetime, timezone

from permit_stall_finder.knowledge_base.loader import KnowledgeBase, default_knowledge_base, lookup
from permit_stall_finder.rendering.fact_renderer import render_what_the_data_shows
from permit_stall_finder.schema.developer_explanation import (
    DISCLAIMER,
    NO_ENTRY_FALLBACK_TEXT,
    DeveloperExplanation,
    DeveloperExplanationSet,
    GroundingStatus,
)
from permit_stall_finder.schema.stall_detection import (
    DelayStallDetection,
    FrictionStallDetection,
    StallAssessment,
)


def explain_detection(
    detection: DelayStallDetection | FrictionStallDetection,
    knowledge_base: KnowledgeBase,
    now: datetime | None = None,
) -> DeveloperExplanation:
    now = now or datetime.now(timezone.utc)

    what_the_data_shows = render_what_the_data_shows(detection)

    entry = lookup(knowledge_base, detection)

    limitations = list(detection.caveats) + list(detection.cannot_infer)

    if entry is None:
        return DeveloperExplanation(
            permit_number=detection.permit_number,
            stall_category=detection.category,
            generated_at=now,
            what_the_data_shows=what_the_data_shows,
            what_this_usually_means=NO_ENTRY_FALLBACK_TEXT,
            grounding_status=GroundingStatus.NO_ENTRY_AVAILABLE,
            knowledge_base_entry_id=None,
            developer_actionable_steps=[],
            city_dependent_steps=[],
            limitations=limitations,
            disclaimer=DISCLAIMER,
            source_detection_category=detection.category,
            source_detection_severity=detection.severity,
            source_percentile_rank=detection.percentile_rank,
            kb_entry_version=None,
            kb_entry_last_reviewed=None,
        )

    return DeveloperExplanation(
        permit_number=detection.permit_number,
        stall_category=detection.category,
        generated_at=now,
        what_the_data_shows=what_the_data_shows,
        what_this_usually_means=entry.explanation,
        grounding_status=GroundingStatus.GROUNDED,
        knowledge_base_entry_id=entry.entry_id,
        developer_actionable_steps=list(entry.developer_actionable_steps),
        city_dependent_steps=list(entry.city_dependent_steps),
        limitations=limitations + list(entry.caveats),
        disclaimer=DISCLAIMER,
        source_detection_category=detection.category,
        source_detection_severity=detection.severity,
        source_percentile_rank=detection.percentile_rank,
        kb_entry_version=entry.kb_version,
        kb_entry_last_reviewed=entry.last_reviewed,
    )


def explain_assessment(
    assessment: StallAssessment,
    knowledge_base: KnowledgeBase | None = None,
    now: datetime | None = None,
) -> DeveloperExplanationSet:
    now = now or datetime.now(timezone.utc)
    knowledge_base = knowledge_base or default_knowledge_base()

    explanations = [explain_detection(d, knowledge_base, now) for d in assessment.detections]

    return DeveloperExplanationSet(
        permit_number=assessment.permit_number,
        generated_at=now,
        source_stall_assessment_generated_at=assessment.generated_at,
        explanations=explanations,
        coverage_gaps=list(assessment.coverage_gaps),
        disclaimer=DISCLAIMER,
    )
