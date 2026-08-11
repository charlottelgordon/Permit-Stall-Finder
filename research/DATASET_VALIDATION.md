# Dataset Validation — Permits vs. Inspections

Status: **superseded in part — see §8.** Sections 0–7 were written before a
third-party dataset lead (`pi9x-tg5x`) surfaced a whole family of
currently-maintained datasets that change the canonical-source
recommendation and reopen the "no pre-issuance data" conclusion in §4/§0.3.
Sections 0–7 are left intact below as the record of how that conclusion was
reached; §8 is the current recommendation. Read §8 first.

All numbers below come from live queries against `data.lacity.org`
(Socrata). Scripts used are in `scripts/` and are re-runnable — they only
depend on the Python standard library (no `requests`, no app token).

## 0. TL;DR — the four things that changed the plan (as of §0–7; revised in §8)

1. **`xnhu-aczu` is a strict subset of `hbkd-qubn`**, not a duplicate or an
   independently-sourced dataset. 100% of `xnhu-aczu`'s permit numbers exist
   in `hbkd-qubn`; `hbkd-qubn` additionally covers 15 permit types (all
   electrical/plumbing/mechanical/etc. trade permits) that `xnhu-aczu`
   excludes by design.
2. **Both permit datasets stopped updating on 2023-05-19/21 and have not
   moved since** (`rowsUpdatedAt` timestamp is identical on both:
   2023-05-22). The inspections dataset (`9w5z-rg2h`), by contrast, is live
   — its most recent inspection in the data is **2026-08-08**, three days
   before this report. Any permit issued after May 2023 simply cannot exist
   in either permit dataset today.
3. **Neither permit dataset contains a pre-issuance timeline.** Every row in
   both datasets has a non-null `issue_date`, and the small number of
   permits with more than one row (~0.2%) turn out to be near-duplicate
   ETL artifacts — identical `latest_status`, differing `issue_date` on the
   *same* permit — not a submission → plan-check → issuance sequence. There
   is no "Submitted" or "In Plan Check" status anywhere in the data. This
   directly affects the PRD's Agent 1 requirement to capture "submission,
   plan check milestones, issuance" — that milestone data does not exist in
   these two sources as published.
4. **The permit ↔ inspection join works well in the direction the product
   actually needs** (given a permit, find its inspections: 80.7% match),
   but is much weaker in the reverse direction for old permits, which
   traces almost entirely to the 2023 coverage cutoff rather than to key
   normalization.

Everything below is the evidence for these four claims, plus a revised
architecture that accounts for them.

## 1. Dataset comparison

| | `xnhu-aczu` | `hbkd-qubn` |
|---|---|---|
| Portal title | "LA BUILD PERMITS" | "LADBS-Permits" |
| Attribution | LADBS | LADBS |
| Portal category | A Prosperous City | City Infrastructure & Service Requests |
| Created | 2015-10-13 | 2017-09-03 |
| Rows last updated | 2023-05-22 (epoch 1684748004) | 2023-05-22 (epoch 1684748004, identical) |
| View metadata last touched | 2025-01-28 | 2025-01-15 |
| Total rows | 375,150 | 1,635,148 |
| Distinct `pcis_permit` | 374,398 | 1,632,568 |
| `issue_date` range | 2015-11-03 → 2023-05-19 | 2013-01-01 → 2023-05-19 |
| Permit types covered | 3: `Bldg-New`, `Bldg-Addition`, `Bldg-Alter/Repair` | 18: the above 3 plus Electrical, Plumbing, HVAC, Fire Sprinkler, Grading, Nonbldg-*, Swimming-Pool/Spa, Bldg-Demolition, Elevator, Sign, Pressure Vessel, Bldg-Relocation |
| Rows with null `issue_date` | 0 | 0 |
| Schema richness | 51 columns: adds `latest_status`, `status_date`, `event_code`, `permit_category`, `project_number`, assessor book/page/parcel, tract/block/lot, floor area (x2), census tract, `location_1` (lat/lon), address fractions, unit ranges | 24 columns: issuance-time facts only (type, sub-type, address, work description, valuation, contractor/applicant, zone, council district) — no status/event fields at all |

**Relationship**: confirmed by set comparison (`scripts/pull_permit_ids.py` +
`scripts/analyze_overlap.py`), pulling the *full* distinct permit-number set
from both datasets (374,398 and 1,632,568 respectively) and normalizing
separators:

- `xnhu-aczu ∩ hbkd-qubn` = 374,398 permits = **100.0% of `xnhu-aczu`**, 22.9%
  of `hbkd-qubn`.
- Every permit in `xnhu-aczu` exists in `hbkd-qubn`; nothing in `xnhu-aczu`
  is absent from `hbkd-qubn`.

So: **`xnhu-aczu` is `hbkd-qubn` filtered to the three core building-permit
types, with a richer per-permit schema layered on top** (parcel data,
zoning floor area, geocoding, and a `latest_status`/`status_date` pair that
`hbkd-qubn` doesn't have). They are not independent sources and not
duplicates of each other — one is a curated view built from the other's
population, published separately with extra fields.

### The "multiple rows per permit" pattern, and why it's not a timeline

Both datasets have a small number of permits with more than one row
(~752 permits in `xnhu-aczu`, ~2,580 in `hbkd-qubn` — about 0.2% each).
Initial inspection of these looked promising (a permit with 7 rows looked
like it might be a status-change log). Pulling the full row set for two
such permits shows the actual pattern:

```
pcis_permit          latest_status  status_date   issue_date
21016-90000-08046     Issued         2021-06-09    2021-06-09
21016-90000-08046     Issued         2021-06-09    2021-06-09
21016-90000-08046     Issued         2021-06-09    2021-06-08
21016-90000-08046     Issued         2021-06-09    2021-06-09
21016-90000-08046     Issued         2021-06-09    2021-03-31
21016-90000-08046     Issued         2021-06-09    2021-06-09
21016-90000-08046     Issued         2021-06-09    2021-06-09
```

`latest_status` and `status_date` are **identical across every row for the
same permit**; only `issue_date` jitters by a few days between rows. That's
consistent with repeated/duplicated ETL loads of the same issuance record,
not a genuine event sequence. Across the full dataset, `latest_status`
values are exclusively post-issuance states (`Issued`, `Permit Finaled`,
`CofO Issued`, `Permit Expired`, `Refund Completed`, `Permit Withdrawn`,
`Permit Revoked`, etc. — 27 distinct values, all listed in
`scripts/analyze_overlap.py`'s companion query output). Nothing resembling
"Submitted," "Application Received," or "In Plan Check" appears anywhere.
`event_code` is populated on only 2 of 375,148 rows — effectively unused.
`permit_category` (`Plan Check` vs. `No Plan Check`) is a classification of
review pathway, not a live status.

**Conclusion**: for both datasets, one row ≈ one permit ≈ one
point-in-time snapshot taken at or after issuance. There is no reconstructable
pre-issuance journey in either source.

## 2. Recommended canonical permit source

**`xnhu-aczu` ("LA BUILD PERMITS")**, for the current MVP scope, because:

- It's a strict subset of `hbkd-qubn` restricted to actual *building*
  permits — matching the PRD's named source ("LA Building Permits") and
  its Agent 1 scope, rather than all LADBS permit types (electrical,
  plumbing, signs, pools, etc.).
- It carries fields `hbkd-qubn` lacks that matter for stall-cohort
  benchmarking later: `permit_category` (Plan Check vs. No Plan Check —
  a real driver of expected timeline), assessor/parcel identifiers, and
  geocoding.
- `hbkd-qubn` remains documented here as the broader superset in case scope
  ever expands to trade permits (electrical/plumbing/mechanical) — switching
  is a filter change, not a re-architecture, since the join key and record
  shape for the columns they share are identical.

This is a scope recommendation, not a schema-availability one — both
datasets have the same pre-issuance-data gap described above, so switching
canonical sources would not recover a submission/plan-check timeline.

## 3. Join validation against inspections (`9w5z-rg2h`)

Inspections dataset: 11,637,515 total rows, 1,912,442 distinct `permit`
values, `inspection_date` range **2013-01-01 → 2026-08-08** (live, current
as of this report).

**Normalization required**: the `permit` field mixes separator styles
within the same dataset — e.g. `"14044 10000 02293"` (space) and
`"00010-10000-00975"` (dash) both occur. `pcis_permit` in the permit
datasets uses dashes consistently (`"20010-30000-00390"`). All matching
here strips every non-alphanumeric character and uppercases before
comparing (`re.sub(r"[^A-Z0-9]", "", s.upper())`); no other transformation
was needed — the underlying digit sequences line up once separators are
removed.

### 3a. Permits → inspections (the direction the product needs)

Random sample of 1,500 distinct permits from `xnhu-aczu` (seeded, reproducible
via `scripts/permit_to_inspection_match.py`), checked directly against
`9w5z-rg2h` with both separator variants:

**1,211 / 1,500 = 80.7% of sampled permits have ≥1 matching inspection
record.**

Unmatched examples span a mix of statuses and aren't explained by one
obvious cause — includes recently-issued permits that may predate any
inspection activity, but also older `Permit Finaled` / `CofO Issued`
permits that would be expected to have at least a final inspection on
record and don't:

```
16010-20000-02443  issued 2017-12-06  CofO Issued     Plan Check    Bldg-New
18016-90000-25812  issued 2018-08-10  Refund Completed No Plan Check Bldg-Alter/Repair
17016-70000-15867  issued 2017-06-13  Permit Finaled   No Plan Check Bldg-Alter/Repair
16016-20000-19565  issued 2016-08-19  Refund Completed No Plan Check Bldg-Alter/Repair
19016-20000-15221  issued 2019-09-17  CofO Issued      Plan Check    Bldg-Alter/Repair
```

**Open question, not yet resolved**: the ~19% gap needs a closer look
before Agent 2 treats "no inspection record" as a meaningful signal (e.g.
"awaiting first inspection") rather than a data-coverage artifact. Worth
checking whether `Refund Completed` / cancelled-before-work-started
permits are expected to have zero inspections (plausible — no work
occurred) versus whether `Permit Finaled` with zero inspections indicates
a genuine inspections-side gap.

### 3b. Inspections → permits (reverse direction)

Stratified sample of 11,200 distinct inspection `permit` values (800 per
year, 2013–2026, via `scripts/sample_inspection_permits.py`), checked
against the full normalized permit-number sets from both `xnhu-aczu` and
`hbkd-qubn`:

**Overall: 590 / 11,200 = 5.3% matched either permit dataset.**

This looks alarming until you segment by the permit number's embedded
year prefix (PCIS numbers start `YY-...`, e.g. `21016-...` = opened 2021).
**92.9% of unmatched inspection permits have a year prefix before 13**
(i.e., the underlying permit was issued/opened before 2013 — before either
permit dataset's coverage begins) or in the 23–26 range (issued after the
May-2023 freeze, so structurally cannot appear in a frozen dataset):

```
permit_yy_prefix   total   matched   match_rate
00 (year 2000)       882      15       1.7%
05 (year 2005)      1724     123       7.1%
10 (year 2010)       108      19      17.6%
18 (year 2018)         9       8      88.9%
19 (year 2019)        13      10      76.9%
21 (year 2021)        19      11      57.9%
23 (year 2023)        32       0       0.0%
25 (year 2025)       270       0       0.0%
26 (year 2026)       333       0       0.0%
```

Restricting to inspection records whose permit's year-prefix falls in the
dataset's nominal coverage window (13–22) raises the match rate to
**61.0% (n=77)** — better, but the sample size here is small (this is a
sub-slice of an already-stratified sample) and shouldn't be treated as a
precise number, just directional confirmation that the gap is
coverage-driven rather than a normalization failure. A dedicated larger
pull restricted to that window would tighten this estimate before it's
relied on.

**Practical implication**: the low reverse-direction rate is not a defect
in the join logic — it's old buildings still receiving inspections decades
after a permit whose issuance record predates both public datasets. Since
the product's actual query pattern is "developer has a permit number, show
me its journey" (forward direction), 3a's 80.7% is the more relevant number
for MVP feasibility. 3b matters if the product ever needs to go
inspection-first (e.g. "what permit does this inspection belong to" for
inspections on old buildings) — which is not in the current PRD scope.

## 4. What this means for the PRD's Agent 1 scope

The PRD asks Agent 1 to capture "submission, plan check milestones,
issuance, and every inspection event." Given the findings above, only two
of those are actually observable in `xnhu-aczu` + `9w5z-rg2h`:

- **Issuance** — one fact per permit (`issue_date`, plus `latest_status` as
  of the dataset's last refresh, which may already reflect a later state
  like `Permit Finaled` or `CofO Issued`).
- **Every inspection event** — a genuine ordered sequence
  (`inspection_date`, `inspection`, `inspection_result`) per permit, this
  *is* real timeline data.

**Submission and plan-check milestones are not present** in either
dataset. Per your instruction #2, Agent 1 must not infer a submission date
from the earliest observed row. In practice, for the ~99.8% of permits
with exactly one permit-dataset row, there is only one observed permit-side
event at all — it should be labeled by what it actually is, not what it's
assumed to represent:

| Field | Meaning | Type |
|---|---|---|
| `issue_date` | LADBS's recorded issuance date | Observed source event |
| `first_observed_permit_event` | The earliest permit-dataset row for this permit (in ~99.8% of cases, identical to `issue_date`; for the ~0.2% multi-row permits, the earliest of the near-duplicate rows) | Observed source event — explicitly *not* labeled "submission" |
| `latest_status` | Status as of this dataset's last refresh (2023-05-19) | Observed source event, but staleness-qualified |
| stage inferred from inspection sequence (e.g. "post-issuance, pre-final") | Derived from ordering inspection events against `issue_date` | Derived/calculated field |
| "this permit appears stalled awaiting reinspection" | Agent 2's interpretation of a gap pattern | Inferred interpretation — must carry its own reasoning/evidence, never presented as fact |

This distinction (observed / derived / inferred) is carried through as an
explicit tag on every field in the Agent 1 → Agent 2 → Agent 3 schema
below, not just a naming convention.

## 5. Revised three-agent architecture

Retained as three distinct agent roles per your instruction, each with a
structured contract, coordinated by a thin orchestrator. Deterministic
Python (join, stats, cohort percentiles) does the actual computation
underneath each agent; the "agent" boundary is about the input/output
contract and separation of concerns, not about forcing an LLM into stages
that don't need one.

```
Orchestrator
  → Agent 1: Journey Reconstructor  → PermitJourney
  → Agent 2: Stall Detector         → StallAssessment
  → Agent 3: Developer Explainer    → DeveloperExplanation
```

### Agent 1 — Journey Reconstructor

- **Input**: a permit number (or a batch), plus raw rows from `xnhu-aczu`
  and `9w5z-rg2h`.
- **Tooling underneath**: normalization (strip separators), the join,
  event ordering.
- **Output contract** (`PermitJourney`):
  ```
  permit_number: str
  permit_type, permit_sub_type, work_description, permit_category
  issue_date: date                     # observed
  first_observed_permit_event: date    # observed, explicitly not "submission"
  latest_status: str                   # observed, timestamped with dataset refresh date
  source_dataset_as_of: date           # staleness disclosure, e.g. 2023-05-19
  inspection_events: [
    { inspection_date, inspection_type, inspection_result }  # observed, ordered
  ]
  reconstruction_notes: [str]          # e.g. "no permit-dataset match found",
                                        # "0 inspection events found"
  match_status: enum[MATCHED, PERMIT_ONLY, UNRECONCILABLE]
  ```
  Permits with no inspection match, or no permit-dataset match at all, are
  still emitted with `match_status` set accordingly and logged — never
  silently dropped, per the PRD requirement.

### Agent 2 — Stall Detector

- **Input**: one or more `PermitJourney` objects, plus a comparable-cohort
  reference (see below).
- **Output contract** (`StallAssessment`):
  ```
  permit_number: str
  stage: str                    # e.g. "post-issuance, awaiting first inspection"
  elapsed_days: int              # derived
  cohort_definition: {permit_type, permit_sub_type, permit_category, issue_year_bucket, stage}
  cohort_n: int
  cohort_median_days, p75_days, p90_days: float   # derived, empirical
  percentile_rank: float          # where this permit falls in its cohort
  excess_days: float              # elapsed - cohort_median
  signal_type: enum[AWAITING_REINSPECTION, REPEATED_CORRECTIONS,
                     FAILED_INSPECTION, NOT_READY, CANCELLED_INDICATORS,
                     INACTIVITY, INSUFFICIENT_COHORT_DATA]
  is_stalled: bool                # derived from percentile_rank vs. configurable cutoff
  evidence: [str]                 # the specific inputs that drove the flag — inspectable
  threshold_config_version: str   # auditability
  ```
- Per instruction #4, no fixed-day thresholds up front. Cohorts are built
  from fields actually present and populated in the data:
  `permit_type` / `permit_sub_type` / `permit_category` (Plan Check vs No
  Plan Check materially changes expected timeline) / issue-year bucket /
  inspection stage. `is_stalled` is a percentile-rank cutoff against the
  permit's own cohort (e.g. "past the 90th percentile for comparable
  permits"), not an absolute day count — the day-count equivalents in the
  contract are outputs of that calculation, not inputs to it.
- Distinct `signal_type`s reflect the finding above that "stalled" isn't
  one phenomenon: a permit sitting untouched since issuance (`INACTIVITY`),
  one with a `Not Ready` or `Insp Cancelled` result on file
  (`NOT_READY` / `CANCELLED_INDICATORS`), one with several `Partial
  Approval` results in a row (`REPEATED_CORRECTIONS`), and one with an
  outright `Failed`/disapproval result (`FAILED_INSPECTION`) are different
  situations with different likely next steps — collapsing them into one
  generic "delay" measure would lose exactly the information Agent 3 needs
  to be useful.
- Before this agent is built for real, a data-profiling pass is needed on
  `inspection_result`'s actual value vocabulary (we've only seen a handful
  of values so far: `Approved`, `Partial Approval`, `Insp Cancelled`,
  `Not Ready`) to confirm the full set and settle the cohort-size question —
  see open items below.

### Agent 3 — Developer Explainer

- **Input**: one `StallAssessment` + an approved knowledge base of stall
  explanations keyed by `signal_type`/`stage` (not free-form retrieval).
- May use an LLM, but only to phrase structured facts already supplied by
  Agents 1–2 plus the approved knowledge base — never to originate a cause.
- **Output contract** (`DeveloperExplanation`):
  ```
  what_the_data_shows: str        # restates StallAssessment facts plainly
  what_this_usually_means: str    # grounded in the knowledge-base entry for this signal_type
  developer_actionable_steps: [str]
  city_dependent_steps: [str]
  confidence_and_limitations: str # e.g. cohort_n was small, or source data is from 2023
  disclaimer: str                 # fixed, always present — informational only, not an
                                   # LADBS determination, confirm directly with LADBS
  ```

### Orchestrator

A simple Python function/CLI, not a framework: `run(permit_number) →
Agent1 → Agent2 → Agent3 → DeveloperExplanation`, or a batch mode over a
permit list. Claude Code subagents or LangGraph-style orchestration are
unnecessary for this — the three contracts above are enough to keep the
stages independently testable and swappable (e.g. Agent 3 could later run
with or without an LLM without touching Agents 1–2).

## 6. MVP technology (unchanged from your directive)

Python + DuckDB, no Streamlit, no GitHub Actions, no external database, no
mandatory Socrata app token. The profiling in this document was done
entirely unauthenticated against small samples via `urllib` — the same
approach is fine for the Agent 1 prototype; add a token/caching layer only
if/when rate limits actually become a problem.

## 7. Open questions before Agent 1 implementation starts

1. **Source staleness**: both permit datasets are frozen as of 2023-05-19.
   Proceed with historical/frozen data for an MVP that demonstrates the
   pipeline end-to-end (defensible for validating the approach), or first
   look for a live-updating LADBS permit source before writing Agent 1?
   This should be a deliberate decision, not a default.
2. **Pre-issuance scope**: given neither dataset has submission/plan-check
   milestone data, should Agent 1's "journey" scope be formally narrowed to
   start at issuance (dropping that part of the PRD's original framing), or
   is finding a third data source for pre-issuance status worth
   investigating first?
3. **Permit-type scope**: confirm `xnhu-aczu`'s 3 building-permit types are
   the intended MVP scope, or whether `hbkd-qubn`'s full 18-type coverage
   (electrical/plumbing/etc.) should be included from the start.
4. **Follow-up profiling before Agent 2 is built**: (a) the ~19% forward-
   direction unmatched permits need characterization before "no inspection
   record" becomes a stall signal; (b) the in-window reverse-match rate
   (61%, n=77) should be re-measured on a larger sample; (c) full
   `inspection_result` value vocabulary needs enumerating to finalize the
   `signal_type` taxonomy in Agent 2.

Nothing in Agent 1/2/3 has been implemented. Waiting for your call on the
four items above (or a decision to proceed with stated defaults) before
writing code.

---

## 8. Update — `pi9x-tg5x` and its dataset family supersede §0–7

A fourth dataset (`pi9x-tg5x`, "Building and Safety - Building Permits
Issued from 2020 to Present (N)") was investigated on your request. It is
not a standalone dataset — it's one of **six datasets published as a
matched family**, all sharing the same 36-column schema and all updated in
the last 24 hours as of this report:

| ID | Name | Rows | `issue_date` null? |
|---|---|---|---|
| `e67z-kt2n` | Building Permits Issued Before 2010 (N) | 639,942 | 0 |
| `dyxf-7hc4` | Building Permits Issued Between 2010 and 2019 (N) | 533,367 | 0 |
| `pi9x-tg5x` | Building Permits Issued from 2020 to Present (N) | 405,688 | 0 |
| `b6ii-mhed` | Building Permits Submitted Before 2010 (N) | 342,331 | 49,761 (14.5%) |
| `n3xg-rixm` | Building Permits Submitted Between 2010 and 2019 (N) | 427,913 | 68,691 (16.1%) |
| `gwh9-jnip` | **Building Permits Submitted from 2020 to Present (N)** | 300,943 | **74,204 (24.7%)** |

All six: attribution `TSB`, created 2023-03-22, `rowsUpdatedAt` /
`refresh_time` = **2026-08-10** (yesterday relative to this report — live).
Both the "Issued" and "Submitted" datasets are bucketed by different date
fields (issue_date vs. submitted_date respectively) covering overlapping
but distinct permit populations — a permit submitted in 2019 and issued in
2021 appears in "Issued 2020-Present" but "Submitted 2010-2019," not
"Submitted 2020-Present." This explains the row-count differences between
siblings; it is not a data-quality gap.

### 8a. This is the answer to "does pre-issuance data exist?" — yes

The **Submitted** family is the one you asked me to look for. `gwh9-jnip`
alone has **74,204 rows (24.7%) with a null `issue_date`** — i.e., permits
submitted since 2020 that have never been issued, still sitting somewhere
in the process today. Its `status_desc` vocabulary (unlike the two-year-old
`xnhu-aczu`/`hbkd-qubn` pair, whose `latest_status` values were exclusively
post-issuance) includes genuine pre-issuance stages at meaningful volume:

```
Corrections Issued        14,356
Quality Review Completed  18,662
Verifications in Progress 16,566
PC Info Complete          12,781
PC Approved                7,576
PC Assigned                   518
PC in Progress                 232
Ready to Issue               1,077
Not Ready to Issue             192
Submitted                     465
Plans on Hold                 202
Re-Submittal Required            7
```

Concrete example pulled live: permit `21030-20000-00256` — `submitted_date`
2020-11-16, `status_desc` "PC Approved" as of `status_date` 2021-08-04,
`issue_date` still null as of this report's refresh (2026-08-09). That
permit has been sitting plan-check-approved but un-issued for roughly five
years — a genuine, non-inferred stall example, exactly the product's core
use case, sourced directly from the data rather than assumed.

**This reverses the §4 recommendation.** `submitted_date` is a real,
observed field (not inferred from `issue_date`), so Agent 1's scope does
**not** need to be narrowed to "issuance through inspections." The PRD's
original "submission through inspections" framing is achievable — with one
honest caveat below.

### 8b. The caveat: snapshot, not a log

`gwh9-jnip` (like every dataset investigated so far) is **one row per
permit** — row count equals distinct `permit_nbr` count exactly
(300,943 = 300,943, no duplicates, unlike the old pair). That means for a
permit already sitting in the pipeline, we get its **current** status and
the date it reached that status (`status_date`) — not the full sequence of
statuses it passed through to get there. We cannot retroactively see that
`21030-20000-00256` was, say, "PC Assigned" for three weeks in December
2020 and "PC in Progress" for two months after that — only that it's been
"PC Approved" since 2021-08-04.

For the MVP's actual need (Agent 2: "how long has this permit been in its
current state, relative to comparable permits?"), this is sufficient —
`elapsed_days = today − status_date` is a real, defensible calculation.
Full stage-by-stage transition timing only becomes available **prospectively**:
once Permit Stall Finder starts polling this dataset on a recurring cadence
and diffing `status_desc`/`status_date` per permit across pulls, it can
build its own transition log going forward. That's a real capability, just
not a retroactive one — worth designing Agent 1's storage layer to support
from day one (store each pull's snapshot, don't just overwrite) even though
the MVP won't have historical transitions to show at launch.

### 8c. Relationship to the datasets already validated in §1–3

- `pi9x-tg5x` ∩ `xnhu-aczu` = 159,940 permits (42.7% of `xnhu-aczu`, 39.4%
  of `pi9x-tg5x`); `pi9x-tg5x` ∩ `hbkd-qubn` = 198,726 (12.2% of
  `hbkd-qubn`). 51.0% of `pi9x-tg5x` is in *neither* older dataset — that's
  the post-May-2023 permit population the old pair structurally cannot
  contain.
- `pi9x-tg5x` → inspections (`9w5z-rg2h`) forward match rate: **1,150/1,500
  sampled permits = 76.7%** (same methodology as §3a: random sample,
  dash/space-normalized batched lookups). Comparable to `xnhu-aczu`'s
  80.7% — the join quality is a property of the inspections data and
  normalization, not of which permit source is used. Same open question as
  §3a applies: some `Permit Finaled`/`CofO Issued` permits in the unmatched
  set have zero inspection records, unexplained so far.
- `xnhu-aczu` and `hbkd-qubn` are now understood to be **deprecated legacy
  exports** — frozen since May 2023, fully superseded in content and
  currency by the "(N)" family for any permit issued or submitted since
  2013. There's no remaining reason to build on them.

### 8d. No dataset exposes genuine multi-event pre-issuance history

Catalog search (`api.us.socrata.com/api/catalog/v1?domains=data.lacity.org`)
for plan check / corrections / application status / case status / PCIS /
express permit / certificate of occupancy turned up one more relevant
dataset — `3f9m-afei` "Building and Safety Certificate of Occupancy," a
dedicated CofO dataset (redundant with `gwh9-jnip`'s `cofo_date` field for
this purpose) — and one aggregate KPI dataset, `c8jn-ua56` "DBS Performance
Plan Check Development Services Counter - Quarterly" (citywide % of plan
checks completed within 15 days, by quarter — useful later as a rough
external sanity check for Agent 2's cohort benchmarks, not permit-level and
not joinable by permit number). Nothing in the catalog exposes a permit-level
event log of individual corrections, plan-check assignments, or
resubmittals over time — `status_desc`/`status_date`'s single current value
is the most granular pre-issuance signal that exists publicly today.

### 8e. Revised canonical source recommendation

**Primary**: `gwh9-jnip` ("Submitted from 2020 to Present"), as the single
source for Agent 1's permit side. It already contains both issued and
not-yet-issued permits for that window (226,739 of its 300,943 rows have a
non-null `issue_date` — issued permits are a subset of it, not a separate
pull), so `pi9x-tg5x` doesn't need to be ingested separately.

**MVP date scope**: submitted 2020–present. This matches "developers and
contractors managing *active* projects" (the PRD's target user) better
than reaching back to pre-2010 permits, and keeps the ingestion volume
manageable (~301K rows vs. adding `n3xg-rixm` + `b6ii-mhed`'s combined
~770K). Extending backward later is a config change (add the two older
"Submitted" siblings), not a re-architecture.

**Permit-type scope**: `gwh9-jnip`'s `permit_group` is uniformly
`"Building"` and spans 12 permit types (the original 3 plus
Grading/Demolition/Sign/Swimming-Pool/Nonbldg-*/Relocation) — all excluding
electrical/plumbing/mechanical trade permits, which live in sibling
datasets (e.g. `ysqd-apz7`). This matches your stated preference for
building permits only, and is a materially broader "building permits"
definition than `xnhu-aczu`'s narrow 3-type scope, with no dataset-quality
reason to narrow it further.

**Inspections**: `9w5z-rg2h`, unchanged.

**Dropped entirely**: `xnhu-aczu`, `hbkd-qubn`, `pi9x-tg5x` (redundant with
`gwh9-jnip` for this date range) as ingestion sources — kept only as
background context in this document for why the "(N)" family is the right
call.

### 8f. Revised Agent 1 scope statement

Not narrowed. Restated precisely against what's actually observable:

> Agent 1 reconstructs each permit's journey from `submitted_date` (real,
> observed) through its current status (`status_desc`/`status_date`,
> single most-recent snapshot — not a full transition log), issuance
> (`issue_date`, if reached), inspection events (`9w5z-rg2h`, a genuine
> ordered sequence), and finalization/CofO (`cofo_date`, if reached).
> Stage-by-stage pre-issuance transition timing is not retroactively
> available from public data and will only accumulate once this tool
> begins polling `gwh9-jnip` on a recurring schedule and storing snapshots
> itself.

### 8g. Updated open questions

Items 1 and 2 from §7 are resolved (proceed with live "(N)" data; don't
narrow scope). Items 3 and 4 stand, plus:

5. Confirm the 2020-present date scope for MVP (vs. reaching back further
   immediately).
6. Decide now whether Agent 1's storage layer persists dated snapshots
   from day one (needed to ever build real transition history) even though
   the MVP won't have historical transitions to show — cheap to add now,
   expensive to retrofit later once only the "current" snapshot has ever
   been kept.

Still nothing implemented in Agent 1/2/3. Scripts for this section's
queries follow the same pattern as `scripts/` (stdlib `urllib`, same
normalization function) and were run ad hoc rather than saved as separate
files, given their similarity to the existing ones — recreate via the same
`pull_permit_ids.py`/`permit_to_inspection_match.py` pattern against
`gwh9-jnip`/`pi9x-tg5x` if you want them re-run.

---

## 9. Final join validation on the approved canonical source (`gwh9-jnip`)

Decisions locked in before this pass: MVP date scope 2020–present, canonical
permit source `gwh9-jnip`, canonical inspection source `9w5z-rg2h`, building
permits only. This validation restricts the match-rate analysis to permits
with a **non-null `issue_date`** — an unissued permit correctly has zero
inspections and must not be scored as a failed join.

### 9a. Normalization rule (confirmed, unchanged from §3)

```python
import re
def normalize_permit(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", s.upper())
```

Strip every non-alphanumeric character, uppercase, compare. `gwh9-jnip`'s
`permit_nbr` is consistently dash-separated (`"21030-20000-00256"`);
`9w5z-rg2h`'s `permit` field mixes dash- and space-separated values within
the same column. No other transformation is needed or was found necessary
— digit sequences align once separators are stripped.

### 9b. Permit → inspection match rate, issued permits only

Pulled the full population of `gwh9-jnip` permits with non-null
`issue_date` (226,739 of 300,943 rows — the "issued" subset of the
Submitted-family dataset). Drew a stratified random sample (~260 per issue
year, 2020–2026, n=1,820) and checked each directly against `9w5z-rg2h`
with both separator variants.

**Overall: 1,283 / 1,820 = 70.5%.**

By issue year:

```
2020: 78.1%    2023: 72.3%    2026: 48.5%  (recency — most 2026
2021: 76.5%    2024: 70.0%             permits haven't had time
2022: 76.9%    2025: 71.2%             to accumulate inspections yet)
```

2020–2025 cluster tightly (70–78%); 2026 is the outlier and is explained by
recency, not a join defect — those permits are, on average, only months
old.

By permit type:

```
Swimming-Pool/Spa    92.1%   Bldg-Demolition      78.9%
Nonbldg-Alter/Repair 63.2%   Grading              72.6%
Sign                 61.8%   Nonbldg-New          71.9%
Bldg-New             50.3%   Bldg-Alter/Repair    71.1%
                             Bldg-Addition        68.7%
```

**`Bldg-New` at 50.3% is the standout anomaly** and is only partly a
recency effect (55 of 78 unmatched `Bldg-New` sample permits are 2022+, but
23 are 2020–2021). Checked several of the older unmatched examples by hand
— they include `CofO Issued` and `Permit Finaled` new-construction permits
(new ADUs, a 4-story small-lot-subdivision dwelling) with **zero**
inspection records, which is surprising for new construction (normally
several required inspections: foundation, framing, rough electrical,
final). This is a genuine open question about inspections-dataset
completeness for certain permit types, not a join-logic problem — flagged
for Agent 2 design, not resolved here.

Other unmatched examples (2020 issue year, so not a recency artifact):

```
18010-20001-05038  Bldg-Alter/Repair
19010-20001-01584  Bldg-Alter/Repair
20047-20001-00556  Swimming-Pool/Spa
20016-10000-09361  Bldg-Alter/Repair
```

**Practical takeaway for Agent 2**: "zero inspection records" cannot be
treated as a clean stall signal on its own — roughly 30% of issued permits
show no inspection match for reasons that include both real data gaps and
recency, and the rate varies meaningfully by permit type. Agent 2 should
condition on permit age and permit type before interpreting a missing
inspection record as meaningful, and Agent 1 should carry `permit_type`
and `issue_date` alongside `match_status` so Agent 2 can make that call
rather than baking an assumption into Agent 1.

### 9c. Unissued permits by current status (pre-issuance stall candidates)

74,204 of `gwh9-jnip`'s 300,943 rows have `issue_date IS NULL`. Breakdown
by `status_desc` (full population, not a sample):

```
Quality Review Completed    18,662        Ready to Issue           1,076
Verifications in Progress   16,566        Reviewed by Supervisor     901
Corrections Issued          14,356        PC Assigned                518
PC Info Complete            12,780        Submitted                  465
PC Approved                  7,575        Submitted for Qual. Rev.   287
                                           No Progress                271
                                           PC in Progress             232
                                           Plans on Hold               202
                                           Not Ready to Issue          192
                                           other (<20 each)           ~90
```

None of these require an inspection record to be a valid, actionable
pre-issuance stall candidate — inspections only become relevant after
issuance. One data-quality wrinkle worth flagging: 23 rows (0.03% of the
unissued set) have `issue_date IS NULL` but a post-issuance `status_desc`
(`Issued` ×3, `CofO Issued` ×1, `Permit Finaled` ×19) — an internal
inconsistency in the source data. Small enough to not block anything, but
Agent 1 should flag these rather than silently trusting either field.

Agent 1 proceeds on this basis.
