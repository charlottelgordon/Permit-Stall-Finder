"""Pure, Streamlit-free presentation helpers: fixed short labels for
existing enum values, a severity tally for the top-level summary sentence,
and a read-only knowledge-base entry lookup by the id Agent 3 already
selected.

Nothing here decides anything Agents 1-3 didn't already decide. See
research/UI_DESIGN.md for the design this implements and the specific
constraints on each function (especially kb_entry_by_id, which must not
perform its own matching -- it only resolves an id string Agent 3 already
chose into the full KnowledgeBaseEntry object for display).
"""

from __future__ import annotations

from collections import Counter

from permit_stall_finder.knowledge_base.loader import KnowledgeBase
from permit_stall_finder.schema.developer_explanation import (
    GroundingStatus,
    GroundingStrength,
    KnowledgeBaseEntry,
    VerificationStatus,
)
from permit_stall_finder.schema.journey import DataQualityFlag, MatchStatus
from permit_stall_finder.schema.stall_detection import (
    BenchmarkSemantics,
    IntervalState,
    Severity,
    StallCategory,
)
from permit_stall_finder.orchestration.pipeline import AnalysisOutcome

CATEGORY_LABELS: dict[StallCategory, str] = {
    StallCategory.PRE_ISSUANCE_STATUS_DWELL: "Time in current pre-issuance status",
    StallCategory.ISSUANCE_TO_FIRST_INSPECTION_GAP: "Gap from issuance to first inspection",
    StallCategory.NO_INSPECTION_SINCE_ISSUANCE: "No inspection on record since issuance",
    StallCategory.INTER_INSPECTION_GAP: "Gap between inspections",
    StallCategory.INACTIVITY_SINCE_LAST_INSPECTION: "Inactivity since last inspection",
    StallCategory.FINALIZATION_GAP: "Gap before finalization",
    StallCategory.REPEATED_CORRECTIONS: "Repeated corrections",
    StallCategory.REPEATED_NOT_READY_OUTCOMES: "Repeated 'not ready' inspection outcomes",
    StallCategory.REPEATED_CANCELLATIONS: "Repeated cancelled inspections",
}

SEVERITY_LABELS: dict[Severity, str] = {
    Severity.WATCH: "Watch",
    Severity.ELEVATED: "Elevated",
    Severity.SEVERE: "Severe",
    Severity.UNSCORED: "Unscored",
}

# Muted, non-alarmist palette -- no pure red. See UI_DESIGN.md decision 3.
SEVERITY_COLORS: dict[Severity, str] = {
    Severity.WATCH: "#5B7A99",       # muted blue
    Severity.ELEVATED: "#B8860B",    # muted amber
    Severity.SEVERE: "#B0553F",      # muted terracotta, not pure red
    Severity.UNSCORED: "#888888",    # grey
}

MATCH_STATUS_LABELS: dict[MatchStatus, str] = {
    MatchStatus.UNISSUED: "Not yet issued",
    MatchStatus.ISSUED_WITH_INSPECTIONS: "Issued, with inspections on record",
    MatchStatus.ISSUED_NO_INSPECTIONS_FOUND: "Issued, no inspections found",
    MatchStatus.PERMIT_NOT_FOUND: "Permit not found in the source dataset",
}

# Paraphrased directly from each flag's own docstring in schema/journey.py --
# no new claims, just shorter captions for display.
DATA_QUALITY_FLAG_LABELS: dict[DataQualityFlag, str] = {
    DataQualityFlag.STATUS_ISSUE_DATE_INCONSISTENT: (
        "The city's own permit record has a status and an issue date that don't quite line up "
        "for this permit -- that's a mismatch in the source data itself, not something this tool "
        "introduced."
    ),
    DataQualityFlag.INSPECTION_MATCH_UNCERTAIN_FOR_TYPE: (
        "For this permit type, inspection records don't always link up reliably with permit "
        "records in the city's data -- so if no inspection shows up here, that doesn't "
        "necessarily mean one didn't happen."
    ),
    DataQualityFlag.FIRST_OBSERVATION: (
        "This is the first time Permit Check LA has looked up this permit number, so we can't "
        "tell you about its history of stalls before today. This tool works by comparing "
        "multiple Los Angeles Department of Building and Safety datasets each time a permit is "
        "searched -- there's no earlier snapshot yet for this one to compare against."
    ),
}

BENCHMARK_SEMANTICS_LABELS: dict[BenchmarkSemantics, str] = {
    BenchmarkSemantics.ACTIVE_PEER_DWELL: "Compared to other permits stuck at this same step right now",
    BenchmarkSemantics.COMPLETED_INTERVAL: "Compared to how long this step usually takes once it's done",
}

INTERVAL_STATE_LABELS: dict[IntervalState, str] = {
    IntervalState.ONGOING: "Still in progress",
    IntervalState.COMPLETED: "This step is finished",
}

OUTCOME_CLEAN_TEXT = "No material stall signals identified"
OUTCOME_INSUFFICIENT_TEXT = "Insufficient evidence to reliably assess this permit"

GROUNDING_STRENGTH_LABELS: dict[GroundingStrength, str] = {
    GroundingStrength.DIRECTLY_SUPPORTED: "directly supported by source",
    GroundingStrength.CAUTIOUS_SYNTHESIS: "reasoned suggestion",
    GroundingStrength.NOT_AVAILABLE: "not available",
}

VERIFICATION_STATUS_LABELS: dict[VerificationStatus, str] = {
    VerificationStatus.DIRECT_PRIMARY_FETCH: "Directly verified against the primary source",
    VerificationStatus.SEARCH_SYNTHESIS_DETAILED: "Sourced via detailed search synthesis, not a full direct fetch",
    VerificationStatus.SEARCH_SYNTHESIS_GENERAL: "Sourced via general search synthesis, not a full direct fetch",
    VerificationStatus.UNVERIFIED: "Not verified",
}


def summarize_severity_counts(detections) -> str:
    """Tallies detections by their own already-assigned Severity -- pure
    counting of existing labels, never a new severity judgment. Returns
    e.g. "3 severe findings · 1 watch finding", omitting zero-count tiers,
    ordered SEVERE -> ELEVATED -> WATCH."""
    counts = Counter(d.severity for d in detections)
    order = [Severity.SEVERE, Severity.ELEVATED, Severity.WATCH]
    parts = []
    for sev in order:
        n = counts.get(sev, 0)
        if n:
            label = SEVERITY_LABELS[sev].lower()
            noun = "finding" if n == 1 else "findings"
            parts.append(f"{n} {label} {noun}")
    return " · ".join(parts) if parts else OUTCOME_CLEAN_TEXT


def summarize_severity_counts_compact(detections) -> str:
    """Compact table-cell version of summarize_severity_counts() above,
    e.g. "3 severe, 1 watch" instead of "3 severe findings · 1 watch
    finding" -- same tally, same ordering, just shorter for a narrow
    results-table column."""
    counts = Counter(d.severity for d in detections)
    order = [Severity.SEVERE, Severity.ELEVATED, Severity.WATCH]
    parts = []
    for sev in order:
        n = counts.get(sev, 0)
        if n:
            parts.append(f"{n} {SEVERITY_LABELS[sev].lower()}")
    return ", ".join(parts) if parts else OUTCOME_CLEAN_TEXT


def outcome_headline(result) -> str:
    if result.outcome == AnalysisOutcome.NO_MATERIAL_STALL_DETECTED:
        return OUTCOME_CLEAN_TEXT
    if result.outcome == AnalysisOutcome.INSUFFICIENT_EVIDENCE:
        return OUTCOME_INSUFFICIENT_TEXT
    return summarize_severity_counts(result.stall_assessment.detections)


def kb_entry_by_id(kb: KnowledgeBase, entry_id: str | None) -> KnowledgeBaseEntry | None:
    """Read-only resolution of the id Agent 3 already selected
    (DeveloperExplanation.knowledge_base_entry_id) into the full entry
    object, for display only. This is an id-equality lookup over the
    already-loaded, already-decided KnowledgeBase.entries list -- it does
    not run knowledge_base.loader.lookup() (category/dimension matching)
    and cannot select a different entry than the one Agent 3 already
    chose. Returns None if entry_id is None (the NO_ENTRY_AVAILABLE case)
    or, defensively, if the id isn't found."""
    if entry_id is None:
        return None
    return next((e for e in kb.entries if e.entry_id == entry_id), None)


def has_mixed_grounding(explanations) -> bool:
    statuses = {e.grounding_status for e in explanations}
    return GroundingStatus.GROUNDED in statuses and GroundingStatus.NO_ENTRY_AVAILABLE in statuses
