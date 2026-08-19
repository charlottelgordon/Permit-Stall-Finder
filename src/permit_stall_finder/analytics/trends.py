"""Pure, Streamlit-free, network-free aggregation for the trends dashboard.

Consumes Agent 1 (PermitJourney) + Agent 2 (StallAssessment) output across
many sampled permits and rolls it up into per-year/per-permit-type summary
statistics. Same rule every other Streamlit-free module in this repo
follows: nothing here is a new analytical judgment -- every duration is a
plain median over an already-DERIVED field (PermitJourney.derived), and
every count is a plain tally of already-assigned StallCategory/Severity
labels (StallAssessment.detections). scripts/generate_trends_artifact.py
is the only caller that runs Agent 1/2 and feeds results in here; this
module never fetches anything itself.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime

from permit_stall_finder.schema.journey import PermitJourney
from permit_stall_finder.schema.stall_detection import StallAssessment


@dataclass(frozen=True)
class YearTypeBucket:
    year: int
    permit_type: str
    n_sampled: int
    """How many permits were sampled into this bucket, before any
    per-permit failure was excluded -- kept alongside n_analyzed for the
    dashboard's own transparency caption (PRD: stall detection must be
    inspectable, not a black box)."""
    n_analyzed: int
    median_days_submitted_to_issuance: float | None
    median_days_issuance_to_first_inspection: float | None
    median_inter_inspection_gap_days: float | None
    stall_category_counts: dict[str, int]
    """Keyed by StallCategory.value."""
    severity_counts: dict[str, int]
    """Keyed by Severity.value."""


@dataclass(frozen=True)
class TrendsArtifact:
    generated_at: datetime
    start_year: int
    end_year: int
    sample_size_per_bucket: int
    cohort_sample_size: int
    permit_types: list[str]
    buckets: list[YearTypeBucket]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def aggregate_bucket(
    year: int,
    permit_type: str,
    n_sampled: int,
    journeys_and_assessments: list[tuple[PermitJourney, StallAssessment]],
) -> YearTypeBucket:
    """One bucket's stats. Each input pair is one already-run Agent 1 +
    Agent 2 result for a permit sampled into this (year, permit_type)
    bucket -- a permit with no derived metrics or no detections simply
    contributes nothing to the corresponding tally, never a zero or an
    estimate standing in for missing data."""
    issuance_days: list[float] = []
    first_inspection_days: list[float] = []
    inter_inspection_days: list[float] = []
    category_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}

    for journey, assessment in journeys_and_assessments:
        derived = journey.derived
        if derived is not None:
            if derived.days_submitted_to_issuance is not None:
                issuance_days.append(float(derived.days_submitted_to_issuance))
            if derived.days_issuance_to_first_inspection is not None:
                first_inspection_days.append(float(derived.days_issuance_to_first_inspection))
            inter_inspection_days.extend(float(d) for d in derived.days_between_inspections)
        for detection in assessment.detections:
            category_counts[detection.category.value] = category_counts.get(detection.category.value, 0) + 1
            severity_counts[detection.severity.value] = severity_counts.get(detection.severity.value, 0) + 1

    return YearTypeBucket(
        year=year,
        permit_type=permit_type,
        n_sampled=n_sampled,
        n_analyzed=len(journeys_and_assessments),
        median_days_submitted_to_issuance=_median(issuance_days),
        median_days_issuance_to_first_inspection=_median(first_inspection_days),
        median_inter_inspection_gap_days=_median(inter_inspection_days),
        stall_category_counts=category_counts,
        severity_counts=severity_counts,
    )


def to_json(artifact: TrendsArtifact) -> str:
    payload = {
        "generated_at": artifact.generated_at.isoformat(),
        "start_year": artifact.start_year,
        "end_year": artifact.end_year,
        "sample_size_per_bucket": artifact.sample_size_per_bucket,
        "cohort_sample_size": artifact.cohort_sample_size,
        "permit_types": artifact.permit_types,
        "buckets": [asdict(b) for b in artifact.buckets],
    }
    return json.dumps(payload, indent=2)


def from_json(raw: str) -> TrendsArtifact:
    payload = json.loads(raw)
    return TrendsArtifact(
        generated_at=datetime.fromisoformat(payload["generated_at"]),
        start_year=payload["start_year"],
        end_year=payload["end_year"],
        sample_size_per_bucket=payload["sample_size_per_bucket"],
        cohort_sample_size=payload["cohort_sample_size"],
        permit_types=payload["permit_types"],
        buckets=[YearTypeBucket(**b) for b in payload["buckets"]],
    )


def save_artifact(artifact: TrendsArtifact, path: str) -> None:
    with open(path, "w") as f:
        f.write(to_json(artifact))


def load_artifact(path: str) -> TrendsArtifact:
    with open(path) as f:
        return from_json(f.read())
