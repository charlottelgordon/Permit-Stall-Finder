"""DuckDB connection and schema. permit_snapshots is append-only by design
(see schema/journey.py PermitSnapshot docstring) — repeated identical
snapshots are kept, not deduplicated away, because their repetition is what
lets schema/transitions.py later confirm a status persisted."""

from __future__ import annotations

import os

import duckdb

from permit_stall_finder import config

DDL = """
CREATE TABLE IF NOT EXISTS permit_snapshots (
    permit_number TEXT NOT NULL,
    observed_at TIMESTAMP NOT NULL,
    source_dataset_id TEXT NOT NULL,
    source_record_id TEXT,
    source_updated_at TIMESTAMP,
    source_refresh_time DATE,
    permit_type TEXT,
    permit_sub_type TEXT,
    business_unit TEXT,
    work_description TEXT,
    submitted_date DATE,
    status_desc TEXT,
    status_date DATE,
    issue_date DATE,
    cofo_date DATE,
    valuation DOUBLE,
    raw_json TEXT,
    PRIMARY KEY (permit_number, observed_at)
);

CREATE TABLE IF NOT EXISTS inspection_events (
    event_id TEXT PRIMARY KEY,
    permit_number TEXT NOT NULL,
    source_dataset_id TEXT NOT NULL,
    source_record_id TEXT,
    source_updated_at TIMESTAMP,
    observed_at TIMESTAMP NOT NULL,
    inspection_date DATE,
    inspection_type TEXT,
    inspection_result TEXT,
    raw_json TEXT
);

CREATE TABLE IF NOT EXISTS reconstruction_log (
    permit_number TEXT,
    observed_at TIMESTAMP NOT NULL,
    issue_type TEXT NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS cohort_stats (
    cohort_key TEXT NOT NULL,       -- category + sorted dimensions, e.g. "pre_issuance_status_dwell|permit_type=Bldg-Alter/Repair|status_desc=Corrections Issued"
    computed_at TIMESTAMP NOT NULL,
    category TEXT NOT NULL,
    dimensions_json TEXT NOT NULL,
    specificity_level INTEGER NOT NULL,
    source TEXT NOT NULL,
    benchmark_semantics TEXT NOT NULL,
    n INTEGER NOT NULL,
    confidence TEXT NOT NULL,
    median_days_or_count DOUBLE,
    p75_days_or_count DOUBLE,
    p90_days_or_count DOUBLE,
    p95_days_or_count DOUBLE,
    PRIMARY KEY (cohort_key, computed_at)
);
"""


def connect(db_path: str = config.DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    if db_path != ":memory:":
        directory = os.path.dirname(db_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
    conn = duckdb.connect(db_path)
    conn.execute(DDL)
    return conn
