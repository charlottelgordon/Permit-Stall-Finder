"""A running tally of search actions performed -- backs the homepage's
"N searches run" civic-impact stat. Separate on purpose from
user_state.py's search_history, which upserts on (kind, value) and so
never grows past the number of *distinct* things ever searched; this is
a plain append-only log, one row per successful search submission,
counting repeat searches too, the same way a page-view counter would.

App-wide, like every table in this storage layer except starred_searches
(see storage/db.py's own comment on that one) -- there's no per-user
scoping here, and none is wanted: this is a single citywide-visible
number, not a personal stat.

Caveat this module can't fix: the DuckDB file behind this is local and
gitignored (config.DEFAULT_DB_PATH), and on Streamlit Community Cloud it
resets on every redeploy/reboot -- the exact same limitation
user_state.py's search_history already documents. This counter is real
and accurate between deploys, but a code push resets it to zero, the
same as every other table here.
"""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb

VALID_KINDS = ("permit_query", "address")


def _to_utc_naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    return dt.replace(tzinfo=None)


def record_search_event(conn: duckdb.DuckDBPyConnection, kind: str, *, now: datetime | None = None) -> None:
    """Appends one row -- call exactly once per successful search
    submission (a Search-button click that resolved to at least one
    permit), not once per permit number within it, so a 5-permit paste
    counts as 1 search, not 5."""
    assert kind in VALID_KINDS, f"unknown kind {kind!r}"
    ts = _to_utc_naive(now or datetime.now(timezone.utc))
    conn.execute("INSERT INTO search_event_log (kind, searched_at) VALUES (?, ?)", [kind, ts])


def count_search_events(conn: duckdb.DuckDBPyConnection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM search_event_log").fetchone()
    return int(row[0]) if row else 0
