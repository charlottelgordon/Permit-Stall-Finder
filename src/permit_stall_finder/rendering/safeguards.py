"""Structural, testable hallucination/blame safeguards (AGENT3_DESIGN.md §5,
§9). These are phrase-scanning checks, not an LLM judgment call -- every
one of them is a plain substring/regex test that can run in CI against
both rendered output and the knowledge base itself, with no ambiguity
about what "banned" means.

Four independent gates:
1. No claim of normal/expected completion duration from an
   ACTIVE_PEER_DWELL comparison (must only say "longer than X% of
   currently observed peers," never "typically takes N days").
2. No claim of a known total/final duration for an ONGOING interval.
3. No blame, causality, fault, or non-compliance language anywhere in
   Agent 3 output or the knowledge base -- Agent 2's severity is a
   percentile ranking, never a verdict.
4. No point-estimate duration promise about THE PERMIT BEING RENDERED
   from a conditional remaining-duration forecast (analysis/forecast.py)
   -- that forecast is a distributional statement about OTHER,
   comparable permits' already-concluded durations; it must never
   collapse into an ETA for this one.
"""

from __future__ import annotations

import re

NORMAL_DURATION_PHRASES = [
    "normally take",
    "normally takes",
    "typically completes",
    "typically takes",
    "usually finished",
    "usually takes",
    "expected to take",
    "on average takes",
]

KNOWN_TOTAL_DURATION_PHRASES = [
    "will take",
    "will be completed",
    "will be done",
    "should be done by",
    "expected to finish",
    "expected to be complete",
    "total of",
]

BLAME_CAUSALITY_PHRASES = [
    "failed to",
    "failure to",
    "violation",
    "non-compliant",
    "noncompliant",
    "non compliance",
    "noncompliance",
    "at fault",
    "negligent",
    "negligence",
    "should have",
    "responsible for the delay",
    "responsible for this delay",
    "their fault",
    "didn't comply",
    "did not comply",
    "caused by the",
    "due to the applicant",
    "due to the developer",
    "due to the contractor",
]


POINT_ESTIMATE_DURATION_PHRASES = [
    "will take",
    "will need",
    "will finish",
    "will be done",
    "will be complete",
    "will resume",
    "should take about",
    "should finish",
    "should be done in",
    "should be done by",
    "is expected to need",
    "is expected to take",
    "expected to finish",
    "expected total",
    "estimated to take",
    "estimated completion",
    "eta",
]


class BannedPhraseError(ValueError):
    def __init__(self, context: str, text: str, hits: list[str]):
        self.context = context
        self.text = text
        self.hits = hits
        super().__init__(f"Banned phrase(s) {hits} found in {context}: {text!r}")


def _scan(text: str, banned: list[str], context: str) -> None:
    lowered = text.lower()
    hits = [p for p in banned if p in lowered]
    if hits:
        raise BannedPhraseError(context, text, hits)


def assert_no_normal_duration_claim(text: str, context: str = "text") -> None:
    _scan(text, NORMAL_DURATION_PHRASES, context)


def assert_no_known_total_duration_claim(text: str, context: str = "text") -> None:
    _scan(text, KNOWN_TOTAL_DURATION_PHRASES, context)


def assert_no_blame_language(text: str, context: str = "text") -> None:
    _scan(text, BLAME_CAUSALITY_PHRASES, context)


def assert_no_point_estimate_duration_claim(text: str, context: str = "text") -> None:
    """A conditional remaining-duration forecast may describe how long
    OTHER, comparable permits took once they resumed; it must never read
    as a promise about the permit currently being rendered."""
    _scan(text, POINT_ESTIMATE_DURATION_PHRASES, context)


_LOOKS_LIKE_SPECIFIC_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_LOOKS_LIKE_PERCENTAGE = re.compile(r"\d+(\.\d+)?%")
_LOOKS_LIKE_DAY_COUNT = re.compile(r"\b\d+\s*days?\b", re.IGNORECASE)


def assert_no_permit_specific_values(text: str, context: str = "text") -> None:
    """Knowledge-base explanation/step text must be a general process
    statement with no interpolated permit-specific numbers -- this is what
    structurally prevents section 1's facts from leaking into section 2's
    prose (AGENT3_DESIGN.md §2, §4)."""
    for pattern, label in (
        (_LOOKS_LIKE_SPECIFIC_DATE, "a specific date (YYYY-MM-DD)"),
        (_LOOKS_LIKE_PERCENTAGE, "a specific percentage"),
        (_LOOKS_LIKE_DAY_COUNT, "a specific day count"),
    ):
        if pattern.search(text):
            raise BannedPhraseError(context, text, [f"looks like {label}"])
