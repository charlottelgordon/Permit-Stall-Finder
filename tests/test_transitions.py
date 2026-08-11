"""Unit tests for schema/transitions.py — synthetic snapshots, no fixtures
needed. Verifies the weak/strong status-persistence language distinction:
a single observation only supports "current status is X," never "has
continuously remained in X since Y," which requires repeated observation."""

from __future__ import annotations

from datetime import date, datetime, timezone

from permit_stall_finder.schema.journey import PermitSnapshot
from permit_stall_finder.schema.transitions import collapse_snapshots_to_transitions


def _snapshot(status_desc: str, observed_at: datetime, status_date=None) -> PermitSnapshot:
    return PermitSnapshot(
        source_dataset_id="gwh9-jnip",
        source_record_id="row-test",
        source_updated_at=None,
        observed_at=observed_at,
        source_refresh_time=None,
        permit_number="TEST-1",
        permit_type="Bldg-Alter/Repair",
        permit_sub_type=None,
        business_unit=None,
        work_description=None,
        submitted_date=date(2024, 1, 1),
        status_desc=status_desc,
        status_date=status_date,
        issue_date=None,
        cofo_date=None,
        valuation=None,
        raw={},
    )


def test_single_observation_uses_weak_language():
    snap = _snapshot("PC Approved", datetime(2024, 3, 1, tzinfo=timezone.utc))
    transitions = collapse_snapshots_to_transitions([snap])

    assert len(transitions) == 1
    t = transitions[0]
    assert t.observation_count == 1
    assert not t.confirmed_by_repeated_observation
    assert "Observed once" in t.describe()
    assert "continuously remained" not in t.describe()


def test_repeated_identical_snapshots_collapse_and_support_strong_language():
    snaps = [
        _snapshot("PC Approved", datetime(2024, 3, 1, tzinfo=timezone.utc)),
        _snapshot("PC Approved", datetime(2024, 3, 8, tzinfo=timezone.utc)),
        _snapshot("PC Approved", datetime(2024, 3, 15, tzinfo=timezone.utc)),
    ]
    transitions = collapse_snapshots_to_transitions(snaps)

    assert len(transitions) == 1
    t = transitions[0]
    assert t.observation_count == 3
    assert t.confirmed_by_repeated_observation
    assert "confirmed present across 3 observations" in t.describe()
    assert "2024-03-01" in t.describe()
    assert "2024-03-15" in t.describe()


def test_status_change_produces_separate_transitions_in_order():
    snaps = [
        _snapshot("PC Approved", datetime(2024, 3, 1, tzinfo=timezone.utc)),
        _snapshot("Ready to Issue", datetime(2024, 3, 8, tzinfo=timezone.utc)),
        _snapshot("Issued", datetime(2024, 3, 15, tzinfo=timezone.utc)),
    ]
    transitions = collapse_snapshots_to_transitions(snaps)

    assert [t.status_desc for t in transitions] == ["PC Approved", "Ready to Issue", "Issued"]
    assert all(t.observation_count == 1 for t in transitions)


def test_empty_history_produces_no_transitions():
    assert collapse_snapshots_to_transitions([]) == []
