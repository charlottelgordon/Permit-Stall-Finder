"""Persistence for a user's starred searches -- a permit-number query or
an address, starred as a whole re-expandable unit (see storage/db.py's
starred_searches table comment for why this isn't shaped like
search_history), so "My Permits" can re-derive the same permit list on a
later visit. Same naive-UTC-timestamp convention as user_state.py/
snapshots.py (see either module's _to_utc_naive docstring for why),
including its own copy of the conversion pair rather than importing
one -- the existing precedent in this package (user_state.py and
snapshots.py each keep their own).

uid is an anonymous per-browser id (app/browser_id.py) -- there's no
user-account system in this app, so unlike every other table in
storage/db.py, uid is a real partition key here, scoping every read/write
to one browser. Like every other table here, this data persists only as
long as the deployed app's underlying filesystem does: it survives across
sessions and reruns, but a redeploy/reboot starts it over -- the same
caveat search_history and permit_snapshots already carry, not a new
regression.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import duckdb

VALID_KINDS = ("permit_query", "address")


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
class StarredSearchEntry:
    uid: str
    kind: str
    value: str
    starred_at: datetime


def star_search(
    conn: duckdb.DuckDBPyConnection, uid: str, kind: str, value: str, *, now: datetime | None = None
) -> None:
    """Upserts (uid, kind, value)'s starred_at to now -- starring the same
    search again moves it back to the top rather than creating a second
    row, same idiom as user_state.record_search."""
    assert kind in VALID_KINDS, f"unknown kind {kind!r}"
    ts = _to_utc_naive(now or datetime.now(timezone.utc))
    conn.execute(
        """
        INSERT INTO starred_searches (uid, kind, value, starred_at) VALUES (?, ?, ?, ?)
        ON CONFLICT (uid, kind, value) DO UPDATE SET starred_at = excluded.starred_at
        """,
        [uid, kind, value, ts],
    )


def unstar_search(conn: duckdb.DuckDBPyConnection, uid: str, kind: str, value: str) -> None:
    conn.execute(
        "DELETE FROM starred_searches WHERE uid = ? AND kind = ? AND value = ?",
        [uid, kind, value],
    )


def is_starred(conn: duckdb.DuckDBPyConnection, uid: str, kind: str, value: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM starred_searches WHERE uid = ? AND kind = ? AND value = ? LIMIT 1",
        [uid, kind, value],
    ).fetchone()
    return row is not None


def read_starred_searches(
    conn: duckdb.DuckDBPyConnection, uid: str, *, limit: int = 50
) -> list[StarredSearchEntry]:
    """Most-recently-starred first, scoped to this uid only -- never reads
    or returns another browser's stars."""
    rows = conn.execute(
        "SELECT uid, kind, value, starred_at FROM starred_searches "
        "WHERE uid = ? ORDER BY starred_at DESC LIMIT ?",
        [uid, limit],
    ).fetchall()
    return [
        StarredSearchEntry(uid=r[0], kind=r[1], value=r[2], starred_at=_from_utc_naive(r[3]))
        for r in rows
    ]
