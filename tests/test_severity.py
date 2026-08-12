from __future__ import annotations

import pytest

from permit_stall_finder.analysis.severity import classify_severity, percentile_rank
from permit_stall_finder.schema.stall_detection import Severity, SeverityThresholds


def test_percentile_rank_basic():
    population = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert percentile_rank(100.0, population) == 100.0
    assert percentile_rank(10.0, population) == 10.0
    assert percentile_rank(55.0, population) == 50.0  # 5 of 10 values <= 55


def test_percentile_rank_empty_population_raises():
    with pytest.raises(ValueError):
        percentile_rank(5.0, [])


@pytest.mark.parametrize(
    "rank,expected",
    [
        (49.9, None),
        (74.9, None),
        (75.0, Severity.WATCH),
        (89.9, Severity.WATCH),
        (90.0, Severity.ELEVATED),
        (94.9, Severity.ELEVATED),
        (95.0, Severity.SEVERE),
        (100.0, Severity.SEVERE),
    ],
)
def test_classify_severity_default_bands(rank, expected):
    assert classify_severity(rank, SeverityThresholds()) == expected


def test_classify_severity_insufficient_cohort_is_unscored():
    assert classify_severity(None, SeverityThresholds()) == Severity.UNSCORED


def test_classify_severity_configurable_thresholds():
    custom = SeverityThresholds(watch=50.0, elevated=70.0, severe=90.0)
    assert classify_severity(60.0, custom) == Severity.WATCH
    assert classify_severity(80.0, custom) == Severity.ELEVATED
    assert classify_severity(95.0, custom) == Severity.SEVERE
    assert classify_severity(40.0, custom) is None


def test_median_never_triggers_a_detection_on_its_own():
    """A permit sitting exactly at the cohort median (50th percentile)
    must not be flagged -- refinement #1: the median is context, not a
    threshold."""
    assert classify_severity(50.0, SeverityThresholds()) is None
