"""Adversarial and exhaustive safeguard tests for the remaining-duration
forecast feature, mirroring tests/test_agent3_grounding_safeguards.py's
two-part structure:

1. Proof the new scanner (assert_no_point_estimate_duration_claim) itself
   catches bad language -- what would catch a regression if the sentence
   template later drifted toward a point-estimate promise.
2. Proof the actual system -- every eligible category, across a spread of
   severities and forecast values, currently renders clean text at both
   the schema layer (render_remaining_duration_forecast, the single-
   language contract) and the i18n layer (remaining_duration_phrase, the
   bilingual UI-facing text) -- against all four existing scanners plus
   this new one, since a forecast sentence must never trip any of them.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import i18n  # noqa: E402

from permit_stall_finder.rendering.safeguards import (
    BannedPhraseError,
    assert_no_blame_language,
    assert_no_known_total_duration_claim,
    assert_no_normal_duration_claim,
    assert_no_point_estimate_duration_claim,
)
from permit_stall_finder.schema.journey import MatchStatus
from permit_stall_finder.schema.stall_detection import (
    BenchmarkSemantics,
    CohortConfidence,
    CohortDefinition,
    CohortSource,
    DelayStallDetection,
    IntervalState,
    RemainingDurationForecast,
    Severity,
    StallCategory,
    render_remaining_duration_forecast,
)

NOW = datetime(2026, 8, 11, tzinfo=timezone.utc)

# --- 1. adversarial strings: proof the scanner itself works ---


@pytest.mark.parametrize(
    "text",
    [
        "This permit will take another 30 days to finish.",
        "This project will need about two more weeks.",
        "It should take about 3 more weeks once corrections clear.",
        "Estimated completion is in 10 more days.",
        "This permit is expected to finish next month.",
        "ETA is roughly three weeks from now.",
    ],
)
def test_point_estimate_scanner_catches_adversarial_language(text):
    with pytest.raises(BannedPhraseError):
        assert_no_point_estimate_duration_claim(text)


def test_point_estimate_scanner_allows_comparison_to_other_permits():
    text = (
        "Among comparable permits that were already delayed this long, the middle half "
        "finished within 12-34 more days once they resumed (based on 15 comparable permits)."
    )
    assert_no_point_estimate_duration_claim(text)


# --- 2. the real system: schema-layer and i18n-layer rendering ---


def _cohort():
    return CohortDefinition(
        dimensions={}, specificity_level=1, source=CohortSource.SOURCE_EVENT_LOG,
        benchmark_semantics=BenchmarkSemantics.COMPLETED_INTERVAL, n=100, confidence=CohortConfidence.FULL,
        median_days_or_count=10.0, p75_days_or_count=20.0, p90_days_or_count=30.0, p95_days_or_count=40.0,
        computed_at=NOW,
    )


def _forecast(p50=12.0, p75=34.0, p90=60.0, n=15):
    return RemainingDurationForecast(
        conditional_n=n, conditional_confidence=CohortConfidence.REDUCED,
        remaining_p50_days=p50, remaining_p75_days=p75, remaining_p90_days=p90,
    )


def _delay_detection(category, severity, forecast):
    return DelayStallDetection(
        permit_number="TEST-1", category=category, stage_label="Some Status", generated_at=NOW,
        elapsed_days=390, as_of=NOW, interval_state=IntervalState.ONGOING,
        status_persistence_confirmed_by_repeated_observation=False,
        cohort=_cohort(), percentile_rank=97.0, excess_days_vs_median=380.0,
        severity=severity, evidence=[], cannot_infer=[], caveats=[],
        based_on_match_status=MatchStatus.ISSUED_WITH_INSPECTIONS,
        remaining_duration_forecast=forecast,
    )


# Only these two categories are ever eligible for a forecast (ONGOING
# interval_state + COMPLETED_INTERVAL cohort) -- see
# stall_detector.py's _detect_no_inspection_since_issuance and
# _detect_inactivity_since_last_inspection.
_ELIGIBLE_CATEGORIES = [
    StallCategory.NO_INSPECTION_SINCE_ISSUANCE,
    StallCategory.INACTIVITY_SINCE_LAST_INSPECTION,
]


@pytest.mark.parametrize(
    "category,severity,p50,p75,n",
    list(product(
        _ELIGIBLE_CATEGORIES,
        [Severity.WATCH, Severity.ELEVATED, Severity.SEVERE],
        [0.0, 1.0, 45.5],
        [12.0, 90.0, 200.25],
        [10, 30, 250],
    )),
)
def test_every_forecast_combination_is_clean_at_schema_layer(category, severity, p50, p75, n):
    forecast = _forecast(p50=p50, p75=max(p75, p50), n=n)
    d = _delay_detection(category, severity, forecast)
    text = render_remaining_duration_forecast(d)
    assert text is not None
    context = str(category)
    assert_no_blame_language(text, context)
    assert_no_normal_duration_claim(text, context)
    assert_no_known_total_duration_claim(text, context)
    assert_no_point_estimate_duration_claim(text, context)


@pytest.mark.parametrize(
    "category,severity",
    list(product(_ELIGIBLE_CATEGORIES, [Severity.WATCH, Severity.ELEVATED, Severity.SEVERE])),
)
def test_every_forecast_combination_is_clean_at_i18n_layer(category, severity):
    # Not scanned with assert_no_permit_specific_values here -- unlike KB
    # entry prose, this text is Agent 2-computed statistical content (the
    # same boundary render_what_the_data_shows sits on) and is *supposed*
    # to carry its own numbers; that scanner only applies to category-
    # generic KB text (see test_agent3_grounding_safeguards.py).
    forecast = _forecast()
    text = i18n.remaining_duration_phrase(forecast)
    context = str(category)
    assert_no_blame_language(text, context)
    assert_no_normal_duration_claim(text, context)
    assert_no_known_total_duration_claim(text, context)
    assert_no_point_estimate_duration_claim(text, context)


def test_render_remaining_duration_forecast_returns_none_when_no_forecast():
    d = _delay_detection(StallCategory.NO_INSPECTION_SINCE_ISSUANCE, Severity.SEVERE, None)
    assert render_remaining_duration_forecast(d) is None


def test_render_remaining_duration_forecast_never_mentions_this_permit_will():
    forecast = _forecast()
    d = _delay_detection(StallCategory.INACTIVITY_SINCE_LAST_INSPECTION, Severity.SEVERE, forecast)
    text = render_remaining_duration_forecast(d)
    assert "this permit will" not in text.lower()
    assert "comparable permits" in text.lower()
