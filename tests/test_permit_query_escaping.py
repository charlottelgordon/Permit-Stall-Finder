"""Regression tests for a real, pre-existing SoQL-escaping gap found during
UI-integration review: ingestion/permits.py interpolated permit_number into
a $where clause unescaped, while inspections.py and cohort_populations.py
already escaped the same kind of value. Low risk with CLI/test-only callers;
a public text input is a different trust boundary. Fixed by routing every
such interpolation through socrata.escape_soql_string() -- see
ingestion/socrata.py and the one call site in ingestion/permits.py.

Deliberately isolated in its own file (not folded into test_ingestion.py)
so this fix is easy to review as a self-contained diff, separate from the
UI implementation it was found while building.
"""

from __future__ import annotations

from permit_stall_finder.ingestion import permits
from permit_stall_finder.ingestion.socrata import escape_soql_string


def test_escape_soql_string_leaves_normal_permit_number_unchanged():
    assert escape_soql_string("21030-20000-00256") == "21030-20000-00256"


def test_escape_soql_string_doubles_a_single_apostrophe():
    assert escape_soql_string("O'Brien") == "O''Brien"


def test_escape_soql_string_doubles_every_quote_in_an_injection_attempt():
    payload = "21030-20000-00256' OR '1'='1"
    escaped = escape_soql_string(payload)
    assert escaped == "21030-20000-00256'' OR ''1''=''1"
    # every quote is paired -- confirms the resulting literal is syntactically closed
    assert escaped.count("'") % 2 == 0


def test_escape_soql_string_handles_obviously_malformed_input_without_raising():
    for payload in (
        "",
        "   ",
        "'; DROP TABLE permits; --",
        "a" * 5000,
        "☃💥 unicode 漢字",
        "\n\t\x00",
    ):
        result = escape_soql_string(payload)
        assert isinstance(result, str)
        assert result.count("'") == payload.count("'") * 2


def test_fetch_raw_permit_row_sends_escaped_where_clause_for_normal_input(monkeypatch):
    captured = {}

    def fake_query(dataset_id, params, base_url):
        captured.update(params)
        return []

    monkeypatch.setattr(permits.socrata, "query", fake_query)

    permits.fetch_raw_permit_row("21030-20000-00256")

    assert captured["$where"] == "permit_nbr='21030-20000-00256'"


def test_fetch_raw_permit_row_sends_escaped_where_clause_for_apostrophe_input(monkeypatch):
    captured = {}

    def fake_query(dataset_id, params, base_url):
        captured.update(params)
        return []

    monkeypatch.setattr(permits.socrata, "query", fake_query)

    permits.fetch_raw_permit_row("21030-20000-00256' OR '1'='1")

    # the quotes in the malicious input are doubled, so the $where clause's
    # own single-quoted literal stays syntactically closed rather than
    # letting the input break out of it
    assert captured["$where"] == "permit_nbr='21030-20000-00256'' OR ''1''=''1'"
    assert captured["$where"].count("'") % 2 == 0


def test_fetch_raw_permit_row_handles_malformed_input_without_raising(monkeypatch):
    def fake_query(dataset_id, params, base_url):
        return []

    monkeypatch.setattr(permits.socrata, "query", fake_query)

    for payload in ("", "   ", "'; DROP TABLE permits; --", "a" * 5000, "☃💥"):
        result = permits.fetch_raw_permit_row(payload)
        assert result is None  # fake_query returns [] -> None, no crash
