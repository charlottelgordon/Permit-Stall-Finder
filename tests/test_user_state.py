"""Tests for storage/user_state.py -- the recent-search-history
persistence backing a possible future "return user" quick-access UI.
Same offline, in-memory-DuckDB-per-test pattern as
test_permit_query_escaping.py etc., via the shared `conn` fixture in
conftest.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from permit_stall_finder.storage import user_state

T1 = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)
T3 = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)


# --- recent searches ---------------------------------------------------


def test_record_search_then_read_recent(conn):
    user_state.record_search(conn, "permit_number", "21030-20000-00256", now=T1)

    recent = user_state.read_recent_searches(conn)

    assert len(recent) == 1
    assert recent[0].kind == "permit_number"
    assert recent[0].value == "21030-20000-00256"
    assert recent[0].searched_at == T1


def test_record_search_again_moves_to_top_not_duplicated():
    import duckdb

    from permit_stall_finder.storage.db import DDL

    conn = duckdb.connect(":memory:")
    conn.execute(DDL)

    user_state.record_search(conn, "permit_number", "A", now=T1)
    user_state.record_search(conn, "permit_number", "B", now=T2)
    user_state.record_search(conn, "permit_number", "A", now=T3)  # re-search A

    recent = user_state.read_recent_searches(conn)

    assert [r.value for r in recent] == ["A", "B"]  # A moved to top, still only 2 rows
    assert recent[0].searched_at == T3


def test_read_recent_searches_respects_limit(conn):
    for i, value in enumerate(["A", "B", "C", "D"]):
        user_state.record_search(conn, "permit_number", value, now=T1)

    recent = user_state.read_recent_searches(conn, limit=2)

    assert len(recent) == 2


def test_read_recent_searches_empty_when_nothing_searched(conn):
    assert user_state.read_recent_searches(conn) == []
