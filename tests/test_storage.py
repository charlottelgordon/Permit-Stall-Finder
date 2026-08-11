"""Storage round-trip tests. Regression coverage for a real bug found while
demonstrating Agent 1: DuckDB's TIMESTAMP column has no timezone concept,
so a tz-aware datetime silently gets reinterpreted as local time on
storage — a UTC observed_at was coming back shifted by the machine's local
UTC offset. storage/snapshots.py now converts to naive-UTC before writing
and reattaches tzinfo=timezone.utc on read; these tests pin that behavior."""

from __future__ import annotations

from datetime import date, datetime, timezone

from permit_stall_finder.schema.journey import PermitSnapshot
from permit_stall_finder.storage import snapshots as storage


def _snapshot(observed_at: datetime, source_updated_at=None) -> PermitSnapshot:
    return PermitSnapshot(
        source_dataset_id="gwh9-jnip",
        source_record_id="row-test",
        source_updated_at=source_updated_at,
        observed_at=observed_at,
        source_refresh_time=date(2026, 8, 9),
        permit_number="TEST-1",
        permit_type="Bldg-Alter/Repair",
        permit_sub_type=None,
        business_unit=None,
        work_description=None,
        submitted_date=date(2024, 1, 1),
        status_desc="Issued",
        status_date=date(2024, 2, 1),
        issue_date=date(2024, 2, 1),
        cofo_date=None,
        valuation=None,
        raw={"permit_nbr": "TEST-1"},
    )


def test_utc_observed_at_survives_round_trip_unchanged(conn):
    observed_at = datetime(2026, 8, 11, 16, 16, 51, 928951, tzinfo=timezone.utc)
    source_updated_at = datetime(2026, 8, 10, 15, 10, 43, 831000, tzinfo=timezone.utc)

    storage.persist_permit_snapshot(conn, _snapshot(observed_at, source_updated_at))
    [read_back] = storage.read_snapshot_history(conn, "TEST-1")

    assert read_back.observed_at == observed_at
    assert read_back.observed_at.tzinfo is not None
    assert read_back.source_updated_at == source_updated_at


def test_non_utc_observed_at_is_normalized_to_utc_on_round_trip(conn):
    # e.g. datetime.now(some_local_tz) — must not be silently reinterpreted
    from datetime import timedelta, timezone as tz

    pdt = tz(timedelta(hours=-7))
    observed_at_pdt = datetime(2026, 8, 11, 9, 16, 51, tzinfo=pdt)

    storage.persist_permit_snapshot(conn, _snapshot(observed_at_pdt))
    [read_back] = storage.read_snapshot_history(conn, "TEST-1")

    assert read_back.observed_at == observed_at_pdt  # same instant
    assert read_back.observed_at == datetime(2026, 8, 11, 16, 16, 51, tzinfo=timezone.utc)


def test_repeated_snapshots_are_both_persisted_append_only(conn):
    t1 = datetime(2026, 8, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 8, 8, tzinfo=timezone.utc)
    storage.persist_permit_snapshot(conn, _snapshot(t1))
    storage.persist_permit_snapshot(conn, _snapshot(t2))

    history = storage.read_snapshot_history(conn, "TEST-1")
    assert [s.observed_at for s in history] == [t1, t2]
