"""Regression test for a grounding bug found reviewing charlotte-ui-2:
app/i18n.py's plain-language "extra time/count" phrases said "than
typical" for every detection, including ACTIVE_PEER_DWELL ones -- a
length-biased sample of permits still in progress, not a sample of
concluded intervals. schema/stall_detection.py's render_dwell_statement()
was written specifically to prevent this exact claim (see
test_dwell_language.py's test_active_peer_dwell_never_produces_normally_
take_language); this test holds app/i18n.py's plain-language layer to the
same rule.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

import i18n  # noqa: E402

from permit_stall_finder.schema.stall_detection import BenchmarkSemantics  # noqa: E402


def test_active_peer_dwell_never_says_typical_for_days():
    phrase = i18n.days_vs_typical_phrase(79.0, BenchmarkSemantics.ACTIVE_PEER_DWELL)
    assert "typical" not in phrase
    assert "79" in phrase


def test_active_peer_dwell_never_says_typical_for_days_negative():
    phrase = i18n.days_vs_typical_phrase(-12.0, BenchmarkSemantics.ACTIVE_PEER_DWELL)
    assert "typical" not in phrase
    assert "12" in phrase


def test_active_peer_dwell_never_says_typical_for_count():
    phrase = i18n.count_vs_typical_phrase(4.0, BenchmarkSemantics.ACTIVE_PEER_DWELL)
    assert "typical" not in phrase
    assert "4" in phrase


def test_active_peer_dwell_metric_label_never_says_typical():
    assert "typical" not in i18n.extra_time_metric_label(BenchmarkSemantics.ACTIVE_PEER_DWELL)
    assert "typical" not in i18n.extra_count_metric_label(BenchmarkSemantics.ACTIVE_PEER_DWELL)


def test_completed_interval_may_say_typical_for_days():
    phrase = i18n.days_vs_typical_phrase(79.0, BenchmarkSemantics.COMPLETED_INTERVAL)
    assert "typical" in phrase
    assert "79" in phrase


def test_completed_interval_may_say_typical_for_count():
    phrase = i18n.count_vs_typical_phrase(4.0, BenchmarkSemantics.COMPLETED_INTERVAL)
    assert "typical" in phrase
    assert "4" in phrase


def test_completed_interval_metric_label_may_say_typical():
    assert "typical" in i18n.extra_time_metric_label(BenchmarkSemantics.COMPLETED_INTERVAL)
    assert "typical" in i18n.extra_count_metric_label(BenchmarkSemantics.COMPLETED_INTERVAL)
