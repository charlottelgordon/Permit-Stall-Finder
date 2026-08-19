"""Tests for storage/search_counter.py -- the append-only search-event
tally backing the homepage's civic-impact stat. Same offline,
in-memory-DuckDB-per-test pattern as test_user_state.py/test_starred.py,
via the shared `conn` fixture in conftest.py.
"""

from __future__ import annotations

from datetime import datetime, timezone

from permit_stall_finder.storage import search_counter

T1 = datetime(2026, 8, 10, 9, 0, tzinfo=timezone.utc)


def test_count_search_events_starts_at_zero(conn):
    assert search_counter.count_search_events(conn) == 0


def test_record_search_event_increments_count(conn):
    search_counter.record_search_event(conn, "permit_query", now=T1)

    assert search_counter.count_search_events(conn) == 1


def test_repeat_searches_each_count_separately(conn):
    # Deliberately distinct from user_state.record_search's upsert
    # behavior -- searching the same thing again must still increment,
    # not overwrite in place.
    search_counter.record_search_event(conn, "permit_query", now=T1)
    search_counter.record_search_event(conn, "permit_query", now=T1)
    search_counter.record_search_event(conn, "address", now=T1)

    assert search_counter.count_search_events(conn) == 3
