from __future__ import annotations

from permit_stall_finder.analysis.cohorts import MIN_FULL_CONFIDENCE_N, MIN_REDUCED_CONFIDENCE_N
from permit_stall_finder.analysis.forecast import conditional_remaining_duration
from permit_stall_finder.schema.stall_detection import CohortConfidence


def test_conditional_remaining_duration_basic():
    # 10 completed intervals; elapsed_days=20 leaves 7 members >= 20
    # (20, 20, 20, 25, 30, 35, 40), so remaining = (0, 0, 0, 5, 10, 15, 20).
    population = [5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 20.0, 20.0]
    forecast = conditional_remaining_duration(20.0, population, min_n=3)
    assert forecast is not None
    assert forecast.conditional_n == 7
    assert forecast.remaining_p50_days >= 0


def test_conditional_remaining_duration_none_when_below_min_n():
    population = [5.0, 10.0, 100.0]
    # Only one member (100.0) is >= 20 -- below any reasonable min_n.
    forecast = conditional_remaining_duration(20.0, population, min_n=2)
    assert forecast is None


def test_conditional_remaining_duration_none_on_empty_tail():
    population = [1.0, 2.0, 3.0]
    forecast = conditional_remaining_duration(1000.0, population, min_n=1)
    assert forecast is None


def test_conditional_remaining_duration_exactly_min_n():
    population = [10.0, 10.0, 10.0]
    forecast = conditional_remaining_duration(5.0, population, min_n=3)
    assert forecast is not None
    assert forecast.conditional_n == 3
    assert forecast.remaining_p50_days == 5.0


def test_conditional_remaining_duration_one_below_min_n():
    population = [10.0, 10.0]
    forecast = conditional_remaining_duration(5.0, population, min_n=3)
    assert forecast is None


def test_conditional_remaining_duration_default_min_n_matches_reduced_confidence_floor():
    # Uses the module default (MIN_REDUCED_CONFIDENCE_N) rather than a
    # second, independently-invented threshold.
    population = [10.0] * (MIN_REDUCED_CONFIDENCE_N - 1)
    assert conditional_remaining_duration(5.0, population) is None
    population = [10.0] * MIN_REDUCED_CONFIDENCE_N
    assert conditional_remaining_duration(5.0, population) is not None


def test_conditional_confidence_tiers():
    reduced_population = [10.0] * MIN_REDUCED_CONFIDENCE_N
    forecast = conditional_remaining_duration(5.0, reduced_population)
    assert forecast.conditional_confidence == CohortConfidence.REDUCED

    full_population = [10.0] * MIN_FULL_CONFIDENCE_N
    forecast = conditional_remaining_duration(5.0, full_population)
    assert forecast.conditional_confidence == CohortConfidence.FULL


def test_conditional_remaining_duration_never_negative():
    # Every qualifying member is >= elapsed_days by construction, so
    # remaining time can never be negative.
    population = [20.0, 21.0, 22.0, 23.0, 24.0]
    forecast = conditional_remaining_duration(20.0, population, min_n=3)
    assert forecast.remaining_p50_days >= 0
    assert forecast.remaining_p75_days >= 0
    assert forecast.remaining_p90_days >= 0
