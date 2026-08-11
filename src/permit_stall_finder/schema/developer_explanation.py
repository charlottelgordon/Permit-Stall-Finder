"""Agent 3's output contract and the knowledge-base contract it's grounded
in. See research/AGENT3_DESIGN.md for full design rationale.

Every DeveloperExplanation is built from exactly two sources, never blended
and never anything else: (1) the StallDetection it explains (section 1,
"what the data shows" -- rendering/fact_renderer.py), and (2) a
KnowledgeBaseEntry looked up by category (and, where a more specific match
exists, by status/result/track -- knowledge_base/loader.py). If no entry
matches, GroundingStatus.NO_ENTRY_AVAILABLE is a first-class result, not an
error path -- Agent 3 says it cannot provide a reliable interpretation
rather than inventing one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum

from permit_stall_finder.schema.stall_detection import (
    DelayStallDetection,
    FrictionStallDetection,
    Severity,
    StallCategory,
)

DISCLAIMER = (
    "This explanation is informational only and is not an official "
    "determination by the Los Angeles Department of Building and Safety "
    "(LADBS). Confirm current status directly with LADBS."
)

NO_ENTRY_FALLBACK_TEXT = (
    "No approved knowledge-base entry exists for this stall pattern. This "
    "tool cannot currently provide a reliable general-process "
    "interpretation for it. Consider contacting LADBS directly about this "
    "permit's status."
)


class GroundingStatus(str, Enum):
    GROUNDED = "grounded"
    NO_ENTRY_AVAILABLE = "no_entry_available"


class VerificationStatus(str, Enum):
    """Per-source confidence that a citation's content reflects the actual
    primary text, not just how it was found."""

    DIRECT_PRIMARY_FETCH = "direct_primary_fetch"
    # The page/document content was read directly.
    SEARCH_SYNTHESIS_DETAILED = "search_synthesis_detailed"
    # Specific, quote-like content surfaced via search, not a full direct
    # fetch of the primary document (e.g. the source blocks scraping).
    SEARCH_SYNTHESIS_GENERAL = "search_synthesis_general"
    # General/paraphrased content via search, not specific enough to be
    # confident it reflects exact current wording.
    UNVERIFIED = "unverified"
    # Could not be confirmed at all. An entry should not rely on an
    # UNVERIFIED source for a specific factual claim -- see AGENT3_DESIGN.md
    # §9 for the LAMC Sec. 106.4.4.3 citation dropped for exactly this
    # reason rather than shipped unverified.


class SourceType(str, Enum):
    PRIMARY_MUNICIPAL_CODE = "primary_municipal_code"
    PRIMARY_OFFICIAL_AGENCY = "primary_official_agency"
    SECONDARY_UNVERIFIED = "secondary_unverified"


class KBConfidence(str, Enum):
    VERIFIED_DIRECT_FETCH = "verified_direct_fetch"
    VERIFIED_SEARCH_SYNTHESIS = "verified_search_synthesis"
    GENERIC_LOW_CONFIDENCE = "generic_low_confidence"


class GroundingStrength(str, Enum):
    """Per-next-step honesty label -- distinct from a source's
    VerificationStatus. A step can be built on a well-verified source and
    still only be a CAUTIOUS_SYNTHESIS if the source states a rule but not
    this specific action."""

    DIRECTLY_SUPPORTED = "directly_supported"
    # The cited source explicitly describes this as a step/action.
    CAUTIOUS_SYNTHESIS = "cautious_synthesis"
    # A reasonable action inferred from a sourced rule or process
    # description, but not itself stated verbatim in the source.
    NOT_AVAILABLE = "not_available"
    # No grounded step exists for this entry/category at all.


@dataclass(frozen=True)
class NextStep:
    text: str
    grounding_strength: GroundingStrength


@dataclass(frozen=True)
class KnowledgeBaseSource:
    title: str
    url: str
    publisher: str
    source_type: SourceType
    retrieved_date: date
    verification_status: VerificationStatus


@dataclass(frozen=True)
class KnowledgeBaseEntry:
    entry_id: str
    stall_category: StallCategory
    applies_to_dimension: str  # "status_desc" | "result_family" | "track" | "category_generic"
    applies_to_value: str | None

    explanation: str  # section 2 content -- no permit-specific interpolation, ever
    developer_actionable_steps: list[NextStep]
    city_dependent_steps: list[NextStep]

    sources: list[KnowledgeBaseSource]  # never empty
    caveats: list[str]
    confidence: KBConfidence

    kb_version: str
    last_reviewed: date


@dataclass(frozen=True)
class DeveloperExplanation:
    permit_number: str
    stall_category: StallCategory
    generated_at: datetime

    # 1. WHAT THE DATA SHOWS
    what_the_data_shows: str

    # 2. WHAT THIS USUALLY MEANS
    what_this_usually_means: str
    grounding_status: GroundingStatus
    knowledge_base_entry_id: str | None

    # 3 & 4. NEXT STEPS
    developer_actionable_steps: list[NextStep]
    city_dependent_steps: list[NextStep]

    # 5. LIMITATIONS / WHAT WE CANNOT TELL
    limitations: list[str]

    disclaimer: str

    # Traceability -- never recomputed, only carried
    source_detection_category: StallCategory
    source_detection_severity: Severity
    source_percentile_rank: float | None
    kb_entry_version: str | None
    kb_entry_last_reviewed: date | None


@dataclass(frozen=True)
class DeveloperExplanationSet:
    permit_number: str
    generated_at: datetime
    source_stall_assessment_generated_at: datetime

    explanations: list[DeveloperExplanation]
    coverage_gaps: list[str]  # passed through from Agent 2 unchanged
    disclaimer: str = DISCLAIMER
