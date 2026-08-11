"""Offline test fixtures: loads captured raw Socrata JSON from
tests/fixtures/ instead of hitting the network. Each fixture pair
(<name>_permit.json, <name>_inspections.json) was captured from a real,
verified permit — see research/DATASET_VALIDATION.md §9 for how the five
permits were selected."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from permit_stall_finder.storage.db import DDL

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture_fetchers(name: str):
    with open(FIXTURES_DIR / f"{name}_permit.json") as f:
        raw_permit = json.load(f)
    with open(FIXTURES_DIR / f"{name}_inspections.json") as f:
        raw_inspections = json.load(f)

    def fetch_permit_row(permit_number: str):
        return raw_permit

    def fetch_inspection_rows(permit_number: str):
        return raw_inspections

    return fetch_permit_row, fetch_inspection_rows


@pytest.fixture
def conn():
    """Fresh in-memory DuckDB per test — no shared state, no disk I/O."""
    c = duckdb.connect(":memory:")
    c.execute(DDL)
    yield c
    c.close()
