"""Permit-level administrative/documentary-permit detection for
NO_INSPECTION_SINCE_ISSUANCE eligibility, distinct from and layered before
the aggregate type-level coverage-rate gate in coverage_eligibility.py.

Motivating case: permit 18010-20001-05038 (a real, verified permit) is a
$0-valuation "SUPPLEMENTAL TO 18010-20000-05038: TO CORRECT LEGAL
DESCRIPTION DUE TO TRACT MAP RECORDATION" permit -- an administrative paperwork
correction, not construction work, and it legitimately has zero inspections.
Its permit_type (Bldg-Alter/Repair) clears the aggregate coverage-rate gate
at 71.1%, so without this layer it produced a SEVERE false-positive stall.

Deliberately deterministic and auditable (substring/regex pattern matching
against real observed fields), not an LLM classification -- every match is
traceable to the exact pattern and field that fired, and the pattern list is
a plain, reviewable constant.

Conservative by design: only permits with *both* a zero valuation and
matching administrative language in work_desc are treated as plausibly
exempt. A permit with only one of the two signals is AMBIGUOUS -- routed to
a coverage gap, not silently treated as either exempt or fully eligible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Patterns matched against work_desc.upper(). Curated from real observed
# LADBS work_desc text (see research/AGENT2_DESIGN.md) -- provisional and
# revisit-worthy, same spirit as this project's other empirically-seeded
# but not exhaustively-validated constants (e.g. the coverage-rate
# threshold). Deliberately narrow: false negatives (missing a real
# administrative permit) are preferable to false positives (wrongly
# suppressing a real stall signal) here.
ADMINISTRATIVE_WORK_DESC_PATTERNS: list[str] = [
    r"SUPPLEMENTAL TO\s+\d",                       # "SUPPLEMENTAL TO 18010-20000-05038"
    r"CORRECT(ION)?\s+(OF\s+)?(THE\s+)?LEGAL DESCRIPTION",
    r"DEPARTMENT ERROR",
    r"\bNO FEE\b",
    r"CORRECT(ION)?\s+(OF\s+)?(THE\s+)?ADDRESS",
    r"\bVOID\b",
    r"DUPLICATE PERMIT",
    r"CHANGE OF (CONTRACTOR|ARCHITECT|ENGINEER|OWNER)",
    r"ADMINISTRATIVE CORRECTION",
    r"REVISE PERMIT",
    r"CORRECT(ION)?\s+(OF\s+)?(THE\s+)?TRACT MAP",
]

_COMPILED_PATTERNS = [re.compile(p) for p in ADMINISTRATIVE_WORK_DESC_PATTERNS]


@dataclass(frozen=True)
class InspectionExemptionAssessment:
    permit_number: str
    is_plausibly_exempt: bool
    is_ambiguous: bool
    matched_signals: list[str] = field(default_factory=list)
    reasoning: str = ""


def assess_inspection_exemption(
    permit_number: str, work_description: str | None, valuation: float | None
) -> InspectionExemptionAssessment:
    text = (work_description or "").upper()
    matched_patterns = [p for p, c in zip(ADMINISTRATIVE_WORK_DESC_PATTERNS, _COMPILED_PATTERNS) if c.search(text)]
    zero_valuation = valuation is not None and valuation == 0

    signals = list(matched_patterns)
    if zero_valuation:
        signals.append("zero_valuation")

    if zero_valuation and matched_patterns:
        return InspectionExemptionAssessment(
            permit_number=permit_number,
            is_plausibly_exempt=True,
            is_ambiguous=False,
            matched_signals=signals,
            reasoning=(
                "$0 valuation and work_desc matches administrative/documentary language "
                f"({len(matched_patterns)} pattern(s)) -- plausibly does not require a "
                "physical inspection."
            ),
        )

    if zero_valuation or matched_patterns:
        which = "zero valuation but no matching administrative language" if zero_valuation else \
            "administrative-language match but nonzero valuation"
        return InspectionExemptionAssessment(
            permit_number=permit_number,
            is_plausibly_exempt=False,
            is_ambiguous=True,
            matched_signals=signals,
            reasoning=(
                f"Only one exemption signal present ({which}) -- not enough to conservatively "
                "conclude this permit is inspection-exempt, but enough to not trust a "
                "no-inspection stall signal either."
            ),
        )

    return InspectionExemptionAssessment(
        permit_number=permit_number,
        is_plausibly_exempt=False,
        is_ambiguous=False,
        matched_signals=[],
        reasoning="No administrative/documentary-permit signals detected in work_desc or valuation.",
    )
