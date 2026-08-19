"""Offline batch job that builds the static artifact
app/sections/trends_dashboard.py reads at runtime. NEVER run by the
deployed app itself -- Streamlit Community Cloud has no persistent job
scheduler and no filesystem guarantee across redeploys, so a live
"nightly cache refresh" inside the app isn't possible. Refreshing the
dashboard means: re-run this script, review the artifact diff, commit,
push.

    python scripts/generate_trends_artifact.py --start-year 2023 --end-year 2024 \
        --sample-size 150 --out app/assets/trends_artifact.json

Cost/precision tradeoff: assess_stalls() internally re-fetches its own
comparison cohort (up to --cohort-sample-size permits) for every category
it evaluates, per permit -- the dominant cost of this script, not the
target-permit fetches themselves. --cohort-sample-size therefore defaults
much lower than the live app's config.DEFAULT_COHORT_SAMPLE_SIZE (200) to
keep a multi-year, multi-type run tractable. This narrows precision only
in the artifact's severity_counts breakdown, never its duration medians,
which read straight off each permit's own already-computed DerivedMetrics
and don't depend on cohort size at all.

Sampling is a convenience sample (first N matching rows per SoQL query),
not randomized -- the same limitation cohort_populations.py's live cohort
sampling already carries, not a new gap introduced here.

Uses an in-memory DuckDB connection throughout, so this script never
touches the gitignored data/ DuckDB file the deployed app uses.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from permit_stall_finder import config
from permit_stall_finder.agents.journey_reconstructor import reconstruct_journey
from permit_stall_finder.agents.stall_detector import assess_stalls
from permit_stall_finder.analytics.trends import TrendsArtifact, aggregate_bucket, save_artifact
from permit_stall_finder.ingestion import socrata
from permit_stall_finder.storage.db import connect


def _sample_permit_numbers(year: int, permit_type: str, sample_size: int) -> list[str]:
    where = (
        f"submitted_date >= '{year}-01-01T00:00:00' "
        f"AND submitted_date < '{year + 1}-01-01T00:00:00' "
        f"AND permit_type='{socrata.escape_soql_string(permit_type)}'"
    )
    rows = socrata.query(
        config.PERMIT_DATASET_ID,
        {"$select": "permit_nbr", "$where": where, "$limit": str(sample_size)},
        config.SOCRATA_BASE_URL,
    )
    return [r["permit_nbr"] for r in rows if r.get("permit_nbr")]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True, help="inclusive")
    parser.add_argument(
        "--sample-size", type=int, default=config.TRENDS_DEFAULT_SAMPLE_SIZE_PER_BUCKET,
        help="permits sampled per (year, permit_type) bucket",
    )
    parser.add_argument(
        "--cohort-sample-size", type=int, default=config.TRENDS_DEFAULT_COHORT_SAMPLE_SIZE,
    )
    parser.add_argument("--permit-types", nargs="+", default=config.TRENDS_DEFAULT_PERMIT_TYPES)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    conn = connect(":memory:")
    buckets = []

    for year in range(args.start_year, args.end_year + 1):
        for permit_type in args.permit_types:
            permit_numbers = _sample_permit_numbers(year, permit_type, args.sample_size)
            results = []
            failures = 0
            for permit_number in permit_numbers:
                try:
                    journey = reconstruct_journey(conn, permit_number)
                    assessment = assess_stalls(journey, sample_size=args.cohort_sample_size)
                    results.append((journey, assessment))
                except Exception as exc:  # batch job: isolate one bad permit, keep going
                    failures += 1
                    print(f"  ! {permit_number}: {exc}", file=sys.stderr)
            bucket = aggregate_bucket(year, permit_type, len(permit_numbers), results)
            buckets.append(bucket)
            print(
                f"{year} {permit_type}: sampled {len(permit_numbers)}, "
                f"analyzed {bucket.n_analyzed}, failed {failures}",
                file=sys.stderr,
            )

    artifact = TrendsArtifact(
        generated_at=datetime.now(timezone.utc),
        start_year=args.start_year,
        end_year=args.end_year,
        sample_size_per_bucket=args.sample_size,
        cohort_sample_size=args.cohort_sample_size,
        permit_types=args.permit_types,
        buckets=buckets,
    )
    save_artifact(artifact, args.out)
    print(f"Wrote {len(buckets)} buckets to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
