"""python -m permit_stall_finder.cli journey <permit_number>
python -m permit_stall_finder.cli stalls <permit_number>
python -m permit_stall_finder.cli explain <permit_number>"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from permit_stall_finder import config
from permit_stall_finder.agents.developer_explainer import explain_assessment
from permit_stall_finder.agents.journey_reconstructor import reconstruct_journey
from permit_stall_finder.agents.stall_detector import assess_stalls
from permit_stall_finder.storage.db import connect


def _json_default(obj):
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "value") and hasattr(obj, "name"):  # Enum
        return obj.value
    return str(obj)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="permit_stall_finder")
    sub = parser.add_subparsers(dest="command", required=True)

    journey_parser = sub.add_parser("journey", help="Reconstruct a permit's journey (Agent 1)")
    journey_parser.add_argument("permit_number")
    journey_parser.add_argument(
        "--db", default=None, help=f"DuckDB path (default: {config.DEFAULT_DB_PATH})"
    )

    stalls_parser = sub.add_parser("stalls", help="Reconstruct a journey and assess stalls (Agent 1 + 2)")
    stalls_parser.add_argument("permit_number")
    stalls_parser.add_argument(
        "--db", default=None, help=f"DuckDB path (default: {config.DEFAULT_DB_PATH})"
    )
    stalls_parser.add_argument(
        "--sample-size", type=int, default=config.DEFAULT_COHORT_SAMPLE_SIZE,
        help="Sample size for post-issuance cohort population fetches",
    )

    explain_parser = sub.add_parser("explain", help="Full pipeline: journey + stalls + explanations (Agent 1 + 2 + 3)")
    explain_parser.add_argument("permit_number")
    explain_parser.add_argument(
        "--db", default=None, help=f"DuckDB path (default: {config.DEFAULT_DB_PATH})"
    )
    explain_parser.add_argument(
        "--sample-size", type=int, default=config.DEFAULT_COHORT_SAMPLE_SIZE,
        help="Sample size for post-issuance cohort population fetches",
    )

    args = parser.parse_args(argv)

    if args.command == "journey":
        conn = connect(args.db or config.DEFAULT_DB_PATH)
        journey = reconstruct_journey(conn, args.permit_number)
        print(json.dumps(asdict(journey), default=_json_default, indent=2))

    elif args.command == "stalls":
        conn = connect(args.db or config.DEFAULT_DB_PATH)
        journey = reconstruct_journey(conn, args.permit_number)
        assessment = assess_stalls(journey, sample_size=args.sample_size)
        print(json.dumps(asdict(assessment), default=_json_default, indent=2))

    elif args.command == "explain":
        conn = connect(args.db or config.DEFAULT_DB_PATH)
        journey = reconstruct_journey(conn, args.permit_number)
        assessment = assess_stalls(journey, sample_size=args.sample_size)
        explanation_set = explain_assessment(assessment)
        print(json.dumps(asdict(explanation_set), default=_json_default, indent=2))


if __name__ == "__main__":
    main()
