"""Central constants. No dataset ID or magic threshold should be hardcoded
elsewhere — see research/DATASET_VALIDATION.md for how these were chosen."""

from __future__ import annotations

PERMIT_DATASET_ID = "gwh9-jnip"
"""Building and Safety - Building Permits Submitted from 2020 to Present (N).
Includes both issued and not-yet-issued permits. See §8e of
research/DATASET_VALIDATION.md."""

INSPECTION_DATASET_ID = "9w5z-rg2h"
"""Building and Safety Inspections."""

SOCRATA_BASE_URL = "https://data.lacity.org/resource"

DEFAULT_DB_PATH = "data/permit_stall_finder.duckdb"

NORMALIZATION_RULE_DESCRIPTION = "strip non-alphanumeric characters, uppercase"

# Permit types with a historically low or highly variable forward
# permit->inspection match rate (research/DATASET_VALIDATION.md §9b,
# n=1,820 stratified sample). A missing inspection match for these types is
# less informative than for others and should not be weighted the same way
# by Agent 2. Empirical, based on one sample — revisit as more data
# accumulates rather than treating as fixed.
INSPECTION_MATCH_UNCERTAIN_PERMIT_TYPES = {"Bldg-New"}

# --- Agent 2 (Stall Detector) ---
# See research/AGENT2_DESIGN.md for the rationale behind every value below.

MIN_FRICTION_COUNT = 2
# "Repeated" is definitionally more than once (§6a) -- below this, a
# friction category is never even assessed, regardless of cohort.

MIN_EXPOSURE_FOR_FRICTION_ASSESSMENT = 3
# Minimum substantive inspection events observed before friction is
# assessed at all (§6c.3) -- too early in a permit's process otherwise,
# regardless of raw count.

FRICTION_EXPOSURE_TIERS = [(1, 5), (6, 15), (16, 30), (31, None)]
# (inclusive_low, inclusive_high_or_None) buckets of
# total_inspection_opportunities used to stratify ONGOING-permit friction
# cohorts (§6c.2). Coarse by design -- exact cut points are a starting
# point, not derived from a distribution-shape analysis.

DEFAULT_COHORT_SAMPLE_SIZE = 200
# Sample size used when bulk-pulling a permit population to build a
# post-issuance (inspection-gap or friction) cohort -- these require
# per-permit inspection-history joins that aren't expressible as a single
# SoQL aggregation, so cohorts are built from a live-pulled sample rather
# than the full population. Pre-issuance dwell cohorts don't need this --
# SoQL can aggregate status_date directly across the full population.
