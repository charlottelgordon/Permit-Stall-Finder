"""Persistence for permit snapshots, inspection events, and the
reconstruction log. Read paths return schema objects (PermitSnapshot /
InspectionEvent), never raw rows, so storage details stay out of the
agent layer."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import duckdb

from permit_stall_finder.schema.journey import InspectionEvent, PermitSnapshot


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    """DuckDB's TIMESTAMP column has no timezone concept: a tz-aware
    datetime gets silently converted to the machine's local time and
    stored as if it were naive, which would corrupt observed_at/
    source_updated_at by the local UTC offset. Storing everything as
    explicit naive-UTC avoids that silent conversion; _from_utc_naive
    reattaches tzinfo on the way back out."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)


def _from_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc)


def persist_permit_snapshot(conn: duckdb.DuckDBPyConnection, snapshot: PermitSnapshot) -> None:
    conn.execute(
        """
        INSERT INTO permit_snapshots (
            permit_number, observed_at, source_dataset_id, source_record_id,
            source_updated_at, source_refresh_time, permit_type, permit_sub_type,
            business_unit, work_description, submitted_date, status_desc,
            status_date, issue_date, cofo_date, valuation, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (permit_number, observed_at) DO NOTHING
        """,
        [
            snapshot.permit_number,
            _to_utc_naive(snapshot.observed_at),
            snapshot.source_dataset_id,
            snapshot.source_record_id,
            _to_utc_naive(snapshot.source_updated_at),
            snapshot.source_refresh_time,
            snapshot.permit_type,
            snapshot.permit_sub_type,
            snapshot.business_unit,
            snapshot.work_description,
            snapshot.submitted_date,
            snapshot.status_desc,
            snapshot.status_date,
            snapshot.issue_date,
            snapshot.cofo_date,
            snapshot.valuation,
            json.dumps(snapshot.raw),
        ],
    )


def persist_inspection_events(
    conn: duckdb.DuckDBPyConnection, events: list[InspectionEvent]
) -> None:
    for event in events:
        conn.execute(
            """
            INSERT INTO inspection_events (
                event_id, permit_number, source_dataset_id, source_record_id,
                source_updated_at, observed_at, inspection_date, inspection_type,
                inspection_result, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (event_id) DO NOTHING
            """,
            [
                event.event_id,
                event.permit_number,
                event.source_dataset_id,
                event.source_record_id,
                _to_utc_naive(event.source_updated_at),
                _to_utc_naive(event.observed_at),
                event.inspection_date,
                event.inspection_type,
                event.inspection_result,
                json.dumps(event.raw),
            ],
        )


def read_snapshot_history(
    conn: duckdb.DuckDBPyConnection, permit_number: str
) -> list[PermitSnapshot]:
    rows = conn.execute(
        """
        SELECT permit_number, observed_at, source_dataset_id, source_record_id,
               source_updated_at, source_refresh_time, permit_type, permit_sub_type,
               business_unit, work_description, submitted_date, status_desc,
               status_date, issue_date, cofo_date, valuation, raw_json
        FROM permit_snapshots
        WHERE permit_number = ?
        ORDER BY observed_at
        """,
        [permit_number],
    ).fetchall()

    snapshots = []
    for r in rows:
        snapshots.append(
            PermitSnapshot(
                permit_number=r[0],
                observed_at=_from_utc_naive(r[1]),
                source_dataset_id=r[2],
                source_record_id=r[3],
                source_updated_at=_from_utc_naive(r[4]),
                source_refresh_time=r[5],
                permit_type=r[6],
                permit_sub_type=r[7],
                business_unit=r[8],
                work_description=r[9],
                submitted_date=r[10],
                status_desc=r[11],
                status_date=r[12],
                issue_date=r[13],
                cofo_date=r[14],
                valuation=r[15],
                raw=json.loads(r[16]) if r[16] else {},
            )
        )
    return snapshots


def read_inspection_events(
    conn: duckdb.DuckDBPyConnection, permit_number: str
) -> list[InspectionEvent]:
    rows = conn.execute(
        """
        SELECT event_id, permit_number, source_dataset_id, source_record_id,
               source_updated_at, observed_at, inspection_date, inspection_type,
               inspection_result, raw_json
        FROM inspection_events
        WHERE permit_number = ?
        ORDER BY inspection_date
        """,
        [permit_number],
    ).fetchall()

    events = []
    for r in rows:
        events.append(
            InspectionEvent(
                event_id=r[0],
                permit_number=r[1],
                source_dataset_id=r[2],
                source_record_id=r[3],
                source_updated_at=_from_utc_naive(r[4]),
                observed_at=_from_utc_naive(r[5]),
                inspection_date=r[6],
                inspection_type=r[7],
                inspection_result=r[8],
                raw=json.loads(r[9]) if r[9] else {},
            )
        )
    return events


def log_reconstruction_issue(
    conn: duckdb.DuckDBPyConnection,
    permit_number: str,
    issue_type: str,
    detail: str,
    observed_at: datetime | None = None,
) -> None:
    conn.execute(
        "INSERT INTO reconstruction_log (permit_number, observed_at, issue_type, detail) "
        "VALUES (?, ?, ?, ?)",
        [
            permit_number,
            _to_utc_naive(observed_at or datetime.now(timezone.utc)),
            issue_type,
            detail,
        ],
    )
