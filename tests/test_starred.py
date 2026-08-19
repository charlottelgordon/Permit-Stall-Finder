"""Tests for storage/starred.py -- starred-search persistence backing the
"star a search, auto-load it later" feature. Same offline,
in-memory-DuckDB-per-test pattern as test_user_state.py, via the shared
`conn` fixture in conftest.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from permit_stall_finder.storage import starred

T1 = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 8, 11, 9, 0, tzinfo=timezone.utc)
T3 = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)

UID_A = "browser-a"
UID_B = "browser-b"


def test_star_then_read(conn):
    starred.star_search(conn, UID_A, "permit_query", "21030-20000-00256", now=T1)

    entries = starred.read_starred_searches(conn, UID_A)

    assert len(entries) == 1
    assert entries[0].uid == UID_A
    assert entries[0].kind == "permit_query"
    assert entries[0].value == "21030-20000-00256"
    assert entries[0].starred_at == T1


def test_star_again_moves_to_top_not_duplicated(conn):
    starred.star_search(conn, UID_A, "permit_query", "A", now=T1)
    starred.star_search(conn, UID_A, "permit_query", "B", now=T2)
    starred.star_search(conn, UID_A, "permit_query", "A", now=T3)  # re-star A

    entries = starred.read_starred_searches(conn, UID_A)

    assert [e.value for e in entries] == ["A", "B"]  # A moved to top, still only 2 rows
    assert entries[0].starred_at == T3


def test_unstar_removes(conn):
    starred.star_search(conn, UID_A, "address", "123 Main St", now=T1)
    starred.unstar_search(conn, UID_A, "address", "123 Main St")

    assert starred.read_starred_searches(conn, UID_A) == []


def test_is_starred_reflects_state(conn):
    assert starred.is_starred(conn, UID_A, "permit_query", "A") is False

    starred.star_search(conn, UID_A, "permit_query", "A", now=T1)
    assert starred.is_starred(conn, UID_A, "permit_query", "A") is True

    starred.unstar_search(conn, UID_A, "permit_query", "A")
    assert starred.is_starred(conn, UID_A, "permit_query", "A") is False


def test_read_starred_searches_empty_when_nothing_starred(conn):
    assert starred.read_starred_searches(conn, UID_A) == []


def test_uid_isolation_never_leaks_across_browsers(conn):
    starred.star_search(conn, UID_A, "permit_query", "A-only", now=T1)
    starred.star_search(conn, UID_B, "permit_query", "B-only", now=T1)

    a_entries = starred.read_starred_searches(conn, UID_A)
    b_entries = starred.read_starred_searches(conn, UID_B)

    assert [e.value for e in a_entries] == ["A-only"]
    assert [e.value for e in b_entries] == ["B-only"]
    assert starred.is_starred(conn, UID_B, "permit_query", "A-only") is False
