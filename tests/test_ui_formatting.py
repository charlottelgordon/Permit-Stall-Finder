"""Tests for app/formatting.py's pure presentation helpers -- no
Streamlit involved. Confirms label coverage for every enum value these
schemas define (so a newly added enum member fails loudly here rather
than rendering as a raw Python repr in the UI), and confirms
kb_entry_by_id() never performs its own matching."""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import formatting  # noqa: E402

from permit_stall_finder.knowledge_base.loader import KnowledgeBase, default_knowledge_base  # noqa: E402
from permit_stall_finder.orchestration.pipeline import AnalysisOutcome  # noqa: E402
from permit_stall_finder.schema.developer_explanation import (  # noqa: E402
    DeveloperExplanation,
    GroundingStatus,
    KBConfidence,
    KnowledgeBaseEntry,
    KnowledgeBaseSource,
    SourceType,
    VerificationStatus,
)
from permit_stall_finder.schema.journey import DataQualityFlag, MatchStatus  # noqa: E402
from permit_stall_finder.schema.stall_detection import (  # noqa: E402
    BenchmarkSemantics,
    CohortConfidence,
    CohortDefinition,
    CohortSource,
    DelayStallDetection,
    IntervalState,
    MatchStatus as StallMatchStatus,
    Severity,
    StallCategory,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)


def _cohort():
    return CohortDefinition(
        dimensions={}, specificity_level=1, source=CohortSource.SOURCE_EVENT_LOG,
        benchmark_semantics=BenchmarkSemantics.COMPLETED_INTERVAL, n=50, confidence=CohortConfidence.FULL,
        median_days_or_count=5.0, p75_days_or_count=10.0, p90_days_or_count=20.0, p95_days_or_count=30.0,
        computed_at=NOW,
    )


def _delay(severity):
    return DelayStallDetection(
        permit_number="TEST-1", category=StallCategory.INTER_INSPECTION_GAP, stage_label="X", generated_at=NOW,
        elapsed_days=84, as_of=NOW, interval_state=IntervalState.COMPLETED,
        status_persistence_confirmed_by_repeated_observation=False,
        cohort=_cohort(), percentile_rank=97.0, excess_days_vs_median=79.0, severity=severity,
        evidence=[], cannot_infer=[], caveats=[], based_on_match_status=StallMatchStatus.ISSUED_WITH_INSPECTIONS,
    )


def test_every_stall_category_has_a_label():
    for category in StallCategory:
        assert category in formatting.CATEGORY_LABELS


def test_every_severity_has_a_label_and_color():
    for severity in Severity:
        assert severity in formatting.SEVERITY_LABELS
        assert severity in formatting.SEVERITY_COLORS


def test_severity_colors_avoid_pure_red():
    assert "#ff0000" not in [c.lower() for c in formatting.SEVERITY_COLORS.values()]
    assert "#f00" not in [c.lower() for c in formatting.SEVERITY_COLORS.values()]


def test_every_match_status_has_a_label():
    for status in MatchStatus:
        assert status in formatting.MATCH_STATUS_LABELS


def test_every_data_quality_flag_has_a_label():
    for flag in DataQualityFlag:
        assert flag in formatting.DATA_QUALITY_FLAG_LABELS


def test_every_verification_status_has_a_label():
    for status in VerificationStatus:
        assert status in formatting.VERIFICATION_STATUS_LABELS


def test_summarize_severity_counts_orders_severe_first_and_omits_zero_tiers():
    detections = [_delay(Severity.WATCH), _delay(Severity.SEVERE), _delay(Severity.SEVERE)]
    summary = formatting.summarize_severity_counts(detections)
    assert summary == "2 severe findings · 1 watch finding"


def test_summarize_severity_counts_empty_list_reads_as_clean():
    assert formatting.summarize_severity_counts([]) == formatting.OUTCOME_CLEAN_TEXT


def test_outcome_headline_dispatches_on_outcome():
    clean = SimpleNamespace(outcome=AnalysisOutcome.NO_MATERIAL_STALL_DETECTED)
    assert formatting.outcome_headline(clean) == formatting.OUTCOME_CLEAN_TEXT

    insufficient = SimpleNamespace(outcome=AnalysisOutcome.INSUFFICIENT_EVIDENCE)
    assert formatting.outcome_headline(insufficient) == formatting.OUTCOME_INSUFFICIENT_TEXT

    stalled = SimpleNamespace(
        outcome=AnalysisOutcome.STALL_DETECTED,
        stall_assessment=SimpleNamespace(detections=[_delay(Severity.SEVERE)]),
    )
    assert formatting.outcome_headline(stalled) == "1 severe finding"


def test_kb_entry_by_id_returns_none_for_none_id():
    kb = default_knowledge_base()
    assert formatting.kb_entry_by_id(kb, None) is None


def test_kb_entry_by_id_returns_none_for_unknown_id():
    kb = default_knowledge_base()
    assert formatting.kb_entry_by_id(kb, "does-not-exist") is None


def test_kb_entry_by_id_resolves_exact_id_only():
    kb = default_knowledge_base()
    target = kb.entries[0]
    other_entry = KnowledgeBaseEntry(
        entry_id=target.entry_id,  # deliberately colliding id would be a bug upstream;
        # here we just confirm equality-by-id, not category/dimension matching
        stall_category=target.stall_category,
        applies_to_dimension="category_generic",
        applies_to_value=None,
        explanation="different text",
        developer_actionable_steps=[], city_dependent_steps=[],
        sources=target.sources, caveats=[], confidence=KBConfidence.GENERIC_LOW_CONFIDENCE,
        kb_version=target.kb_version, last_reviewed=target.last_reviewed,
    )
    small_kb = KnowledgeBase(
        kb_version="test", last_reviewed=target.last_reviewed, entries=[other_entry], by_key={}
    )
    resolved = formatting.kb_entry_by_id(small_kb, other_entry.entry_id)
    assert resolved is other_entry


def test_has_mixed_grounding_true_only_when_both_statuses_present():
    grounded = SimpleNamespace(grounding_status=GroundingStatus.GROUNDED)
    ungrounded = SimpleNamespace(grounding_status=GroundingStatus.NO_ENTRY_AVAILABLE)

    assert formatting.has_mixed_grounding([grounded, grounded]) is False
    assert formatting.has_mixed_grounding([ungrounded, ungrounded]) is False
    assert formatting.has_mixed_grounding([grounded, ungrounded]) is True
    assert formatting.has_mixed_grounding([]) is False
