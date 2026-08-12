"""Controlled analytical mappings over the raw inspection_result and
inspection_type vocabularies (AGENT2_DESIGN.md §5). Raw values are never
overwritten anywhere in this project — InspectionEvent.inspection_type/
.inspection_result (Agent 1's schema) always carry the original string.
These lookups are additive: given a raw value, what analytical category
does it belong to, with an explicit, visible fallback when the answer is
"we don't know."

Mapping data lives in research/*.json (the versioned, documented artifacts
produced during design) rather than duplicated into the package, so there
is exactly one copy to keep in sync. See AGENT2_DESIGN.md §5c for the
mapping_version/vocabulary_extraction_date provenance these files carry.
"""

from __future__ import annotations

import json
from enum import Enum
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RESULT_MAPPING_PATH = _REPO_ROOT / "research" / "inspection_result_family_mapping.json"
_STAGE_MAPPING_PATH = _REPO_ROOT / "research" / "inspection_type_stage_mapping.json"


class ResultFamily(str, Enum):
    APPROVED = "APPROVED"
    CORRECTIONS = "CORRECTIONS"
    NOT_READY = "NOT_READY"
    SCHEDULED = "SCHEDULED"
    CANCELLED = "CANCELLED"
    PARTIAL = "PARTIAL"
    FINAL = "FINAL"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


# Result families that represent a genuine, completed site inspection with
# a real outcome -- used to filter inspection_events before any gap or
# friction calculation. SCHEDULED (hasn't happened), CANCELLED (didn't
# happen), FINAL (administrative closing record, not a site visit), OTHER,
# and UNKNOWN are all excluded.
SUBSTANTIVE_RESULT_FAMILIES = frozenset(
    {ResultFamily.APPROVED, ResultFamily.CORRECTIONS, ResultFamily.NOT_READY, ResultFamily.PARTIAL}
)


@lru_cache(maxsize=1)
def _load_result_mapping() -> dict:
    with open(_RESULT_MAPPING_PATH) as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _load_stage_mapping() -> dict:
    with open(_STAGE_MAPPING_PATH) as f:
        return json.load(f)


def result_mapping_metadata() -> dict:
    return _load_result_mapping()["metadata"]


def stage_mapping_metadata() -> dict:
    return _load_stage_mapping()["metadata"]


def result_family(raw_inspection_result: str | None) -> ResultFamily:
    """Never raises, never guesses. A value not present in the mapping
    table -- including a value that didn't exist at
    vocabulary_extraction_date -- resolves to UNKNOWN, visibly, rather
    than silently inheriting an existing family."""
    if not raw_inspection_result:
        return ResultFamily.UNKNOWN
    family_of = _load_result_mapping()["family_of"]
    name = family_of.get(raw_inspection_result)
    if name is None:
        return ResultFamily.UNKNOWN
    return ResultFamily(name)


def inspection_stage(raw_inspection_type: str | None) -> str | None:
    """Returns the mapped construction-stage bucket name, or None if the
    raw value is unmapped (§5b — 10 of 185 known values are deliberately
    left unmapped, plus any future value not seen at extraction time).
    None is a real, meaningful answer here ("unmapped"), never coerced
    into a stage."""
    if not raw_inspection_type:
        return None
    return _load_stage_mapping()["stage_of"].get(raw_inspection_type)


def is_substantive(raw_inspection_result: str | None) -> bool:
    return result_family(raw_inspection_result) in SUBSTANTIVE_RESULT_FAMILIES
