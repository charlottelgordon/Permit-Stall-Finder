"""Tests for storage/user_state.py -- the starred-items and
recent-search-history persistence backing the "return user" quick-access
UI. Same offline, in-memory-DuckDB-per-test pattern as
test_permit_query_escaping.py etc., via the shared `conn` fixture in
conftest.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from permit_stall_finder.storage import user_state

T1 = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)
T3 = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)


# --- starring --------------------------------------------------------


def test_star_item_then_is_starred(conn):
    assert user_state.is_starred(conn, "permit_number", "21030-20000-00256") is False

    user_state.star_item(conn, "permit_number", "21030-20000-00256", now=T1)

    assert user_state.is_starred(conn, "permit_number", "21030-20000-00256") is True


def test_star_item_is_idempotent(conn):
    user_state.star_item(conn, "permit_number", "21030-20000-00256", now=T1)
    user_state.star_item(conn, "permit_number", "21030-20000-00256", now=T2)  # starring again

    items = user_state.read_starred_items(conn)

    assert len(items) == 1
    assert items[0].starred_at == T1  # first star wins, not overwritten


def test_unstar_item_removes_it(conn):
    user_state.star_item(conn, "permit_number", "21030-20000-00256", now=T1)
    user_state.unstar_item(conn, "permit_number", "21030-20000-00256")

    assert user_state.is_starred(conn, "permit_number", "21030-20000-00256") is False
    assert user_state.read_starred_items(conn) == []


def test_unstar_item_missing_does_not_raise(conn):
    user_state.unstar_item(conn, "permit_number", "nonexistent")  # no-op, no error


def test_read_starred_items_most_recent_first(conn):
    user_state.star_item(conn, "permit_number", "A", now=T1)
    user_state.star_item(conn, "permit_number", "B", now=T3)
    user_state.star_item(conn, "address", "200 N Spring St", now=T2)

    items = user_state.read_starred_items(conn)

    assert [i.value for i in items] == ["B", "200 N Spring St", "A"]


def test_star_item_distinguishes_kind_for_same_value(conn):
    # A permit number and an address could theoretically collide as raw
    # strings -- kind keeps them as two distinct starred entries.
    user_state.star_item(conn, "permit_number", "12345", now=T1)
    user_state.star_item(conn, "address", "12345", now=T1)

    items = user_state.read_starred_items(conn)

    assert len(items) == 2
    assert {i.kind for i in items} == {"permit_number", "address"}


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
