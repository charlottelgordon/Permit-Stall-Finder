# Agent 2 — Stall Detector: Design

Status: **design only, not approved for implementation.** No Agent 2 code
exists. Revision 2 — incorporates 8 refinements requested after the first
review. Grounded in Agent 1's actual `PermitJourney` contract
(`src/permit_stall_finder/schema/journey.py`) and in live queries against
the real data (exact counts cited throughout), not assumption.

---

## 1. Proposed stall taxonomy

Two orthogonal axes: **class** (delay vs. friction) and **applicability**
(pre-issuance vs. post-issuance). A permit can have detections in multiple
categories simultaneously — they are never merged into one score.

### Axis 1 — stall class

- **DELAY** — elapsed-time based, percentile-ranked against a cohort.
- **FRICTION** — count/frequency based, percentile-ranked against a
  cohort, and gated by an explicit minimum raw count (refinement #6, §4c).

### Axis 2 — categories

**A. Pre-issuance** (`match_status == UNISSUED`)

| Category | Signal |
|---|---|
| `PRE_ISSUANCE_STATUS_DWELL` | Time in current `status_desc` (`status_date` → now), benchmarked per status |

One category parameterized by the literal `status_desc` string, not a
hardcoded enum per status — see §2a for why. Statuses with enough volume to
cohort meaningfully on their own (full unissued population, n=74,204,
`DATASET_VALIDATION.md` §9c): `Corrections Issued` (14,356), `Verifications
in Progress` (16,566), `Quality Review Completed` (18,662), `PC Info
Complete` (12,780), `PC Approved` (7,575), `Ready to Issue` (1,076), `PC in
Progress` (232), `Not Ready to Issue` (192), `Plans on Hold` (202),
`Submitted` (465).

**B. Post-issuance** (`ISSUED_WITH_INSPECTIONS` or `ISSUED_NO_INSPECTIONS_FOUND`)

| Category | Signal | interval_state |
|---|---|---|
| `ISSUANCE_TO_FIRST_INSPECTION_GAP` | `issue_date` → first substantive inspection | COMPLETED (once a first inspection exists) |
| `NO_INSPECTION_SINCE_ISSUANCE` | Days since issuance, zero inspections — gated (§4) | ONGOING |
| `INTER_INSPECTION_GAP` | Gap between two consecutive substantive inspections | COMPLETED |
| `INACTIVITY_SINCE_LAST_INSPECTION` | Gap from most recent substantive event to now, permit not yet terminal | ONGOING |
| `FINALIZATION_GAP` | Last substantive passing inspection → the permit's actual terminal outcome, permit-type aware (§7) | COMPLETED (only computed once terminal) |
| `REPEATED_CORRECTIONS` | Count of CORRECTIONS-family outcomes, min-count gated | n/a (FRICTION) |
| `REPEATED_NOT_READY_OUTCOMES` | Count of NOT_READY-family outcomes, min-count gated | n/a (FRICTION) |
| `REPEATED_CANCELLATIONS` | Count of CANCELLED-family outcomes, min-count gated | n/a (FRICTION) |

`CORRECTIONS_TO_REINSPECTION_GAP` is a same-`inspection_type` (or same-
stage, via the mapping in §5) special case of `INTER_INSPECTION_GAP`, not
its own category.

---

## 2. Benchmark / cohort methodology

### 2a. Cohort dimensions actually available

| Field | Usable? | Notes |
|---|---|---|
| `permit_type` | Yes — primary | 12 values; empirically confirmed to matter (§9b match-rate spread) |
| `permit_sub_type` | Marginal | Optional deeper tier only, fragments cohorts fast |
| `work_description` | **Not usable** | Free text, no categorization exists; excluded from MVP |
| submitted/issue year, bucketed | Yes, secondary | Coarse buckets only (e.g. 2020–21 / 2022–23 / 2024–26) |
| `status_desc` (pre-issuance) / `inspection_type` or mapped stage (post-issuance) | Yes — primary | Strongest single driver of "what's normal" |
| `business_unit` | Untested, promising | Flagged for the validation pass (§8), not assumed |

### 2b. Two cohort *sources* — and now two distinct benchmark semantics (refinement #2)

**`CohortSource`** (mechanical provenance — which pool the numbers came
from):

```
CROSS_SECTIONAL_CURRENT_SNAPSHOT   # pre-issuance, bulk-pulled from currently-unissued gwh9-jnip rows
COMPLETED_TRANSITIONS_OWN_HISTORY  # future: Agent 1's own accumulated polling history
SOURCE_EVENT_LOG                   # 9w5z-rg2h inspection events — a genuine historical log, available today
```

**`BenchmarkSemantics`** (the statistical interpretation category — exactly
two values, drives which sentence template is legal downstream):

```
ACTIVE_PEER_DWELL    # cohort = other permits currently in the same ongoing state (length-biased)
COMPLETED_INTERVAL    # cohort = intervals that have already concluded (unbiased duration distribution)
```

Mapping: `CROSS_SECTIONAL_CURRENT_SNAPSHOT` → `ACTIVE_PEER_DWELL`.
`COMPLETED_TRANSITIONS_OWN_HISTORY` and `SOURCE_EVENT_LOG` → `COMPLETED_
INTERVAL` (both represent cohorts built from intervals with a known start
*and* end).

**Why this split matters, concretely**: `9w5z-rg2h` is a real event log, so
inspection-gap cohorts are `COMPLETED_INTERVAL` and statistically sound
today. Pre-issuance dwell cohorts have no accumulated polling history yet,
so the only available cohort is "other permits currently stuck in the same
status right now" — `ACTIVE_PEER_DWELL`, and it is **length-biased**: a
permit that clears `Corrections Issued` in 3 days is far less likely to be
*caught* sitting there by any snapshot than one that sits for 200 days, so
the cohort systematically overrepresents slow permits.

**Mandatory language gate (refinement #2)**: when `benchmark_semantics ==
ACTIVE_PEER_DWELL`, the only legal sentence form is:

> "This permit has remained in the currently published status longer than
> X% of currently observed comparable permits."

It is **never** translated into "permits normally take N days to clear
this stage" — that would be a `COMPLETED_INTERVAL`-only claim this cohort
cannot support. This is enforced structurally: the sentence-template
function takes `benchmark_semantics` as a required argument and has no
code path that produces the "normally take" phrasing for
`ACTIVE_PEER_DWELL`. `COMPLETED_INTERVAL` benchmarks (all post-issuance
gap categories) may use the "typically take N days" framing, since that
cohort's intervals actually concluded.

### 2c. `interval_state` — completed vs. ongoing (refinement #3)

Independent of `benchmark_semantics` (which describes the *cohort*),
`interval_state` describes *this specific permit's* measurement:

```
COMPLETED   # both endpoints of this permit's interval are observed facts
ONGOING     # the "end" is just "as of now" — the true endpoint is unknown
```

| Category | interval_state |
|---|---|
| `PRE_ISSUANCE_STATUS_DWELL` | always `ONGOING` (issuance hasn't happened yet) |
| `ISSUANCE_TO_FIRST_INSPECTION_GAP` | `COMPLETED` (only computed once a first inspection exists) |
| `NO_INSPECTION_SINCE_ISSUANCE` | always `ONGOING` |
| `INTER_INSPECTION_GAP` | always `COMPLETED` (both inspection events already happened) |
| `INACTIVITY_SINCE_LAST_INSPECTION` | always `ONGOING` |
| `FINALIZATION_GAP` | always `COMPLETED` (only computed once terminal) |

**Rule**: whenever `interval_state == ONGOING`, the detection's `caveats`
must include a statement that the interval has not closed and its eventual
total duration is not known — `elapsed_days` reflects time-so-far only. No
sentence in Agent 2's output may imply an ongoing interval's final length.

One more asymmetry worth naming: `INACTIVITY_SINCE_LAST_INSPECTION` is
`ONGOING` but its cohort (`INTER_INSPECTION_GAP` history) is built from
`COMPLETED` intervals — comparing a still-growing wait against a
distribution of gaps that *did* eventually close. This is a milder,
different bias than the pre-issuance one (closer to statistical
right-censoring than length-bias) and gets its own caveat, distinct from
the `ACTIVE_PEER_DWELL` one.

### 2c-1. Structural gate on continuity language (refinement #2, hardened)

The first review already forbade translating `ACTIVE_PEER_DWELL` into
"permits normally take N days" language. This revision goes further: even
the *weaker*, licensed form of the claim — "this permit has remained in
this status for N days" — must not silently imply **continuous, unbroken
residence** unless repeated snapshot observation actually confirms it.
Agent 1's `schema/transitions.py::ObservedTransition.
confirmed_by_repeated_observation` already exists for exactly this
reason; Agent 2 must not restate a weaker fact more strongly than Agent 1
already licensed it.

Two things make this structural rather than a matter of careful prose:

**1. A required boolean field, not just a caveat string.**
`DelayStallDetection` carries
`status_persistence_confirmed_by_repeated_observation: bool` (mirrored
directly from the `ObservedTransition` that produced this detection).
Caveats are free text and can be dropped or summarized away by a careless
downstream consumer; a typed boolean field cannot be silently lost the same
way, and Agent 3 (when built) is contractually required to branch on it
rather than infer continuity from the mere presence of an elapsed-days
number.

**2. A single canonical sentence-renderer, so no one hand-writes this
prose twice.**

```python
def render_dwell_statement(detection: DelayStallDetection) -> str:
    """The sanctioned way to turn a PRE_ISSUANCE_STATUS_DWELL (or any
    ACTIVE_PEER_DWELL) detection into a sentence. There is no code path
    here that can produce continuity language ("has continuously
    remained") unless status_persistence_confirmed_by_repeated_observation
    is True — and even then, the phrasing stays close to what was actually
    observed (matching ObservedTransition.describe()'s existing wording in
    Agent 1) rather than reaching for a stronger claim."""
    base = (
        f"{detection.elapsed_days} days have elapsed since the published "
        f"'{detection.stage_label}' status_date."
    )
    if (
        detection.cohort.benchmark_semantics == BenchmarkSemantics.ACTIVE_PEER_DWELL
        and detection.percentile_rank is not None
    ):
        base += (
            f" This elapsed time is longer than {detection.percentile_rank:.0f}% "
            "of currently observed comparable permits with the same "
            "published status."
        )
    if detection.status_persistence_confirmed_by_repeated_observation:
        base += " This status has been confirmed present across repeated observation."
    return base
```

This produces exactly the two example sentences from your instructions
("261 days have elapsed since the published PC Approved status_date" / "...
longer than X% of currently observed comparable permits with the same
published status") and has no branch that can produce "has continuously
remained in PC Approved for 261 days" unless the confirmation flag is
actually `True` — and even then, the wording stays at "confirmed present
across repeated observation," consistent with Agent 1's existing, more
careful phrasing rather than escalating to "continuously remained."

### 2d. Fallback ladder (unchanged from rev. 1, still constraint #5)

**Pre-issuance**: `permit_type × status_desc × year-bucket` → `permit_type
× status_desc` → `status_desc` only → floor (no percentile).
**Post-issuance**: `permit_type × stage × year-bucket` → `permit_type ×
stage` → `stage` only → floor. ("stage" = the mapped grouping from §5 when
exact `inspection_type` is too sparse, falling back further to exact
`inspection_type` first before the mapped stage — precision preferred when
available.)
**Friction**: `permit_type × year-bucket` → `permit_type` → floor.

### 2e. Minimum cohort sizes (unchanged)

n ≥ 30 → `FULL`. 10 ≤ n < 30 → `REDUCED` (caveat attached). n < 10 even at
the floor tier → no percentile computed at all; recorded in `StallAssessment.
coverage_gaps` instead of fabricating a number. Confirmed empirically
achievable at tier 1–2 for common type/status pairs, and correctly
degrading for the rare tail (`Bldg-Relocation`, `Nonbldg-Addition`) — see
§8.

---

## 3. Severity model (refinement #1 — replaces rev. 1's P50/75/90 bands)

The median is **contextual information only** — carried in `CohortDefinition`
for reference — and is **not** a detection threshold. Default bands:

| percentile_rank | Severity |
|---|---|
| < 75 | *(no detection emitted)* |
| [75, 90) | `WATCH` |
| [90, 95) | `ELEVATED` |
| ≥ 95 | `SEVERE` |
| *(cohort `INSUFFICIENT`)* | `UNSCORED` — no percentile, no detection; goes to `coverage_gaps` |

Configurable via a `SeverityThresholds` object (`watch=75.0, elevated=90.0,
severe=95.0`) with these values as MVP defaults — not hardcoded literals
scattered through the detection logic.

```python
@dataclass(frozen=True)
class SeverityThresholds:
    watch: float = 75.0
    elevated: float = 90.0
    severe: float = 95.0

def classify_severity(percentile_rank: float | None, thresholds: SeverityThresholds) -> Severity:
    if percentile_rank is None:
        return Severity.UNSCORED
    if percentile_rank >= thresholds.severe:
        return Severity.SEVERE
    if percentile_rank >= thresholds.elevated:
        return Severity.ELEVATED
    if percentile_rank >= thresholds.watch:
        return Severity.WATCH
    return None  # below watch threshold -> no detection at all
```

A permit sitting exactly at its cohort's median (50th percentile) is
**not** flagged — that was true in rev. 1 and remains true, just with a
much higher bar (75th, not 50th) before anything gets surfaced at all. This
directly addresses "do not classify everything above the median as a
stall."

---

## 4. No-inspection eligibility gate (refinement #4)

`NO_INSPECTION_SINCE_ISSUANCE` is the single riskiest signal in this
design — absence of a record is easy to misread as absence of activity.
Rev. 1 gated it on Agent 1's `INSPECTION_MATCH_UNCERTAIN_FOR_TYPE` flag
(a single hardcoded permit type). This revision formalizes it as its own
assessed eligibility check, not a flag lookup.

### 4a. `InspectionCoverageEligibility`

```python
@dataclass(frozen=True)
class InspectionCoverageEligibility:
    permit_type: str
    observed_forward_match_rate: float | None  # None = not yet measured
    sample_n: int
    eligible: bool
    reason: str
    measured_at: datetime  # freshness of this coverage measurement
```

**Rule**: `eligible = observed_forward_match_rate is not None and
observed_forward_match_rate >= MIN_INSPECTION_COVERAGE_RATE` (MVP default
`0.60`, see sensitivity analysis below). **An unmeasured type defaults to
`eligible=False`** — absence of a coverage measurement is treated as
"unknown, therefore not trusted," never as "assume fine."

**This is a data-coverage rule, not a definition of a stall.** It answers
"is a missing inspection record on this permit type interpretable at all,"
not "is this permit stalled." A permit type failing the gate produces zero
information either way about whether any given permit of that type is
progressing normally — it produces a `coverage_gaps` entry saying the
question can't currently be answered.

### 4b. Sensitivity analysis — 0.50 / 0.60 / 0.70 / 0.80

Measured forward permit→inspection match rate per `permit_type`. Nine
types from the validated stratified sample (`DATASET_VALIDATION.md` §9b,
n=1,820); the three rarest types weren't in that sample and were measured
directly against their full issued population for this analysis (small n,
noted):

| permit_type | rate | sample n | source |
|---|---|---|---|
| Swimming-Pool/Spa | 92.1% | 114 | §9b stratified sample |
| Nonbldg-Addition | 80.7% | 109 | full population (this analysis) |
| Bldg-Demolition | 78.9% | 90 | §9b stratified sample |
| Grading | 72.6% | 168 | §9b stratified sample |
| Nonbldg-New | 71.9% | 89 | §9b stratified sample |
| Bldg-Alter/Repair | 71.1% | 879 | §9b stratified sample (highest-volume permit type overall) |
| Bldg-Addition | 68.7% | 249 | §9b stratified sample |
| Nonbldg-Demolition | 64.9% | 77 | full population (this analysis) |
| Nonbldg-Alter/Repair | 63.2% | 19 | §9b stratified sample |
| Sign | 61.8% | 55 | §9b stratified sample |
| Bldg-New | 50.3% | 157 | §9b stratified sample |
| Bldg-Relocation | 33.3% | 9 | full population (this analysis) — n=9, low confidence |

Eligible set at each candidate threshold:

| Threshold | Eligible (n types) | Ineligible |
|---|---|---|
| **0.50** | 11 of 12 | Bldg-Relocation only |
| **0.60** | 10 of 12 | Bldg-New, Bldg-Relocation |
| **0.70** | 6 of 12 | Bldg-Addition, Nonbldg-Demolition, Nonbldg-Alter/Repair, Sign, Bldg-New, Bldg-Relocation |
| **0.80** | 2 of 12 | everything except Swimming-Pool/Spa, Nonbldg-Addition |

**Trade-off analysis:**

- **0.50** lets through everything except the n=9 `Bldg-Relocation` sample —
  including `Bldg-New` at 50.3%, i.e. a coin-flip. That's too weak an
  evidentiary bar for a signal whose whole purpose is distinguishing "data
  gap" from "meaningful absence." Rejected: not permissive enough
  protection against false interpretation.
- **0.60** excludes exactly the two types whose rates are close to or below
  a coin flip (`Bldg-New` 50.3%, `Bldg-Relocation` 33.3%/n=9), while
  keeping all ten other types eligible — including every high-volume type
  (`Bldg-Alter/Repair`, the single largest permit type by volume, at
  71.1%). Coverage stays broad and practically useful.
- **0.70** cuts the eligible set to half the types, excluding several that
  aren't obviously unreliable (`Sign` 61.8%, `Bldg-Addition` 68.7%,
  `Nonbldg-Alter/Repair` 63.2%) for a marginal gain over 0.60 — none of
  those three are meaningfully closer to "coin flip" territory than they
  are to the types that stay eligible. It also puts `Bldg-Alter/Repair`
  (71.1%, the dominant permit type by volume) right at the boundary,
  meaning ordinary sampling noise in a future remeasurement could flip
  eligibility for the majority of all permits in the system. Rejected:
  costs a lot of coverage for limited additional protection, and
  destabilizes the most common type.
- **0.80** leaves only 2 of 12 types eligible, discarding this signal for
  nearly the entire permit population including `Bldg-Demolition` (78.9%)
  and `Bldg-Alter/Repair` (71.1%). Rejected: makes the signal practically
  unusable.

**Recommended MVP default: 0.60.** This is the threshold where the
eligible/ineligible split tracks a real qualitative gap in the data (types
near a coin flip vs. types that aren't) rather than an arbitrary cut
through the middle of a continuum — moving the line to 0.70 or 0.80 starts
cutting through types with no clear reason to treat them differently from
their nearest eligible neighbor. Still explicitly a provisional,
configurable MVP default, not a statistically derived optimum — there was
no formal statistical test performed to select it, and it should be
revisited as more data accumulates (particularly for `Bldg-Relocation`,
whose n=9 measurement carries very wide uncertainty even though its point
estimate is far enough below any candidate threshold that the qualitative
conclusion — ineligible — is unlikely to flip).

### 4c. Behavior when ineligible

No `NO_INSPECTION_SINCE_ISSUANCE` detection is produced. Instead, Agent 2
emits a `coverage_gaps` entry: `"NO_INSPECTION_SINCE_ISSUANCE not assessed
for Bldg-New: observed forward inspection-match rate (50.3%, n=157) is
below the configured data-coverage threshold (60%) — absence of an
inspection record is not currently interpretable as evidence for this
permit type."` This is visible in aggregate monitoring without asserting
anything about the individual permit, and the wording deliberately frames
this as a data-coverage limitation, not a stall judgment.

---

## 5. Inspection vocabulary normalization (refinement #5)

**Raw values are always preserved** — `InspectionEvent.inspection_type`
and `.inspection_result` (Agent 1's schema) are never overwritten or
coerced. The mappings below are additive lookup tables Agent 2 logic
consults; an unmapped raw value stays visible as `UNKNOWN`/`UNMAPPED`
rather than being silently absorbed into an unrelated bucket.

### 5a. `inspection_result` → result family

Pulled the complete vocabulary (all 58 non-null values, full 11.6M-row
`9w5z-rg2h`) rather than working from the partial sample rev. 1 used. Nine
families (`SCHEDULED` added beyond your minimum list — it's the 3rd-most-
common value overall, 1.37M rows, and semantically distinct from
`NOT_READY`: nothing has happened yet vs. something happened and wasn't
ready):

| Family | Meaning | Example values |
|---|---|---|
| `APPROVED` | Genuine passing outcome | Approved, SGSOV Approved, Conditional Approval, Event Approved |
| `CORRECTIONS` | Defect found, fix required | Corrections Issued, Violation Observed, NOV Issued, Event Denied |
| `NOT_READY` | Inspector visited, site not ready | Not Ready for Inspection, No Access for Inspection, SGSOV Not Ready |
| `SCHEDULED` | Booked, not yet occurred | Insp Scheduled |
| `CANCELLED` | Did not occur / voided | Insp Cancelled, Cancelled, Permit Withdrawn, *-Status Void variants |
| `PARTIAL` | Incomplete inspection | Partial Approval, Partial Inspection |
| `FINAL` | Administrative close/certificate record | Permit Finaled, CofO Issued, OK for CofO, Completed, Permit Expired, Permit Closed |
| `OTHER` | Fee/admin/niche | Off-Hour Fees Due, SGSOV Gas Company, OTC Issued |
| `UNKNOWN` | Null/blank result | (481,450 rows, 4.1% of all inspection rows) |

Full machine-readable mapping (all 58 values + counts): `research/
inspection_result_family_mapping.json`. Coverage: **95.9%** of all rows
mapped to a named family; the remaining 4.1% is exactly the null/blank
rows, correctly routed to `UNKNOWN` rather than guessed.

**`SUBSTANTIVE` set for gap/friction logic** = `{APPROVED, CORRECTIONS,
NOT_READY, PARTIAL}` — an actual site visit with a real outcome. `SCHEDULED`
(hasn't happened), `CANCELLED` (didn't happen), `FINAL` (administrative,
not a site inspection), `OTHER`, `UNKNOWN` are excluded from gap
calculations — this is the formalization of what rev. 1 called
"substantive" informally in edge case 5.

### 5b. `inspection_type` → construction stage (184 distinct values)

Pulled the complete list (185 rows incl. blank) rather than the top-25
sample used in rev. 1. Proposed grouping into 13 stages based on naming
patterns — **this is a structural proposal from label text, not verified
against LADBS process documentation**, and should be treated as lower-
confidence than the result-family mapping above until reviewed by someone
with domain knowledge of the actual inspection sequence:

`PRE_CONSTRUCTION_SITE_PREP`, `FOUNDATION_EARTHWORK`, `STRUCTURAL_FRAME`,
`UNDERGROUND_UTILITIES`, `TRADE_ROUGH_IN`, `INTERIOR_CLOSE_IN`,
`LIFE_SAFETY_FIRE`, `FINAL_TRADE_SIGNOFF`, `METHANE_SPECIALTY`,
`VERIFICATION_ADMIN`, `FINAL_CLOSEOUT_CERTIFICATE`,
`COMPLIANCE_ENFORCEMENT`, `PERMIT_LIFECYCLE_ADMIN`.

**175 of 185 types mapped, covering 88.6% of all inspection rows.** Ten
types deliberately left `UNMAPPED` rather than force-fit, in descending
volume order: `(blank)` (481K), `Inspection` (348K — too generic a label to
assign confidently), `SGSOV-Seismic Gas S/O Valve` (298K — a standalone
compliance check whose position in a build sequence isn't inferable from
the label), `Deputy Drilled-In Anchors` (113K), `Public Counter` (70K — not
clearly a physical inspection at all), `Grounding or Bonding` (18K), `Pool/
Spa Cover` (1,855), `Plan Check` (37), `Deputy Inspection` (3),
`Application Submittal` (1). Full mapping + every raw value:
`research/inspection_type_stage_mapping.json`.

**Usage in Agent 2**: exact `inspection_type` string match is the
*preferred* pairing key for `CORRECTIONS_TO_REINSPECTION_GAP` (matching a
`Corrections Issued` on `Sewer` to the next `Sewer` result); the mapped
stage is a documented *fallback* when the exact type differs but likely
refers to the same construction step (e.g. a correction logged under
`Rough-Plumbing` resolved by a follow-up logged as `PLUMBING-Rough`).
Evidence must record which matching method was used (§8) — the fallback
should never be silently indistinguishable from an exact match, since it's
a real interpretive step with more uncertainty.

### 5c. Mapping versioning (refinement #4)

Both mapping files now carry a `metadata` block, not just the raw
value→category tables:

```json
{
  "metadata": {
    "source_dataset_id": "9w5z-rg2h",
    "source_field": "inspection_result",
    "vocabulary_extraction_date": "2026-08-11",
    "mapping_version": "1.0.0",
    "notes": "..."
  },
  "family_of": { "Approved": "APPROVED", "...": "..." },
  "unmapped_at_extraction": ["(blank)"],
  "counts_at_extraction": { "Approved": 2414366, "...": "..." }
}
```

(mirrored for `inspection_type_stage_mapping.json` with `stage_of` in
place of `family_of`). `mapping_version` is a plain semver-style string
bumped whenever the mapping tables themselves change; it is not currently
used to gate loading (no version-compatibility logic exists yet — a future
concern if the schema of the mapping file itself changes shape), only to
make it possible to tell, from data alone, which mapping version produced
a given `StallDetection`.

**Unknown-value routing — the load-bearing rule**: `family_of.get(raw,
ResultFamily.UNKNOWN)` and `stage_of.get(raw, None)` (never a `KeyError`,
never a default that falls through to an existing category, never fuzzy/
substring matching). A raw `inspection_result` or `inspection_type` value
encountered in live data that isn't a key in the mapping table — including
one that didn't exist at `vocabulary_extraction_date` and appears in the
source later — must resolve to `UNKNOWN` (results) or stay unmapped
(stages), visibly, not silently inherit whichever family/stage happens to
be alphabetically or numerically adjacent in the lookup implementation.
Tests for this behavior are part of the Agent 2 test suite (§11 below,
"vocabulary normalization" test group): a synthetic never-seen-before
string must map to `UNKNOWN`/`None`, and a value present in the mapping
must map to exactly its assigned category, with both checked in the same
test so a regression that widens the fallback can't pass silently.

---

## 6. Friction signal minimums and exposure-bias controls (refinements #6, #3-friction)

### 6a. Minimum count gate (unchanged from the first pass)

A `FrictionStallDetection` requires **both** of:

1. **Structural minimum**: `observed_count >= MIN_FRICTION_COUNT` (MVP
   default `2` for all three friction categories — "repeated" is
   definitionally more than once; one `Corrections Issued` event is
   ordinary, not a signal).
2. **Cohort-relative threshold**: `percentile_rank >= thresholds.watch`
   (§3) — even permits clearing the structural minimum aren't flagged
   unless their count is unusual *for their cohort*.

`MIN_FRICTION_COUNT` is configurable per category if evidence later
suggests different floors (e.g. `REPEATED_CANCELLATIONS` might warrant a
higher floor than `REPEATED_CORRECTIONS` — not yet justified by data, so
MVP uses one shared default).

### 6b. The exposure problem

Raw friction counts are confounded by how much *opportunity* a permit has
had to accumulate them. A permit with 40 inspections over 3 years having 6
corrections is unremarkable; a permit with 4 inspections over 2 months
having 3 corrections is a very different situation — a raw-count comparison
between them is comparing apples to oranges. Two distinct exposure
dimensions matter and are tracked separately rather than collapsed into
one:

- **Event exposure**: `total_inspection_opportunities` — count of all
  SUBSTANTIVE-family inspection events observed for this permit so far
  (the number of times a correction *could* have been logged).
- **Time exposure**: `observed_lifecycle_days` — days from `issue_date` to
  `now` (ongoing permits) or to the permit's terminal date (completed
  permits).

Both are carried on every `FrictionStallDetection`, always, regardless of
which one (if either) drives the cohort match — satisfying "carry an
exposure metric alongside the raw count" directly rather than folding it
invisibly into a rate.

### 6c. Cohort controls, layered

1. **Lifecycle-stage stratification (mandatory, applies first).** Every
   friction cohort is split into `COMPLETED` vs. `ONGOING` populations
   (mirroring `interval_state`, but at the cohort-membership level, not
   just the single detection level) and **never pooled**. A completed
   permit's total correction count over its full lifetime is not compared
   against an ongoing permit's count-so-far.

2. **Exposure-tier stratification for ONGOING permits.** Within the
   `ONGOING` population, permits are additionally bucketed into coarse
   exposure tiers by `total_inspection_opportunities` (e.g. 1–5, 6–15,
   16–30, 31+ — exact cut points to be set from real distribution shape
   during implementation, not assumed here). This directly addresses "young
   ongoing permit vs. multi-year completed permit" by making sure an
   ongoing permit is only ever compared against other ongoing permits at a
   *similar* exposure level, not the full ongoing population regardless of
   age.

3. **Minimum-exposure gate before assessing friction at all.** A permit
   with fewer than `MIN_EXPOSURE_FOR_FRICTION_ASSESSMENT` (MVP default: 3)
   substantive inspection events is too early in its process to assess
   meaningfully — Agent 2 does not attempt a friction detection at all for
   it, regardless of raw count, and instead notes it in `coverage_gaps`
   ("insufficient inspection exposure to assess friction: 1 substantive
   inspection observed so far").

4. **Rate as a carried, contextual metric — not (yet) the primary severity
   driver.** `correction_rate = observed_count / total_inspection_
   opportunities` is computed and stored on the detection whenever
   `total_inspection_opportunities > 0`, satisfying "correction count per
   inspection opportunity where appropriate." It is **not** used to drive
   `percentile_rank`/`severity` in the MVP: a rate computed from very few
   inspections is unstable (1 correction / 2 inspections = 50%, dwarfing a
   mature permit's 1 correction / 40 inspections = 2.5%, despite both being
   potentially unremarkable), and exposure-tier-matched raw counts are the
   more stable MVP control. Rate-based severity scoring is a reasonable
   future refinement once enough data exists to see whether it outperforms
   tier-matching — flagged, not built now.

5. **Fallback ladder** for friction cohorts becomes: `permit_type ×
   lifecycle_stage × exposure_tier × year-bucket` → drop year-bucket →
   drop exposure_tier → `permit_type × lifecycle_stage` → floor (same
   `FULL`/`REDUCED`/`INSUFFICIENT` confidence tiers as §2e).

### 6d. Target-permit exclusion from its own cohort (generalized, not friction-only)

**This rule applies to every cohort computation in this design, not just
friction** — the permit being assessed must be excluded from the
population used to compute that same permit's cohort statistics
(`n`, median, P75/90/95). This matters most visibly for friction (a
permit's own count shouldn't inflate the distribution it's being ranked
against) but applies identically to pre-issuance `ACTIVE_PEER_DWELL`
cohorts (the target permit is literally one of the "currently observed
comparable permits" in the bulk cross-sectional pull unless explicitly
filtered out) and to `COMPLETED_INTERVAL` inspection-gap cohorts. Enforced
as a single shared step in `analysis/cohorts.py`'s cohort-construction
function, not re-implemented per category.

---

## 7. `FINALIZATION_GAP` — permit-type aware terminal outcomes (refinement #7)

Not every permit is expected to reach a Certificate of Occupancy. From the
observed `status_desc` vocabulary and the five fixture permits already
validated in Agent 1 (both `Bldg-Alter/Repair` fixtures ended in `Permit
Finaled` with no `cofo_date`; the two `Bldg-New` fixtures both carry a
populated `cofo_date`), two **terminal tracks** are proposed:

| Track | Terminal marker | Permit population (proposed, not fully verified) |
|---|---|---|
| `COFO_TRACK` | `cofo_date` populated, or `status_desc` reaches a CofO-family state | Primarily `Bldg-New`, `Bldg-Addition` — new/added habitable space. Individual-permit membership is **not** fully determined by `permit_type` alone (a small addition may never need a CofO) — treated as a cohort-stratification heuristic, not a per-permit certainty |
| `FINALED_ONLY_TRACK` | `status_desc == "Permit Finaled"`, no `cofo_date` ever populated | `Bldg-Alter/Repair`, `Bldg-Demolition`, `Grading`, `Sign`, `Swimming-Pool/Spa`, `Nonbldg-*` — confirmed by both real `Bldg-Alter/Repair` fixtures |

**Non-terminal exits are explicitly excluded from `FINALIZATION_GAP`
entirely**: `Permit Expired`, `Permit Withdrawn`, `Permit Revoked`, `Permit
Closed` represent a permit leaving the pipeline without completing
construction, not a healthy finalization — scoring them on the same scale
would conflate "finished normally" with "abandoned." These are noted
separately (a `PERMIT_EXITED_WITHOUT_FINALIZATION` observation is a
reasonable future category, not built now).

`FINALIZATION_GAP`'s cohort is stratified by `(permit_type, track)` — never
comparing a `COFO_TRACK` gap against a `FINALED_ONLY_TRACK` cohort, since
they represent different completion pathways with different expected
durations.

---

## 8. Structured schema (updated for all 8 refinements)

```python
class StallClass(str, Enum):
    DELAY = "delay"
    FRICTION = "friction"

class StallCategory(str, Enum):
    PRE_ISSUANCE_STATUS_DWELL = "pre_issuance_status_dwell"
    ISSUANCE_TO_FIRST_INSPECTION_GAP = "issuance_to_first_inspection_gap"
    NO_INSPECTION_SINCE_ISSUANCE = "no_inspection_since_issuance"
    INTER_INSPECTION_GAP = "inter_inspection_gap"
    INACTIVITY_SINCE_LAST_INSPECTION = "inactivity_since_last_inspection"
    FINALIZATION_GAP = "finalization_gap"
    REPEATED_CORRECTIONS = "repeated_corrections"
    REPEATED_NOT_READY_OUTCOMES = "repeated_not_ready_outcomes"
    REPEATED_CANCELLATIONS = "repeated_cancellations"

class CohortSource(str, Enum):
    CROSS_SECTIONAL_CURRENT_SNAPSHOT = "cross_sectional_current_snapshot"
    COMPLETED_TRANSITIONS_OWN_HISTORY = "completed_transitions_own_history"
    SOURCE_EVENT_LOG = "source_event_log"

class BenchmarkSemantics(str, Enum):
    ACTIVE_PEER_DWELL = "active_peer_dwell"      # length-biased; "longer than X% of currently-waiting peers"
    COMPLETED_INTERVAL = "completed_interval"     # unbiased; "typically takes N days" language permitted

class IntervalState(str, Enum):
    COMPLETED = "completed"
    ONGOING = "ongoing"

class LifecycleStage(str, Enum):
    """Friction cohort stratification (§6c) — never pooled together."""
    COMPLETED = "completed"
    ONGOING = "ongoing"

class CohortConfidence(str, Enum):
    FULL = "full"                # n >= 30
    REDUCED = "reduced"          # 10 <= n < 30
    INSUFFICIENT = "insufficient"  # n < 10 -> no percentile/severity

class Severity(str, Enum):
    WATCH = "watch"        # [75, 90)
    ELEVATED = "elevated"  # [90, 95)
    SEVERE = "severe"      # >= 95
    UNSCORED = "unscored"  # CohortConfidence.INSUFFICIENT

@dataclass(frozen=True)
class SeverityThresholds:
    watch: float = 75.0
    elevated: float = 90.0
    severe: float = 95.0

@dataclass(frozen=True)
class CohortDefinition:
    dimensions: dict[str, str]
    specificity_level: int
    source: CohortSource
    benchmark_semantics: BenchmarkSemantics
    n: int
    confidence: CohortConfidence
    median_days_or_count: float | None    # contextual only — never a threshold (§3)
    p75_days_or_count: float | None
    p90_days_or_count: float | None
    p95_days_or_count: float | None
    computed_at: datetime

@dataclass(frozen=True)
class EvidenceRef:
    kind: str  # "status_snapshot" | "inspection_event" | "inspection_event_pair" | "event_count"
    description: str
    source_event_ids: list[str]                    # InspectionEvent.event_id references
    source_snapshot_refs: list[tuple[str, datetime]]  # (permit_number, observed_at) — PermitSnapshot's natural key
    source_status_date: date | None
    observed_dates: list[date]
    matching_method: str | None
    # e.g. "exact_inspection_type" | "mapped_stage_fallback" — required whenever
    # this evidence involved pairing two events (corrections -> reinspection)

@dataclass(frozen=True)
class DelayStallDetection:
    permit_number: str                    # 1. source permit
    category: StallCategory
    stage_label: str                      # literal status_desc or inspection_type/stage
    generated_at: datetime

    elapsed_days: int                     # 4. calculated metric
    as_of: datetime
    interval_state: IntervalState         # 3. completed vs. ongoing

    status_persistence_confirmed_by_repeated_observation: bool
    # mirrors ObservedTransition.confirmed_by_repeated_observation (Agent 1)
    # for the status this detection concerns — see §2c-1. Only relevant for
    # ACTIVE_PEER_DWELL detections; False for anything derived from a single
    # snapshot, regardless of elapsed_days.

    cohort: CohortDefinition              # 5,6,7. cohort def, n, benchmark stats+semantics (all embedded)
    percentile_rank: float | None
    excess_days_vs_median: float | None   # contextual, not a severity input
    severity: Severity

    evidence: list[EvidenceRef]           # 2. event/snapshot IDs, observed dates — never empty
    cannot_infer: list[str]               # 9.
    caveats: list[str]                    # 8. — mandatory ACTIVE_PEER_DWELL / ONGOING caveats live here
    based_on_match_status: MatchStatus
    carried_data_quality_flags: list[str]

@dataclass(frozen=True)
class FrictionStallDetection:
    permit_number: str
    category: StallCategory
    generated_at: datetime

    observed_count: int
    meets_minimum_count: bool             # explicit record that the §6a structural gate was checked
    minimum_count_required: int

    lifecycle_stage: LifecycleStage       # §6c.1 — which population this permit was compared against
    total_inspection_opportunities: int   # §6b — event exposure, always carried
    observed_lifecycle_days: int          # §6b — time exposure, always carried
    correction_rate: float | None         # §6c.4 — observed_count / total_inspection_opportunities;
                                           # contextual only, does not drive severity in MVP
    meets_minimum_exposure: bool          # §6c.3 — explicit record of the exposure gate check

    cohort: CohortDefinition              # exposure-tier-matched, per §6c.2/.5
    percentile_rank: float | None
    excess_count_vs_median: float | None
    severity: Severity

    evidence: list[EvidenceRef]           # one ref per contributing event, minimum
    cannot_infer: list[str]
    caveats: list[str]
    based_on_match_status: MatchStatus
    carried_data_quality_flags: list[str]

@dataclass(frozen=True)
class StallAssessment:
    permit_number: str
    generated_at: datetime
    source_permit_journey_generated_at: datetime

    detections: list[DelayStallDetection | FrictionStallDetection]
    coverage_gaps: list[str]
    # includes: insufficient-cohort skips (§2e) AND eligibility-gate skips (§4c)

    summary_note: str
```

**Evidence completeness (refinement #8)** — every `DelayStallDetection`
and `FrictionStallDetection` carries, without exception: source permit
(`permit_number`), event/snapshot IDs (`evidence[].source_event_ids` /
`.source_snapshot_refs`), observed dates (`evidence[].observed_dates` /
`.source_status_date`), the calculated metric (`elapsed_days` or
`observed_count`), cohort definition + n + benchmark stats
(`cohort.dimensions`, `.n`, `.median/p75/p90/p95`), benchmark semantics
(`cohort.benchmark_semantics`), caveats (`caveats`), and cannot-infer
statements (`cannot_infer`). None of these are optional/sometimes-absent
fields — a detection that can't populate all of them shouldn't be emitted.

---

## 9. Edge cases (rev. 1's 12, unchanged, plus 2 new from this revision)

1. `STATUS_ISSUE_DATE_INCONSISTENT` permits — skip percentile scoring,
   `coverage_gaps` entry, flag carried forward.
2. Single-observation permits — elapsed time still valid (`status_date` is
   observed); persistence-confirmed language gated by `ObservedTransition.
   confirmed_by_repeated_observation`, reused directly from Agent 1.
3. `NO_INSPECTION_SINCE_ISSUANCE` eligibility — now formalized in §4, not
   just a flag check.
4. Trivially-fresh permits — no special-casing; naturally produce no
   detection.
5. Corrections↔reinspection matching by exact `inspection_type` isn't
   perfectly reliable — now has a documented fallback (§5b) with the
   matching method recorded in evidence rather than silently guessed.
6. `Insp Cancelled`/`Cancelled` events are cause-ambiguous — kept as their
   own `REPEATED_CANCELLATIONS` friction subtype; `cannot_infer` states
   cause is not determinable.
7. Structurally tiny permit types (`Bldg-Relocation`: 5–13 permits per
   slice) — expected to land in `coverage_gaps`, not a bug.
8. Rare administrative statuses (`*`, `Hold Released`, single-digit-to-teens
   counts) — same treatment as #7.
9. Source refresh staleness — `PermitSnapshot.source_refresh_time` already
   captured by Agent 1; surfaced as a caveat when materially old.
10. Zero/near-zero inspection gaps (same-day duplicate rows observed in
    real data) — flagged for exclusion/review, not trusted as a genuine
    instant turnaround.
11. Status non-monotonicity (`Re-Activate Permit`, `CofO Reactivated`) —
    `collapse_snapshots_to_transitions` already handles arbitrary
    sequences; a caution for cohort construction, not a blocker.
12. ~4.1% null `inspection_result` — now formally the `UNKNOWN` family
    (§5a), excluded from `SUBSTANTIVE`-dependent logic, counted separately.
13. **(new)** `ONGOING` intervals compared against a `COMPLETED_INTERVAL`
    cohort (`INACTIVITY_SINCE_LAST_INSPECTION`) — a distinct, milder bias
    from length-bias; gets its own caveat (§2c).
14. **(new)** Permits exiting via `Permit Expired`/`Withdrawn`/`Revoked`/
    `Closed` — excluded from `FINALIZATION_GAP` scoring entirely (§7), not
    silently scored on the wrong scale.

---

## 10. What this design deliberately does not do

Unchanged from rev. 1, restated: never assigns responsibility for a delay;
never explains *why* a gap happened (Agent 3's job, grounded in a curated
knowledge base); never treats missing data as a positive claim in either
direction. Refinements #2–#4 in this revision are direct extensions of
this principle — `benchmark_semantics`, `interval_state`, and the coverage
eligibility gate all exist specifically to prevent Agent 2 (or a careless
reading of its output) from asserting more than the data supports.

---

## 11. Validation strategy using real permits

Unchanged core plan from rev. 1 (§7 there), now updated for the new
mechanics:

1. **Face validity on Agent 1's 5 fixture permits**, re-checked against the
   revised severity bands and eligibility gate:
   - `21030-20000-00256` (unissued, `PC Approved` since 2021-08-04,
     ~1,800+ days elapsed) — `PRE_ISSUANCE_STATUS_DWELL`, `interval_state=
     ONGOING`, `benchmark_semantics=ACTIVE_PEER_DWELL`. At this elapsed
     magnitude, expected to clear P95 (`SEVERE`) under essentially any
     realistic cohort, single-observation caveat attached per edge case 2.
   - `18010-20001-05038` ($0 administrative correction permit, 0
     inspections, `Bldg-Alter/Repair`) — `Bldg-Alter/Repair` clears the
     §4 eligibility gate (71.1% match rate ≥ 60%), so
     `NO_INSPECTION_SINCE_ISSUANCE` *is* assessed here (unlike `Bldg-New`)
     — worth checking by hand whether it should still fire given this
     permit's administrative nature (`work_desc` pattern "SUPPLEMENTAL
     TO... TO CORRECT LEGAL DESCRIPTION") — a possible future refinement
     to exclude clearly-administrative permits from this category, not
     designed yet.
   - `21016-20000-20141` (clean 3-event lifecycle) — should produce no
     detections; validates the P75 floor isn't over-triggering on routine
     permits.
   - `21010-10000-05865` (82 events, real correction cycles) — validates
     `REPEATED_CORRECTIONS` against the new min-count-2 gate and the
     exact-vs-mapped-stage matching fallback from §5b.
   - `20010-20000-02739` (finaled via CofO) — validates `FINALIZATION_GAP`
     on the `COFO_TRACK` (has a populated `cofo_date`).

2. **Cohort-size dry run** — extend the §2e spot-check to the full
   `permit_type × status_desc` and `permit_type × inspection_type`/stage
   cross-tabs before writing cohort-computation code.

3. **`business_unit` as a cohort dimension** — test whether it produces
   statistically distinct dwell distributions before adopting it into the
   ladder.

4. **Correction-matching accuracy** — manually trace `21010-10000-05865`'s
   82 events against both the exact-type and mapped-stage matching rules
   to see how often they diverge and which is more defensible.

5. **Stage-mapping review** — the 88.6%-coverage `inspection_type` → stage
   grouping (§5b) is a structural guess from label text; flagged for review
   by anyone with real LADBS inspection-sequence knowledge before Agent 3
   ever surfaces stage-grouped language to a developer.

6. **Cross-sectional bias** — monitor, don't attempt to fully resolve now;
   revisit once `permit_snapshots` accumulates enough history to compare
   `ACTIVE_PEER_DWELL` against a real `COMPLETED_INTERVAL` distribution for
   the same statuses.

---

Approved with these 4 additional controls (coverage-threshold sensitivity
analysis, structural dwell-language gate, friction exposure-bias controls,
mapping versioning). Implementation followed in that same change.

## 12. Post-implementation fixes (revision 3)

Live demonstration against 6 real permits (implementation report) surfaced
two bugs producing materially misleading results. Both are fixed; this
section documents what was found and the fix, keeping §3/§7 above as the
original design record.

### 12a. Zero-variance cohorts (fixes the FINALIZATION_GAP false positive)

**Bug**: `21016-20000-20141`'s `FINALIZATION_GAP` fired **SEVERE** at
`elapsed_days=0` — the sampled cohort (n=50, `Bldg-Alter/Repair`
`finaled_only_track`) had `median=p75=p90=p95=0.0` (every observed value
identical). `percentile_rank`'s `<=` tie convention put any value equal to
a degenerate cohort's constant at the 100th percentile, regardless of
whether that value is remarkable.

**Fix**: `CohortConfidence` gained a fourth member, `ZERO_VARIANCE`
(`schema/stall_detection.py`). `analysis/cohorts.py::compute_cohort_
definition` checks the population's range (`max - min`); a cohort with
adequate `n` but a range below one whole unit (`ZERO_VARIANCE_RANGE_
THRESHOLD = 1.0`) is marked `ZERO_VARIANCE` instead of `FULL`/`REDUCED`,
and no percentile is computed against it. `build_cohort_with_fallback`
treats `ZERO_VARIANCE` the same as `INSUFFICIENT` for ladder purposes — it
keeps falling back to a coarser tier, since a coarser population might
have real spread even if a narrow one doesn't. Every `stall_detector.py`
call site now routes through a shared `_cohort_gap_message()` helper that
emits a distinct `"ZERO_VARIANCE_COHORT"`-labeled `coverage_gaps` entry
explaining the cohort has no discriminatory information, instead of
silently producing (or silently suppressing without explanation) a
detection.

**A range check, not the originally-considered stdev threshold**: an
initial attempt used `stdev < 0.5`, which correctly caught the degenerate
all-zero case but also mis-flagged legitimate low-variance count data — a
friction population that's 45×`0` and 5×`1` has `stdev≈0.3` but is not
degenerate (a permit with 5 corrections against that population is a real
outlier). Range is checked instead, thresholded at 1.0 full unit — since
every population in this project is whole days or whole event counts, a
range below 1.0 means every value is effectively the same number, which is
what "zero variance" should actually mean here.

**`FINALED_ONLY_TRACK` reassessed and removed, not just gated**. Per your
instruction to check whether same-day finalization is normal LADBS
behavior rather than relying on the generic gate to catch it every time,
pulled real population data directly:

```
Bldg-Alter/Repair / cofo_track:         n=17  min=0   max=268  stdev=68.5
Bldg-New         / cofo_track:          n=51  min=0   max=367  stdev=63.0
Bldg-Alter/Repair / finaled_only_track: n=50  min=0   max=0    stdev=0.0
Bldg-New         / finaled_only_track:  n=0
```

`finaled_only_track` is confirmed degenerate on real data, not just in one
sample — `status_date` for `Permit Finaled` appears to get set the same
day as the qualifying final inspection as a matter of LADBS process, so
there is no discriminatory signal to measure. `_detect_finalization_gap`
now returns immediately for this track with an explanatory `coverage_gaps`
message, rather than attempting the fetch/cohort/percentile machinery on
every single finaled-only permit only to hit `ZERO_VARIANCE_COHORT` every
time. `cofo_track` is kept — real, substantial variance (stdev ~63–68 days,
range up to 367 days) confirms it's analytically useful.

**Regression tests**: `tests/test_cohorts.py` (target=0/cohort-all-0 →
`ZERO_VARIANCE`, not `FULL`; a realistic low-but-real-variance population
stays `FULL`; the fallback ladder skips a degenerate tier for a better one
and correctly reports `ZERO_VARIANCE` when even the floor tier is
degenerate) and `tests/test_stall_detector.py::test_finalization_gap_
never_assessed_for_finaled_only_track`.

### 12b. Inspection-exemption eligibility layer (fixes the admin-permit false positive)

**Bug**: `18010-20001-05038` — a real, verified $0-valuation "SUPPLEMENTAL
TO 18010-20000-05038: TO CORRECT LEGAL DESCRIPTION DUE TO TRACT MAP
RECORDATION" permit, i.e. a paperwork correction with no construction
work — produced a **SEVERE** `NO_INSPECTION_SINCE_ISSUANCE` because its
`permit_type` (`Bldg-Alter/Repair`, 71.1% aggregate match rate) clears the
type-level coverage gate. The aggregate gate protects against *data-
linkage* uncertainty (§4); it says nothing about whether a specific,
individual permit plausibly needs an inspection at all.

**Fix**: a new deterministic, auditable, permit-level layer,
`analysis/inspection_exemption.py`, checked *before* the aggregate
type-level gate (permit_type alone is not sufficient, per your
instruction). Two signals, checked conservatively:

- **Zero valuation** (`valuation == 0`).
- **Administrative-language match** in `work_desc` against a curated,
  reviewable pattern list (`ADMINISTRATIVE_WORK_DESC_PATTERNS`): supplemental-
  permit references, legal-description/address/tract-map corrections,
  "DEPARTMENT ERROR", "NO FEE", "VOID", duplicate-permit language,
  change-of-contractor/architect/engineer/owner, explicit "ADMINISTRATIVE
  CORRECTION"/"REVISE PERMIT" phrasing.

**Both signals present** → `is_plausibly_exempt=True`, skip the signal,
`coverage_gaps` entry naming the matched patterns. **Only one signal
present** → `is_ambiguous=True`, also skip the signal (do not proceed to
either exempt-and-silent or eligible-and-scored), distinct `coverage_gaps`
wording. **Neither signal** → proceeds to the existing aggregate type-level
gate unchanged.

No LLM classification, per your instruction — plain regex/substring
matching against real observed field values, with every match traceable to
the exact pattern that fired (`matched_signals` on the result object).

Deliberately conservative in the direction of *not* suppressing a real
stall: a permit with only a zero valuation, or only matching language, is
routed to a coverage gap rather than confidently declared exempt — false
negatives (missing a real administrative permit, letting the aggregate
gate make the call) are preferable here to false positives (wrongly
suppressing a genuine stall signal).

**Verified against three real permits** (not just synthetic fixtures):
`18010-20001-05038` (both signals → exempt), `20010-20000-02739` (neither
signal → proceeds normally), and `22014-10001-04999` — a real permit found
by searching live data for exactly this shape (`$0` valuation, no matching
administrative language: "SUPPLEMENTAL PERMIT TO INCREASE BUILDING HEIGHT
AND REVISE CEILING HEIGHTS" — a real scope change, not a paperwork fix) →
correctly `is_ambiguous=True`, not silently treated either way.

**Regression tests**: `tests/test_inspection_exemption.py` (6 tests, pure
logic layer, using the three real permits above plus edge cases) and
`tests/test_stall_detector.py::test_no_inspection_since_issuance_
administrative_permit_no_false_positive` / `..._ambiguous_permit_is_
coverage_gap_not_stall` (integration level).

### 12c. `ACTIVE_PEER_DWELL` semantics — no threshold change, documentation hardened

Per your instruction, `21030-20000-00256`'s result (0 detections; 1,833
days elapsed ranks at the 74.6th percentile of its `Grading`/`PC Approved`
active-peer cohort, n=1,652, max observed 2,401 days) is **kept as-is** —
no threshold was adjusted to make it fire. `_ACTIVE_PEER_DWELL_CAVEAT` in
`stall_detector.py` was rewritten to lead with the precise question this
percentile answers ("how unusual is this among permits *currently
observed* in this status") and to explicitly name what it does *not*
answer (normal/expected stage-completion time), rather than leaving that
distinction implicit in a caveat about sampling bias. This is the same
restriction already structurally enforced by `render_dwell_statement()`
(§2c-1) — §12c is a documentation strengthening, not a new mechanism.

### 12d. MVP scope-gap classification

All four items reviewed against the two bugs just fixed and reclassified
where warranted — **none required promotion to "required for reliability"
as a consequence of this fix pass**; both bugs were orthogonal to cohort
tiering or gap-selection breadth:

| Item | Classification | Reasoning |
|---|---|---|
| Year-bucket cohort fallback tier (not built) | **Acceptable MVP deferral** | The 2-tier ladder still compares against a real, appropriately-scoped cohort; missing year-bucketing reduces precision, doesn't misrepresent anything |
| Friction exposure-tier sub-stratification (only lifecycle_stage implemented) | **Acceptable MVP deferral** | The mandatory primary control (COMPLETED vs ONGOING) is in place and prevents the worst case (multi-year vs. brand-new). Flagged as the most likely of the four to matter eventually — next priority if revisited |
| `INTER_INSPECTION_GAP` reports only the largest gap | **Acceptable MVP deferral** | Underreports (a second real gap elsewhere won't surface) but the gap it does report is accurate, not misleading |
| Same-type/stage correction↔reinspection pairing (not built; uses any-consecutive-substantive-event gap instead) | **Acceptable MVP deferral** | "No inspection activity of any kind occurred in this window" is a true statement regardless of trade; coarser than a same-defect-resolution signal, not incorrect |

Full reasoning for each restated in `stall_detector.py`'s module docstring
so it travels with the code, not just this document.

---

Fixes approved and implemented in this same change. Agent 2 status:
implemented, tested (82 tests), demonstrated against 6 real permits with
both known false positives confirmed fixed. Agent 3 not started.
