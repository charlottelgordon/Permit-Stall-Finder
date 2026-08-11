"""Loads and validates research/agent3_knowledge_base.json, and implements
specific-before-generic lookup (AGENT3_DESIGN.md §3, §9): a detection is
matched against the most specific key available for its category before
falling back to that category's generic entry, and to None
(NO_ENTRY_AVAILABLE) if neither exists. Matching never falls back further
than the category's own generic entry -- there is no cross-category
fallback, since that would be exactly the kind of category-only matching
this design was told to avoid.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

from permit_stall_finder.schema.developer_explanation import (
    GroundingStrength,
    KBConfidence,
    KnowledgeBaseEntry,
    KnowledgeBaseSource,
    NextStep,
    SourceType,
    VerificationStatus,
)
from permit_stall_finder.schema.stall_detection import (
    DelayStallDetection,
    FrictionStallDetection,
    StallCategory,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_KB_PATH = _REPO_ROOT / "research" / "agent3_knowledge_base.json"

LookupKey = tuple[StallCategory, str, Optional[str]]


@dataclass(frozen=True)
class KnowledgeBase:
    kb_version: str
    last_reviewed: date
    entries: list[KnowledgeBaseEntry]
    by_key: dict[LookupKey, KnowledgeBaseEntry]


def _parse_next_steps(raw: list[dict]) -> list[NextStep]:
    return [NextStep(text=s["text"], grounding_strength=GroundingStrength(s["grounding_strength"])) for s in raw]


def _parse_source(raw: dict) -> KnowledgeBaseSource:
    return KnowledgeBaseSource(
        title=raw["title"],
        url=raw["url"],
        publisher=raw["publisher"],
        source_type=SourceType(raw["source_type"]),
        retrieved_date=date.fromisoformat(raw["retrieved_date"]),
        verification_status=VerificationStatus(raw["verification_status"]),
    )


def _parse_entry(raw: dict) -> KnowledgeBaseEntry:
    return KnowledgeBaseEntry(
        entry_id=raw["entry_id"],
        stall_category=StallCategory(raw["stall_category"]),
        applies_to_dimension=raw["applies_to_dimension"],
        applies_to_value=raw["applies_to_value"],
        explanation=raw["explanation"],
        developer_actionable_steps=_parse_next_steps(raw["developer_actionable_steps"]),
        city_dependent_steps=_parse_next_steps(raw["city_dependent_steps"]),
        sources=[_parse_source(s) for s in raw["sources"]],
        caveats=raw["caveats"],
        confidence=KBConfidence(raw["confidence"]),
        kb_version=raw["kb_version"],
        last_reviewed=date.fromisoformat(raw["last_reviewed"]),
    )


def load_knowledge_base(path: Path = _KB_PATH) -> KnowledgeBase:
    with open(path) as f:
        raw = json.load(f)

    entries = [_parse_entry(e) for e in raw["entries"]]

    for entry in entries:
        if not entry.sources:
            raise ValueError(f"KB entry {entry.entry_id!r} has no sources -- every entry must cite at least one")

    by_key: dict[LookupKey, KnowledgeBaseEntry] = {}
    for entry in entries:
        key = (entry.stall_category, entry.applies_to_dimension, entry.applies_to_value)
        if key in by_key:
            raise ValueError(f"Duplicate KB lookup key {key} -- entries {by_key[key].entry_id!r} and {entry.entry_id!r}")
        by_key[key] = entry

    return KnowledgeBase(
        kb_version=raw["metadata"]["kb_version"],
        last_reviewed=date.fromisoformat(raw["metadata"]["last_reviewed"]),
        entries=entries,
        by_key=by_key,
    )


@lru_cache(maxsize=1)
def default_knowledge_base() -> KnowledgeBase:
    return load_knowledge_base()


def _specific_key_for(
    detection: DelayStallDetection | FrictionStallDetection,
) -> tuple[str, str] | None:
    """Returns the (dimension, value) for the most specific lookup this
    detection's category supports, or None if only category-generic
    lookup applies to it. Deliberately explicit per category rather than
    a generic "use stage_label" rule, since stage_label means different
    things for different categories (a status_desc for pre-issuance dwell,
    a terminal track for finalization gap, an inspection-type pair label
    for inter-inspection gap -- only the first two currently have any
    specifically-keyed KB entries)."""
    if detection.category == StallCategory.PRE_ISSUANCE_STATUS_DWELL:
        return ("status_desc", detection.stage_label)
    if detection.category == StallCategory.FINALIZATION_GAP:
        return ("track", detection.stage_label)
    return None


def lookup(
    kb: KnowledgeBase, detection: DelayStallDetection | FrictionStallDetection
) -> KnowledgeBaseEntry | None:
    """Specific match first, then this category's generic entry, then
    None. Never matches across categories."""
    specific = _specific_key_for(detection)
    if specific is not None:
        entry = kb.by_key.get((detection.category, specific[0], specific[1]))
        if entry is not None:
            return entry
    return kb.by_key.get((detection.category, "category_generic", None))
