"""Adversarial and exhaustive safeguard tests (AGENT3_DESIGN.md §5, §9).

Two kinds of coverage here:
1. Proof the scanners themselves catch bad language (adversarial strings
   fed directly into the scanner functions) -- this is what would catch a
   regression if someone later added templated blame language or an LLM
   phrasing layer that drifted.
2. Proof the actual system -- every real KB entry, and every category's
   rendered output across a spread of severities -- currently produces
   nothing that trips any scanner.
"""

from __future__ import annotations

from datetime import datetime, timezone
from itertools import product

import pytest

from permit_stall_finder.knowledge_base.loader import default_knowledge_base
from permit_stall_finder.rendering.fact_renderer import render_what_the_data_shows
from permit_stall_finder.rendering.safeguards import (
    BannedPhraseError,
    assert_no_blame_language,
    assert_no_known_total_duration_claim,
    assert_no_normal_duration_claim,
    assert_no_permit_specific_values,
)
from permit_stall_finder.schema.journey import MatchStatus
from permit_stall_finder.schema.stall_detection import (
    BenchmarkSemantics,
    CohortConfidence,
    CohortDefinition,
    CohortSource,
    DelayStallDetection,
    FrictionStallDetection,
    IntervalState,
    LifecycleStage,
    Severity,
    StallCategory,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)

# --- 1. adversarial strings: proof the scanners themselves work ---


@pytest.mark.parametrize(
    "text",
    [
        "This permit is stuck because the applicant failed to schedule inspections.",
        "This is a clear violation of LADBS requirements.",
        "The permit holder is non-compliant with the correction notice.",
        "The contractor should have requested reinspection sooner.",
        "This delay is due to the developer's negligence.",
        "The applicant is at fault for this gap.",
        "This gap was caused by the owner's failure to comply.",
    ],
)
def test_blame_scanner_catches_adversarial_blame_language(text):
    with pytest.raises(BannedPhraseError):
        assert_no_blame_language(text)


@pytest.mark.parametrize(
    "text",
    [
        "Permits in this status normally take 90 days to clear.",
        "This stage typically completes in about two weeks.",
        "Comparable permits are usually finished within a month.",
    ],
)
def test_normal_duration_scanner_catches_adversarial_language(text):
    with pytest.raises(BannedPhraseError):
        assert_no_normal_duration_claim(text)


@pytest.mark.parametrize(
    "text",
    [
        "This project will take another 30 days to finish.",
        "The permit should be done by next month.",
        "Total of 60 days remain before completion.",
    ],
)
def test_known_total_duration_scanner_catches_adversarial_language(text):
    with pytest.raises(BannedPhraseError):
        assert_no_known_total_duration_claim(text)


@pytest.mark.parametrize(
    "text",
    [
        "This status was reached on 2021-08-04 and is unusual.",
        "This ranks at approximately the 92% mark among peers.",
        "Permits in this state commonly wait 45 days before the next step.",
    ],
)
def test_permit_specific_value_scanner_catches_interpolated_looking_text(text):
    with pytest.raises(BannedPhraseError):
        assert_no_permit_specific_values(text)


def test_clean_neutral_text_passes_all_scanners():
    text = "This status reflects a checkpoint in LADBS's plan check process."
    assert_no_blame_language(text)
    assert_no_normal_duration_claim(text)
    assert_no_known_total_duration_claim(text)
    assert_no_permit_specific_values(text)


# --- 2. the real system: every KB entry, every category's renderer ---


def test_every_kb_entry_text_is_free_of_all_four_problems():
    kb = default_knowledge_base()
    for entry in kb.entries:
        texts = (
            [("explanation", entry.explanation)]
            + [(f"dev_step[{i}]", s.text) for i, s in enumerate(entry.developer_actionable_steps)]
            + [(f"city_step[{i}]", s.text) for i, s in enumerate(entry.city_dependent_steps)]
            + [(f"caveat[{i}]", c) for i, c in enumerate(entry.caveats)]
        )
        for label, text in texts:
            context = f"{entry.entry_id}.{label}"
            assert_no_blame_language(text, context)
            assert_no_normal_duration_claim(text, context)
            assert_no_known_total_duration_claim(text, context)
            assert_no_permit_specific_values(text, context)


def _cohort(benchmark_semantics):
    return CohortDefinition(
        dimensions={}, specificity_level=1, source=CohortSource.SOURCE_EVENT_LOG,
        benchmark_semantics=benchmark_semantics, n=100, confidence=CohortConfidence.FULL,
        median_days_or_count=10.0, p75_days_or_count=20.0, p90_days_or_count=30.0, p95_days_or_count=40.0,
        computed_at=NOW,
    )


_DELAY_CATEGORIES = [
    StallCategory.PRE_ISSUANCE_STATUS_DWELL,
    StallCategory.ISSUANCE_TO_FIRST_INSPECTION_GAP,
    StallCategory.NO_INSPECTION_SINCE_ISSUANCE,
    StallCategory.INTER_INSPECTION_GAP,
    StallCategory.INACTIVITY_SINCE_LAST_INSPECTION,
    StallCategory.FINALIZATION_GAP,
]
_FRICTION_CATEGORIES = [
    StallCategory.REPEATED_CORRECTIONS,
    StallCategory.REPEATED_NOT_READY_OUTCOMES,
    StallCategory.REPEATED_CANCELLATIONS,
]


@pytest.mark.parametrize(
    "category,severity,benchmark_semantics,interval_state,persistence",
    list(product(
        _DELAY_CATEGORIES,
        [Severity.WATCH, Severity.ELEVATED, Severity.SEVERE],
        [BenchmarkSemantics.ACTIVE_PEER_DWELL, BenchmarkSemantics.COMPLETED_INTERVAL],
        [IntervalState.ONGOING, IntervalState.COMPLETED],
        [False, True],
    )),
)
def test_every_delay_rendering_combination_is_clean(category, severity, benchmark_semantics, interval_state, persistence):
    d = DelayStallDetection(
        permit_number="TEST-1", category=category, stage_label="Some Status", generated_at=NOW,
        elapsed_days=2000, as_of=NOW, interval_state=interval_state,
        status_persistence_confirmed_by_repeated_observation=persistence,
        cohort=_cohort(benchmark_semantics), percentile_rank=99.0, excess_days_vs_median=1990.0,
        severity=severity, evidence=[], cannot_infer=[], caveats=[],
        based_on_match_status=MatchStatus.ISSUED_WITH_INSPECTIONS,
    )
    text = render_what_the_data_shows(d)
    assert_no_blame_language(text, str(category))
    if benchmark_semantics == BenchmarkSemantics.ACTIVE_PEER_DWELL:
        assert_no_normal_duration_claim(text, str(category))
    if interval_state == IntervalState.ONGOING:
        assert_no_known_total_duration_claim(text, str(category))


@pytest.mark.parametrize(
    "category,severity",
    list(product(_FRICTION_CATEGORIES, [Severity.WATCH, Severity.ELEVATED, Severity.SEVERE])),
)
def test_every_friction_rendering_combination_is_clean(category, severity):
    d = FrictionStallDetection(
        permit_number="TEST-1", category=category, generated_at=NOW,
        observed_count=20, meets_minimum_count=True, minimum_count_required=2,
        lifecycle_stage=LifecycleStage.COMPLETED, total_inspection_opportunities=30,
        observed_lifecycle_days=400, correction_rate=0.66, meets_minimum_exposure=True,
        cohort=_cohort(BenchmarkSemantics.COMPLETED_INTERVAL), percentile_rank=99.0,
        excess_count_vs_median=19.0, severity=severity,
        evidence=[], cannot_infer=[], caveats=[], based_on_match_status=MatchStatus.ISSUED_WITH_INSPECTIONS,
    )
    text = render_what_the_data_shows(d)
    assert_no_blame_language(text, str(category))
