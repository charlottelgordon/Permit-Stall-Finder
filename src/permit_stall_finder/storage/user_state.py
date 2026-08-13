"""Persistence for a return user's recent search history -- so someone
who checks the same permit(s) every day for their job doesn't have to
retype a search each time. Same DuckDB connection and naive-UTC-timestamp
convention as storage/snapshots.py (see that module's _to_utc_naive
docstring for why: DuckDB's TIMESTAMP column silently reinterprets a
tz-aware datetime in local time, so everything here is stored naive-UTC
and re-tagged UTC on the way out).

There's no user-account system anywhere in this app, so "recent" is
app-wide state, not per-person -- the same scope every other table in
storage/db.py already has. And like permit_snapshots, this data persists
only as long as the deployed app's underlying filesystem does: it
survives across sessions and reruns, but a redeploy/reboot starts it
over, exactly the same caveat that already applies to permit journey
history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import duckdb

VALID_KINDS = ("permit_number", "address")


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)


def _from_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class SearchHistoryEntry:
    kind: str
    value: str
    searched_at: datetime


def record_search(
    conn: duckdb.DuckDBPyConnection, kind: str, value: str, *, now: datetime | None = None
) -> None:
    """Upserts (kind, value)'s searched_at to now. Searching the same
    thing again moves it back to the top of "recent" rather than creating
    a second row for it -- recent searches are meant to be a short list of
    distinct things a user actually cares about, not a raw click log."""
    assert kind in VALID_KINDS, f"unknown kind {kind!r}"
    ts = _to_utc_naive(now or datetime.now(timezone.utc))
    conn.execute(
        """
        INSERT INTO search_history (kind, value, searched_at) VALUES (?, ?, ?)
        ON CONFLICT (kind, value) DO UPDATE SET searched_at = excluded.searched_at
        """,
        [kind, value, ts],
    )


def read_recent_searches(
    conn: duckdb.DuckDBPyConnection, *, limit: int = 8
) -> list[SearchHistoryEntry]:
    """Most-recently-searched first, capped at `limit` -- this backs a
    short quick-access list, not a full audit trail."""
    rows = conn.execute(
        "SELECT kind, value, searched_at FROM search_history ORDER BY searched_at DESC LIMIT ?",
        [limit],
    ).fetchall()
    return [
        SearchHistoryEntry(kind=r[0], value=r[1], searched_at=_from_utc_naive(r[2]))
        for r in rows
    ]
