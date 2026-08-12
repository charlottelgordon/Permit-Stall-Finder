"""Tests for permits.fetch_permits_by_address() -- the address->permit_number
resolver added for the "search by address" UI flow, and for the
primary_address/lat/lon fields added to PERMIT_FIELDS.

Deliberately isolated (like test_permit_query_escaping.py) so both fixes
are easy to review as self-contained diffs, separate from the UI they
support. Every $where-building test here follows the same
mock-socrata.query-and-inspect-captured-params pattern that file already
established.
"""

from __future__ import annotations

from permit_stall_finder.ingestion import permits


def test_permit_fields_includes_address_and_coordinates():
    # Regression guard for the bug this session found: the UI already read
    # raw.get("primary_address")/raw.get("lat")/raw.get("lon"), but Socrata's
    # $select silently dropped them because PERMIT_FIELDS never listed them.
    assert "primary_address" in permits.PERMIT_FIELDS
    assert "lat" in permits.PERMIT_FIELDS
    assert "lon" in permits.PERMIT_FIELDS
    assert "zip_code" in permits.PERMIT_FIELDS


def test_fetch_permits_by_address_sends_escaped_case_insensitive_where(monkeypatch):
    captured = {}

    def fake_query(dataset_id, params, base_url):
        captured.update(params)
        return []

    monkeypatch.setattr(permits.socrata, "query", fake_query)

    permits.fetch_permits_by_address("256 S Spring St")

    assert captured["$where"] == "upper(primary_address) like upper('%256 S Spring St%')"
    assert captured["$order"] == "status_date DESC"
    assert captured["$limit"] == str(permits.ADDRESS_SEARCH_LIMIT)
    assert "primary_address" in captured["$select"]
    assert "lat" in captured["$select"]
    assert "lon" in captured["$select"]


def test_fetch_permits_by_address_escapes_apostrophe_input(monkeypatch):
    captured = {}

    def fake_query(dataset_id, params, base_url):
        captured.update(params)
        return []

    monkeypatch.setattr(permits.socrata, "query", fake_query)

    permits.fetch_permits_by_address("O'Brien Ave")

    assert captured["$where"] == "upper(primary_address) like upper('%O''Brien Ave%')"
    assert captured["$where"].count("'") % 2 == 0


def test_fetch_permits_by_address_escapes_injection_attempt_without_raising(monkeypatch):
    captured = {}

    def fake_query(dataset_id, params, base_url):
        captured.update(params)
        return []

    monkeypatch.setattr(permits.socrata, "query", fake_query)

    payload = "x' OR '1'='1"
    permits.fetch_permits_by_address(payload)

    assert captured["$where"].count("'") % 2 == 0
    assert "OR ''1''=''1" in captured["$where"]


def test_fetch_permits_by_address_respects_custom_limit(monkeypatch):
    captured = {}

    def fake_query(dataset_id, params, base_url):
        captured.update(params)
        return []

    monkeypatch.setattr(permits.socrata, "query", fake_query)

    permits.fetch_permits_by_address("Main St", limit=3)

    assert captured["$limit"] == "3"


def test_fetch_permits_by_address_returns_empty_list_for_no_matches(monkeypatch):
    monkeypatch.setattr(permits.socrata, "query", lambda dataset_id, params, base_url: [])

    result = permits.fetch_permits_by_address("nonexistent address zzz")

    assert result == []


def test_fetch_permits_by_address_returns_rows_unchanged(monkeypatch):
    fake_rows = [
        {"permit_nbr": "25016-20000-34482", "primary_address": "416 S SPRING ST"},
        {"permit_nbr": "22014-20000-00688", "primary_address": "416 S SPRING ST # 1207"},
    ]
    monkeypatch.setattr(permits.socrata, "query", lambda dataset_id, params, base_url: fake_rows)

    result = permits.fetch_permits_by_address("416 S Spring")

    assert result == fake_rows

