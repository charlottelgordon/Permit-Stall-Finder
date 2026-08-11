"""Audit-trail persistence for computed cohort statistics. Not on the hot
path of a single permit assessment (Agent 2 builds cohorts live from the
source datasets, per AGENT2_DESIGN.md, since the underlying populations
change as new permits/inspections are recorded) -- this table exists so a
computed cohort can be inspected/audited after the fact rather than only
existing transiently in memory during one CLI run."""

from __future__ import annotations

import json

import duckdb

from permit_stall_finder.schema.stall_detection import CohortDefinition


def cohort_key(category: str, dimensions: dict[str, str]) -> str:
    parts = [category] + [f"{k}={v}" for k, v in sorted(dimensions.items())]
    return "|".join(parts)


def persist_cohort(conn: duckdb.DuckDBPyConnection, category: str, cohort: CohortDefinition) -> None:
    conn.execute(
        """
        INSERT INTO cohort_stats (
            cohort_key, computed_at, category, dimensions_json, specificity_level,
            source, benchmark_semantics, n, confidence,
            median_days_or_count, p75_days_or_count, p90_days_or_count, p95_days_or_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (cohort_key, computed_at) DO NOTHING
        """,
        [
            cohort_key(category, cohort.dimensions),
            cohort.computed_at,
            category,
            json.dumps(cohort.dimensions),
            cohort.specificity_level,
            cohort.source.value,
            cohort.benchmark_semantics.value,
            cohort.n,
            cohort.confidence.value,
            cohort.median_days_or_count,
            cohort.p75_days_or_count,
            cohort.p90_days_or_count,
            cohort.p95_days_or_count,
        ],
    )


def read_latest_cohort(
    conn: duckdb.DuckDBPyConnection, category: str, dimensions: dict[str, str]
) -> dict | None:
    key = cohort_key(category, dimensions)
    row = conn.execute(
        """
        SELECT computed_at, n, confidence, median_days_or_count, p75_days_or_count,
               p90_days_or_count, p95_days_or_count
        FROM cohort_stats
        WHERE cohort_key = ?
        ORDER BY computed_at DESC
        LIMIT 1
        """,
        [key],
    ).fetchone()
    if row is None:
        return None
    return {
        "computed_at": row[0],
        "n": row[1],
        "confidence": row[2],
        "median_days_or_count": row[3],
        "p75_days_or_count": row[4],
        "p90_days_or_count": row[5],
        "p95_days_or_count": row[6],
    }
