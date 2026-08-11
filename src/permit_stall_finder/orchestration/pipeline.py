"""End-to-end orchestration: permit number -> PermitAnalysisResult.

This module performs NO analytical reasoning. It does not compute a
statistic, look up a knowledge-base entry, classify a severity, or render
any fact-describing prose -- every one of those already happened inside
Agent 1, 2, or 3, and this module only calls them in sequence and carries
their outputs forward unchanged. The one piece of logic here,
`classify_outcome()`, is a plain if/elif over fields Agents 1-3 already
computed (whether any detection exists, whether any coverage gap exists) --
categorization/bookkeeping for presentation, not new analysis. It never
inspects a percentile, a cohort, or a knowledge-base entry itself.

Agent 2 consumes Agent 1's PermitJourney exactly as Agent 1 produced it.
Agent 3 consumes Agent 2's StallAssessment exactly as Agent 2 produced it.
Nothing is recalculated, reinterpreted, or edited in transit -- this is
verified by test_orchestration.py's identity checks against the standalone
agents, not just asserted here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

import duckdb

from permit_stall_finder.agents.developer_explainer import explain_assessment
from permit_stall_finder.agents.journey_reconstructor import reconstruct_journey
from permit_stall_finder.agents.stall_detector import assess_stalls
from permit_stall_finder.ingestion import inspections, permits
from permit_stall_finder.knowledge_base.loader import KnowledgeBase, default_knowledge_base
from permit_stall_finder.schema.developer_explanation import DeveloperExplanationSet
from permit_stall_finder.schema.journey import DataQualityFlag, PermitJourney
from permit_stall_finder.schema.stall_detection import SeverityThresholds, StallAssessment
from permit_stall_finder import config


class AnalysisOutcome(str, Enum):
    """A presentation-layer categorization of Agent 2's already-final
    output -- never a new determination. Computed by classify_outcome()."""

    NO_MATERIAL_STALL_DETECTED = "no_material_stall_detected"
    # Every applicable category was actually assessed (no coverage gaps)
    # and none reached Agent 2's reporting threshold. A genuine clean read,
    # not an absence of information.
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    # No detections were produced, but at least one category could not be
    # responsibly assessed (insufficient cohort, zero-variance cohort,
    # ineligible/exempt coverage, insufficient exposure, or the permit
    # wasn't found at all). Must never be read as "no problem found."
    STALL_DETECTED = "stall_detected"
    # At least one detection was produced. Takes priority even if other
    # categories separately hit a coverage gap -- a confirmed stall doesn't
    # become less real because something else couldn't be assessed.


class PipelineStage(str, Enum):
    JOURNEY_RECONSTRUCTION = "journey_reconstruction"
    STALL_DETECTION = "stall_detection"
    DEVELOPER_EXPLANATION = "developer_explanation"


class PipelineExecutionError(RuntimeError):
    """Wraps an unexpected failure with which stage it happened in and
    which permit was being analyzed. Never raised for a permit that simply
    wasn't found, has no inspections, or produced no detections -- those
    are all valid, successfully-completed results (see AnalysisOutcome).
    This is only for actual infrastructure/execution failures (e.g. a
    network error reaching the source datasets), which must propagate
    clearly rather than be silently coerced into looking like a normal
    "no stall" or "insufficient evidence" result."""

    def __init__(self, permit_number: str, stage: PipelineStage, original: Exception):
        self.permit_number = permit_number
        self.stage = stage
        self.original = original
        super().__init__(
            f"Pipeline failed for permit {permit_number!r} during {stage.value}: "
            f"{type(original).__name__}: {original}"
        )


def classify_outcome(stall_assessment: StallAssessment) -> AnalysisOutcome:
    if stall_assessment.detections:
        return AnalysisOutcome.STALL_DETECTED
    if stall_assessment.coverage_gaps:
        return AnalysisOutcome.INSUFFICIENT_EVIDENCE
    return AnalysisOutcome.NO_MATERIAL_STALL_DETECTED


@dataclass(frozen=True)
class PermitAnalysisResult:
    permit_number: str
    analyzed_at: datetime

    journey: PermitJourney
    stall_assessment: StallAssessment
    developer_explanations: DeveloperExplanationSet

    outcome: AnalysisOutcome
    coverage_gaps: list[str]
    data_quality_flags: list[DataQualityFlag]

    source_provenance: dict[str, object]
    """Chain-of-custody summary across all three stages: dataset-level
    provenance from Agent 1 plus each stage's own generated_at and the
    backward-link it recorded to the stage before it -- so a caller can
    confirm (as verify_provenance_chain() does) that Agent 2 really
    consumed this exact PermitJourney and Agent 3 really consumed this
    exact StallAssessment, not a stale or substituted one."""


def verify_provenance_chain(result: PermitAnalysisResult) -> None:
    """Defensive integrity check, not analysis: confirms Agent 2 actually
    ran against this PermitJourney and Agent 3 actually ran against this
    StallAssessment, by comparing the backward-link timestamps each agent
    already records. Raises AssertionError if the chain is broken -- under
    normal orchestration (see run_pipeline) this can only happen if the
    module is misused, e.g. by manually swapping in a stage's output from
    a different run."""
    if result.stall_assessment.source_permit_journey_generated_at != result.journey.generated_at:
        raise AssertionError(
            "Provenance chain broken: StallAssessment was not generated from this PermitJourney "
            f"(expected source_permit_journey_generated_at={result.journey.generated_at}, "
            f"got {result.stall_assessment.source_permit_journey_generated_at})"
        )
    if (
        result.developer_explanations.source_stall_assessment_generated_at
        != result.stall_assessment.generated_at
    ):
        raise AssertionError(
            "Provenance chain broken: DeveloperExplanationSet was not generated from this "
            f"StallAssessment (expected source_stall_assessment_generated_at="
            f"{result.stall_assessment.generated_at}, got "
            f"{result.developer_explanations.source_stall_assessment_generated_at})"
        )


def run_pipeline(
    conn: duckdb.DuckDBPyConnection,
    permit_number: str,
    *,
    fetch_permit_row=permits.fetch_raw_permit_row,
    fetch_inspection_rows=inspections.fetch_raw_inspection_rows,
    sample_size: int = config.DEFAULT_COHORT_SAMPLE_SIZE,
    thresholds: SeverityThresholds = SeverityThresholds(),
    knowledge_base: KnowledgeBase | None = None,
    now: datetime | None = None,
) -> PermitAnalysisResult:
    """Agent 1 -> Agent 2 -> Agent 3, in sequence, with no transformation
    of any agent's output in between. Every keyword argument here is an
    injection point that already existed on the underlying agent (fixture
    fetchers for Agent 1, sample_size/thresholds for Agent 2, an explicit
    KnowledgeBase for Agent 3) -- the orchestrator adds no new
    configuration surface of its own, only threads existing ones through."""
    now = now or datetime.now(timezone.utc)
    knowledge_base = knowledge_base or default_knowledge_base()

    try:
        journey = reconstruct_journey(
            conn,
            permit_number,
            fetch_permit_row=fetch_permit_row,
            fetch_inspection_rows=fetch_inspection_rows,
            observed_at=now,
        )
    except Exception as exc:  # noqa: BLE001 -- intentionally broad: any failure here is an
        # infrastructure/execution problem, not a data-shape one; Agent 1 itself already
        # handles "permit not found" and similar cases without raising.
        raise PipelineExecutionError(permit_number, PipelineStage.JOURNEY_RECONSTRUCTION, exc) from exc

    try:
        stall_assessment = assess_stalls(journey, now=now, thresholds=thresholds, sample_size=sample_size)
    except Exception as exc:  # noqa: BLE001
        raise PipelineExecutionError(permit_number, PipelineStage.STALL_DETECTION, exc) from exc

    try:
        developer_explanations = explain_assessment(stall_assessment, knowledge_base, now=now)
    except Exception as exc:  # noqa: BLE001
        raise PipelineExecutionError(permit_number, PipelineStage.DEVELOPER_EXPLANATION, exc) from exc

    outcome = classify_outcome(stall_assessment)

    source_provenance = {
        "journey": {
            "generated_at": journey.generated_at,
            "match_status": journey.match_status,
            **journey.source_provenance,
        },
        "stall_assessment": {
            "generated_at": stall_assessment.generated_at,
            "source_permit_journey_generated_at": stall_assessment.source_permit_journey_generated_at,
        },
        "developer_explanations": {
            "generated_at": developer_explanations.generated_at,
            "source_stall_assessment_generated_at": developer_explanations.source_stall_assessment_generated_at,
            "knowledge_base_version": knowledge_base.kb_version,
        },
    }

    result = PermitAnalysisResult(
        permit_number=permit_number,
        analyzed_at=now,
        journey=journey,
        stall_assessment=stall_assessment,
        developer_explanations=developer_explanations,
        outcome=outcome,
        coverage_gaps=list(stall_assessment.coverage_gaps),
        data_quality_flags=list(journey.data_quality_flags),
        source_provenance=source_provenance,
    )
    verify_provenance_chain(result)
    return result
