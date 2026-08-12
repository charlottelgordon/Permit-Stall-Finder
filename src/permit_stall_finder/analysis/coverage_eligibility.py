"""NO_INSPECTION_SINCE_ISSUANCE eligibility gate (AGENT2_DESIGN.md §4).

This is a data-coverage rule, not a definition of a stall: it answers
"is a missing inspection record on this permit type interpretable at all,"
never "is this permit stalled." A permit type failing the gate produces a
coverage_gaps entry, not a detection with reduced confidence -- absence of
a reliable coverage measurement is treated as "not currently trusted,"
never as "assume fine."

MIN_INSPECTION_COVERAGE_RATE default (0.60) and the measured rates below
come from the sensitivity analysis in AGENT2_DESIGN.md §4b (forward
permit->inspection match rate per permit_type, DATASET_VALIDATION.md §9b
plus a direct full-population measurement for the three rarest types).
Both are provisional MVP values, explicitly configurable and revisit-
worthy -- not derived from a formal statistical test.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

MIN_INSPECTION_COVERAGE_RATE = 0.60

MEASUREMENT_DATE = datetime(2026, 8, 11, tzinfo=timezone.utc)

# permit_type -> (observed_forward_match_rate, sample_n)
# Source: research/DATASET_VALIDATION.md §9b (9 types, stratified sample,
# n=1,820) + a direct full-population measurement for the 3 rarest types
# (research/AGENT2_DESIGN.md §4b) not covered by that sample.
MEASURED_COVERAGE_RATES: dict[str, tuple[float, int]] = {
    "Swimming-Pool/Spa": (0.921, 114),
    "Nonbldg-Addition": (0.807, 109),
    "Bldg-Demolition": (0.789, 90),
    "Grading": (0.726, 168),
    "Nonbldg-New": (0.719, 89),
    "Bldg-Alter/Repair": (0.711, 879),
    "Bldg-Addition": (0.687, 249),
    "Nonbldg-Demolition": (0.649, 77),
    "Nonbldg-Alter/Repair": (0.632, 19),
    "Sign": (0.618, 55),
    "Bldg-New": (0.503, 157),
    "Bldg-Relocation": (0.333, 9),
}


@dataclass(frozen=True)
class InspectionCoverageEligibility:
    permit_type: str
    observed_forward_match_rate: float | None
    sample_n: int
    eligible: bool
    reason: str
    measured_at: datetime


def assess_eligibility(
    permit_type: str,
    min_coverage_rate: float = MIN_INSPECTION_COVERAGE_RATE,
    measured_rates: dict[str, tuple[float, int]] = MEASURED_COVERAGE_RATES,
    measured_at: datetime = MEASUREMENT_DATE,
) -> InspectionCoverageEligibility:
    measurement = measured_rates.get(permit_type)
    if measurement is None:
        return InspectionCoverageEligibility(
            permit_type=permit_type,
            observed_forward_match_rate=None,
            sample_n=0,
            eligible=False,
            reason=(
                f"No inspection-coverage measurement exists for permit_type "
                f"'{permit_type}'. Unmeasured types default to ineligible "
                "rather than assumed reliable."
            ),
            measured_at=measured_at,
        )
    rate, n = measurement
    eligible = rate >= min_coverage_rate
    reason = (
        f"observed forward inspection-match rate ({rate*100:.1f}%, n={n}) is "
        f"{'at or above' if eligible else 'below'} the configured "
        f"data-coverage threshold ({min_coverage_rate*100:.0f}%)"
    )
    return InspectionCoverageEligibility(
        permit_type=permit_type,
        observed_forward_match_rate=rate,
        sample_n=n,
        eligible=eligible,
        reason=reason,
        measured_at=measured_at,
    )
