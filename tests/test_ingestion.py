"""Ingestion-layer unit tests: permit-number normalization and the
deterministic event_id fallback used only when a source row lacks a
Socrata :id system column (not observed in practice so far, but the
fallback path itself must still be correct)."""

from __future__ import annotations

from permit_stall_finder.ingestion.inspections import parse_inspection_event
from permit_stall_finder.ingestion.socrata import normalize_permit


def test_normalize_permit_strips_separators_and_uppercases():
    assert normalize_permit("21030-20000-00256") == normalize_permit("21030 20000 00256")
    assert normalize_permit("abc-123") == "ABC123"


def test_event_id_uses_source_system_id_when_present():
    raw = {
        ":id": "row-789q.jfdb~2vgh",
        "inspection_date": "2021-09-15T00:00:00.000",
        "inspection": "BUILDING-Rough-Frame",
        "inspection_result": "Approved",
    }
    event = parse_inspection_event(raw, "21016-20000-20141")
    assert event.event_id == "row-789q.jfdb~2vgh"
    assert event.source_record_id == "row-789q.jfdb~2vgh"


def test_event_id_falls_back_to_deterministic_hash_when_no_source_id():
    raw = {
        "inspection_date": "2021-09-15T00:00:00.000",
        "inspection": "BUILDING-Rough-Frame",
        "inspection_result": "Approved",
    }
    event = parse_inspection_event(raw, "21016-20000-20141")
    assert event.source_record_id is None
    assert event.event_id.startswith("hash:")

    # deterministic: same input -> same id, every time
    event2 = parse_inspection_event(raw, "21016-20000-20141")
    assert event.event_id == event2.event_id

    # a different event (different result) must not collide
    raw_other = {**raw, "inspection_result": "Not Ready for Inspection"}
    event3 = parse_inspection_event(raw_other, "21016-20000-20141")
    assert event3.event_id != event.event_id


def test_event_without_inspection_date_is_skipped():
    raw = {":id": "row-x", "inspection": "Final", "inspection_result": "Approved"}
    assert parse_inspection_event(raw, "21016-20000-20141") is None
