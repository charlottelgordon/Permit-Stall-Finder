"""Knowledge-base schema, completeness, and lookup tests
(AGENT3_DESIGN.md §3, §8)."""

from __future__ import annotations

from permit_stall_finder.knowledge_base.loader import default_knowledge_base, load_knowledge_base, lookup
from permit_stall_finder.schema.developer_explanation import GroundingStrength, VerificationStatus
from permit_stall_finder.schema.stall_detection import StallCategory

from datetime import datetime, timezone

from permit_stall_finder.schema.stall_detection import (
    BenchmarkSemantics,
    CohortConfidence,
    CohortDefinition,
    CohortSource,
    DelayStallDetection,
    IntervalState,
    Severity,
)
from permit_stall_finder.schema.journey import MatchStatus

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def _cohort(benchmark_semantics=BenchmarkSemantics.COMPLETED_INTERVAL):
    return CohortDefinition(
        dimensions={}, specificity_level=1, source=CohortSource.SOURCE_EVENT_LOG,
        benchmark_semantics=benchmark_semantics, n=50, confidence=CohortConfidence.FULL,
        median_days_or_count=1.0, p75_days_or_count=5.0, p90_days_or_count=10.0, p95_days_or_count=20.0,
        computed_at=NOW,
    )


def _delay_detection(category, stage_label="X"):
    return DelayStallDetection(
        permit_number="TEST-1", category=category, stage_label=stage_label, generated_at=NOW,
        elapsed_days=30, as_of=NOW, interval_state=IntervalState.COMPLETED,
        status_persistence_confirmed_by_repeated_observation=False,
        cohort=_cohort(), percentile_rank=90.0, excess_days_vs_median=29.0, severity=Severity.ELEVATED,
        evidence=[], cannot_infer=[], caveats=[], based_on_match_status=MatchStatus.ISSUED_WITH_INSPECTIONS,
    )


def test_kb_loads_and_every_entry_has_at_least_one_source():
    kb = load_knowledge_base()
    assert len(kb.entries) > 0
    for entry in kb.entries:
        assert entry.sources, f"{entry.entry_id} has no sources"


def test_every_source_has_a_verification_status():
    kb = default_knowledge_base()
    for entry in kb.entries:
        for source in entry.sources:
            assert isinstance(source.verification_status, VerificationStatus)


def test_every_next_step_has_a_grounding_strength():
    kb = default_knowledge_base()
    for entry in kb.entries:
        for step in entry.developer_actionable_steps + entry.city_dependent_steps:
            assert isinstance(step.grounding_strength, GroundingStrength)


def test_specific_lookup_beats_generic_for_corrections_issued():
    """pre_issuance_status_dwell x 'Corrections Issued' has its own entry
    -- lookup must prefer it over pre_issuance.generic (AGENT3_DESIGN.md
    §3 requirement: specific matching, not category-only)."""
    kb = default_knowledge_base()
    detection = _delay_detection(StallCategory.PRE_ISSUANCE_STATUS_DWELL, stage_label="Corrections Issued")
    entry = lookup(kb, detection)
    assert entry is not None
    assert entry.entry_id == "pre_issuance.corrections_issued"


def test_generic_fallback_for_unmatched_status_desc():
    """A pre-issuance status without its own specific entry (e.g. 'PC
    Approved') falls back to the category-generic entry, not None."""
    kb = default_knowledge_base()
    detection = _delay_detection(StallCategory.PRE_ISSUANCE_STATUS_DWELL, stage_label="PC Approved")
    entry = lookup(kb, detection)
    assert entry is not None
    assert entry.entry_id == "pre_issuance.generic"


def test_finalization_gap_cofo_track_specific_lookup():
    kb = default_knowledge_base()
    detection = _delay_detection(StallCategory.FINALIZATION_GAP, stage_label="cofo_track")
    entry = lookup(kb, detection)
    assert entry is not None
    assert entry.entry_id == "finalization_gap.cofo_track"


def test_no_entry_for_repeated_not_ready_outcomes():
    """No official source was found for this category -- by design there
    is no KB entry at all, not even a generic one."""
    kb = default_knowledge_base()
    assert (StallCategory.REPEATED_NOT_READY_OUTCOMES, "category_generic", None) not in kb.by_key


def test_no_entry_for_repeated_cancellations():
    kb = default_knowledge_base()
    assert (StallCategory.REPEATED_CANCELLATIONS, "category_generic", None) not in kb.by_key


def test_lookup_returns_none_when_no_entry_exists():
    from permit_stall_finder.schema.stall_detection import FrictionStallDetection, LifecycleStage

    kb = default_knowledge_base()
    detection = FrictionStallDetection(
        permit_number="TEST-1", category=StallCategory.REPEATED_CANCELLATIONS, generated_at=NOW,
        observed_count=5, meets_minimum_count=True, minimum_count_required=2,
        lifecycle_stage=LifecycleStage.COMPLETED, total_inspection_opportunities=20,
        observed_lifecycle_days=100, correction_rate=0.25, meets_minimum_exposure=True,
        cohort=_cohort(), percentile_rank=80.0, excess_count_vs_median=4.0, severity=Severity.WATCH,
        evidence=[], cannot_infer=[], caveats=[], based_on_match_status=MatchStatus.ISSUED_WITH_INSPECTIONS,
    )
    assert lookup(kb, detection) is None
