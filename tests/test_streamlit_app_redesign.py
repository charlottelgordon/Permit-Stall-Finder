"""Offline end-to-end smoke test for the Phase 10 redesign. Runs
streamlit_app.py via AppTest with run_pipeline / fetch_permits_by_address
monkeypatched to fixture data (no live network access in this sandbox),
driving: search -> unified results table -> row selection -> drill-down
tab -> expandable sections -> "other permits at this address" click ->
second drill-down tab opens."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "app"))
FIXTURES = REPO / "tests" / "fixtures"

import portfolio
import drill_down

from permit_stall_finder.orchestration.pipeline import run_pipeline as real_run_pipeline
from permit_stall_finder.ingestion import cohort_populations as pop

_DEFAULT_POPULATION = [float(i) for i in range(50)]


def _fixture_fetchers(name):
    with open(FIXTURES / f"{name}_permit.json") as f:
        raw_permit = json.load(f)
    with open(FIXTURES / f"{name}_inspections.json") as f:
        raw_inspections = json.load(f)

    def fetch_permit_row(permit_number):
        return raw_permit

    def fetch_inspection_rows(permit_number):
        return raw_inspections

    return fetch_permit_row, fetch_inspection_rows


# Two real permit numbers from the fixtures, used as "this permit" and
# "another permit at the same address" for the drill-down flow.
PERMIT_A = "21010-10000-05865"  # corrections_then_reinspection -- has stall detections
PERMIT_B = "21030-20000-00256"  # unissued -- clean read

_FIXTURE_BY_PERMIT = {
    PERMIT_A: "corrections_then_reinspection",
    PERMIT_B: "unissued",
}


def _fake_run_pipeline(conn, permit_number, sample_size=None):
    fetch_permit, fetch_inspections = _fixture_fetchers(_FIXTURE_BY_PERMIT[permit_number])
    return real_run_pipeline(
        conn, permit_number,
        fetch_permit_row=fetch_permit, fetch_inspection_rows=fetch_inspections,
    )


def _fake_fetch_permits_by_address(address):
    return [
        {"permit_nbr": PERMIT_A, "permit_type": "Bldg-Alter/Repair", "status_desc": "Issued", "primary_address": address},
        {"permit_nbr": PERMIT_B, "permit_type": "Bldg-Alter/Repair", "status_desc": "Plan Check Approved", "primary_address": address},
    ]


def apply_patches(monkeypatch):
    monkeypatch.setattr(pop, "fetch_pre_issuance_dwell_population", lambda *a, **k: list(_DEFAULT_POPULATION))
    monkeypatch.setattr(pop, "fetch_issuance_to_first_inspection_population", lambda *a, **k: list(_DEFAULT_POPULATION))
    monkeypatch.setattr(pop, "fetch_inter_inspection_gap_population", lambda *a, **k: list(_DEFAULT_POPULATION))
    monkeypatch.setattr(pop, "fetch_friction_count_population", lambda *a, **k: list(_DEFAULT_POPULATION))
    monkeypatch.setattr(pop, "fetch_finalization_gap_population", lambda *a, **k: list(_DEFAULT_POPULATION))
    monkeypatch.setattr(portfolio, "run_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(drill_down, "run_pipeline", _fake_run_pipeline)
    monkeypatch.setattr(drill_down, "fetch_permits_by_address", _fake_fetch_permits_by_address)
    # The fixture permit rows don't carry primary_address (not needed by
    # any other test) -- pin it here so the "Other permits at this
    # address" flow has something to look up.
    monkeypatch.setattr(portfolio, "address_of", lambda result: "123 Test St")


def test_full_redesign_flow(monkeypatch):
    apply_patches(monkeypatch)
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(REPO / "app" / "streamlit_app.py"))
    at.run()
    assert not at.exception, f"initial render failed: {at.exception}"

    # Type a single permit number and click Search.
    at.text_input(key="unified_search_input").set_value(PERMIT_A)
    at.button(key="unified_search_button").click().run()
    assert not at.exception, f"search failed: {at.exception}"

    # Results table rendered with 9 columns worth of data, and the
    # single-permit search auto-opened its drill-down tab.
    assert at.dataframe, "results table did not render"
    tabs = at.tabs
    assert len(tabs) >= 1, "drill-down tab did not auto-open for single-permit search"
    assert PERMIT_A in [t.label for t in tabs]

    # Expand "Other permits at this address" inside the tab and click to
    # open PERMIT_B as a second drill-down tab.
    other_buttons = [b for b in at.button if b.label == "Open"]
    assert other_buttons, "no 'Open' button found under Other permits at this address"
    other_buttons[0].click().run()
    assert not at.exception, f"opening other permit failed: {at.exception}"

    tabs_after = at.tabs
    assert len(tabs_after) == 2, f"expected 2 drill-down tabs, got {[t.label for t in tabs_after]}"
    assert set(t.label for t in tabs_after) == {PERMIT_A, PERMIT_B}

    print("E2E FLOW OK")


def test_multi_permit_search_table_and_row_selection(monkeypatch):
    apply_patches(monkeypatch)
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(REPO / "app" / "streamlit_app.py"))
    at.run()

    at.text_input(key="unified_search_input").set_value(f"{PERMIT_A}, {PERMIT_B}")
    at.button(key="unified_search_button").click().run()
    assert not at.exception, f"multi search failed: {at.exception}"

    assert at.dataframe, "results table did not render for multi-permit search"
    # Nothing should be auto-opened for a multi-permit search until a row
    # is actually selected.
    assert len(at.tabs) == 0, f"expected no drill-down tabs yet, got {[t.label for t in at.tabs]}"

    # Simulate the user clicking the first row of the results table.
    at.session_state["results_table"] = {"selection": {"rows": [0], "columns": [], "cells": []}}
    at.run()
    assert not at.exception, f"row-selection render failed: {at.exception}"
    assert len(at.tabs) == 1, f"expected exactly 1 drill-down tab, got {[t.label for t in at.tabs]}"


def test_header_and_language_toggle(monkeypatch):
    apply_patches(monkeypatch)
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(REPO / "app" / "streamlit_app.py"))
    at.run()
    assert not at.exception

    headers = [h.value for h in at.get("markdown") if "Permit Check LA" in h.value]
    assert headers, "app title header not found"
    guide_links = [m.value for m in at.markdown if "dbs.lacity.gov/services/homeowner-step-by-step" in m.value]
    assert guide_links, "homeowner guide link not found in header"

    toggles = at.get("toggle")
    assert toggles, "language toggle not found"
    assert toggles[0].value is False  # defaults to English

    toggles[0].set_value(True).run()
    assert not at.exception, f"language toggle failed: {at.exception}"
    search_buttons = [b for b in at.button if b.label == "Buscar"]
    assert search_buttons, "Spanish search button label not shown after toggle"
