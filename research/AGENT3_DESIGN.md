# Agent 3 — Developer Explainer: Design

Status: **design only, not approved for implementation.** No Agent 3 code
exists. Agents 1 and 2 are frozen/approved and treated here as read-only
inputs — this document never proposes recalculating anything they produce.

---

## 0. Source research (grounding requirement)

Before designing the knowledge base, I researched primary official sources
for the process meaning of each of Agent 2's 9 stall categories. Findings,
with an honest accounting of what is and isn't well-grounded:

### Confirmed official/primary sources

| Source | What it establishes |
|---|---|
| **LAMC §98.0602 "Expiration of Permits"** (Los Angeles Municipal Code, official codification, `codelibrary.amlegal.com`) | Permits are valid 24 months from issuance; a permit expires after 180 days if work has not commenced; **follow-up inspection must be requested at least every 180 days to keep a permit active**; extensions of 180 days available on written request. Retrieved via search synthesis — direct full-text fetch returned HTTP 403 (site blocks scraping); **flagged for direct-text verification before this exact wording ships in a live tool.** |
| **LAMC §106.4.4.3 "Project inactivity"** (same code library) | A project inactive for 180 days triggers a notice to the owner, with a 90-day window to obtain new permits before existing permits are affected. Same retrieval caveat as above. |
| **LADBS official glossary** (`dbs.lacity.gov`, the current domain — `ladbs.org` now 301-redirects here) | Fetched directly. Confirms: "C of O = Certificate of Occupancy," "G-49 = Correction notice," "PCIS = Plan Check and Inspection System." |
| **`dbs.lacity.gov/services/plan-review-permitting`** | Fetched directly. Defines the plan-review tracks: Counter Plan Check (simple projects), Expanded Counter Plan Check ("modest projects like multi-floor tenant improvements and medium-sized home additions"), Express Permits (simple, no plan check), Regular Plan Check (large/complex projects). **These map directly to real `business_unit` values already observed in our data** ("Regular Plan Check," "Express Permit," "Plan Check at Counter," "Expanded Counter Plan Check") — a genuine, confirmed connection between the dataset and official process terminology. |
| **`dbs.lacity.gov/services/homeowner-step-by-step`** | Fetched directly. Direct quote: *"You will need to schedule and pass inspections for each phase of the project before moving on to the next one."* Also covers scheduling windows (appointments requested one day ahead, weekday 7am–3:30pm, off-hours fees apply), required on-site documents (permit copy, approved plans, Building Card B-8), and the final-inspection/CofO process. |
| **LADBS plan-check correction-sheet materials** (`dbs.lacity.gov/sites/default/files/efs/forms/pc17/...`) | Confirm "Inspection Correction Notice" is the document issued when a field inspection finds items needing correction, and that the applicant is expected to contact the plan-check engineer for a **verification appointment** after addressing plan-check corrections. Found via search synthesis of official PDF forms, not a full direct fetch of one document — moderate-high confidence. |

### Explicitly NOT well-grounded (and treated that way in the KB, not papered over)

- **The distinct meaning of granular pre-issuance PCIS sub-statuses** (`Verifications in Progress`, `Quality Review Completed`, `PC Info Complete`, `PC Assigned`, `PC in Progress`) — I could not find official LADBS text defining each one distinctly. They are clearly internal plan-check workflow checkpoints, but I'm not confident enough in what differentiates them to write separate, specific explanations. **One generic, appropriately-hedged entry covers all pre-issuance statuses collectively** rather than fabricating per-status distinctions — see KB entry `pre_issuance.generic`.
- **Why a permit sits in `PC Approved`/`Ready to Issue` without being issued** — the only source I found suggesting "just fees remain" was a third-party permit-tracking startup's glossary page (`signedoff.io`), not LADBS or the City. Not used — I will not ground a knowledge-base entry in a non-official source for a project this explicit about primary-source grounding.
- **`Not Ready for Inspection` / `Insp Cancelled` (the two friction categories `REPEATED_NOT_READY_OUTCOMES`, `REPEATED_CANCELLATIONS`)** — every source I found describing causes was generic or from other jurisdictions (site-access issues, no-shows, re-inspection fee policies elsewhere), nothing LADBS-specific. **No knowledge-base entry.** Per your instruction, Agent 3 must say it cannot provide a reliable process interpretation for these two categories rather than borrow generic guidance and present it as LADBS-specific.

### Resulting coverage (9 Agent-2 categories)

| Category | KB coverage |
|---|---|
| `PRE_ISSUANCE_STATUS_DWELL` | Generic entry (all statuses), moderate confidence |
| `ISSUANCE_TO_FIRST_INSPECTION_GAP` | Grounded |
| `NO_INSPECTION_SINCE_ISSUANCE` | Grounded — strongest entry, ties directly to LAMC §98.0602 expiration risk |
| `INTER_INSPECTION_GAP` | Grounded |
| `INACTIVITY_SINCE_LAST_INSPECTION` | Grounded — strongest entry, same LAMC tie |
| `FINALIZATION_GAP` (COFO_TRACK only — FINALED_ONLY_TRACK isn't computed by Agent 2 at all) | Grounded |
| `REPEATED_CORRECTIONS` | Grounded |
| `REPEATED_NOT_READY_OUTCOMES` | **No entry — NO_ENTRY_AVAILABLE by design** |
| `REPEATED_CANCELLATIONS` | **No entry — NO_ENTRY_AVAILABLE by design** |

7 of 9 grounded, 2 deliberately not. This split is itself the main deliverable of the grounding requirement — it's meant to be uneven, not padded out to look complete.

---

## 1. Agent 3 input/output contract

**Input**: exactly Agent 2's `StallAssessment` — nothing else. Agent 3 does
not reach back into `PermitJourney` or re-touch raw source data; everything
it needs (evidence, cohort stats, caveats, cannot_infer, match_status) is
already carried on each `StallDetection`. This keeps the pipeline strictly
one-directional and means Agent 3 physically cannot recompute anything
Agent 2 already decided.

```python
def explain_assessment(
    assessment: StallAssessment,
    knowledge_base: KnowledgeBase,
    now: datetime | None = None,
) -> DeveloperExplanationSet:
    ...
```

**Output**:

```python
@dataclass(frozen=True)
class DeveloperExplanationSet:
    permit_number: str
    generated_at: datetime
    source_stall_assessment_generated_at: datetime  # provenance, mirrors Agent 1<->2 pattern

    explanations: list[DeveloperExplanation]  # one per StallDetection in the assessment
    coverage_gaps: list[str]                   # passed through from Agent 2 UNCHANGED --
                                                 # Agent 2's coverage_gaps messages are already
                                                 # plain-language and require no KB/LLM processing;
                                                 # re-touching them would risk paraphrasing away
                                                 # their precision
    disclaimer: str                             # fixed, permit-level, always present
```

One `DeveloperExplanation` per detection, not one per permit — a permit
with 4 detections (like `21010-10000-05865` in our real data) gets 4
independent explanations, matching Agent 2's own "never merge unrelated
signals into one score" principle.

---

## 2. Proposed explanation schema

```python
class GroundingStatus(str, Enum):
    GROUNDED = "grounded"                    # a matching KB entry was found and used
    NO_ENTRY_AVAILABLE = "no_entry_available"  # no matching KB entry -- must say so, never invent

@dataclass(frozen=True)
class DeveloperExplanation:
    permit_number: str
    stall_category: StallCategory
    generated_at: datetime

    # 1. WHAT THE DATA SHOWS -- built ONLY from StallDetection fields via a
    # deterministic renderer (fact_renderer.py), never from the KB or an LLM.
    what_the_data_shows: str

    # 2. WHAT THIS USUALLY MEANS -- built ONLY from a KnowledgeBaseEntry.
    # Structurally cannot reference this permit's specific numbers (see §4).
    what_this_usually_means: str
    grounding_status: GroundingStatus
    knowledge_base_entry_id: str | None      # None iff NO_ENTRY_AVAILABLE

    # 3 & 4. Next steps -- verbatim from the KB entry, empty list (not
    # invented filler) when grounding_status is NO_ENTRY_AVAILABLE.
    developer_actionable_steps: list[str]
    city_dependent_steps: list[str]

    # 5. LIMITATIONS -- deterministic passthrough of Agent 2's own fields,
    # plus KB-level caveats when an entry was used.
    limitations: list[str]                    # detection.caveats + detection.cannot_infer
                                                # + kb_entry.caveats (if grounded)

    disclaimer: str                            # fixed text, identical across every explanation

    # Traceability
    source_detection_category: StallCategory
    source_detection_severity: Severity
    source_percentile_rank: float | None
    kb_entry_version: str | None
    kb_entry_last_reviewed: date | None
```

`what_this_usually_means` is a single string, not a further-nested object —
the separation between "general process" (section 2) and "this permit's
facts" (section 1) is enforced structurally by *where the content comes
from* (§4), not by extra schema nesting. A KB entry's `explanation` string
is a fixed constant with no interpolation slots for permit-specific values,
so there is no code path that could let a number from section 1 leak into
section 2's prose.

---

## 3. Knowledge-base schema

Every field your instructions listed, plus a confidence/versioning layer
consistent with how this project has treated every other empirically-seeded
constant (coverage thresholds, severity bands, vocabulary mappings):

```python
class SourceType(str, Enum):
    PRIMARY_MUNICIPAL_CODE = "primary_municipal_code"   # LAMC sections
    PRIMARY_OFFICIAL_AGENCY = "primary_official_agency"  # dbs.lacity.gov pages/forms
    SECONDARY_UNVERIFIED = "secondary_unverified"        # not used in any shipped entry (see §0)

class KBConfidence(str, Enum):
    VERIFIED_DIRECT_FETCH = "verified_direct_fetch"        # page/doc content read directly
    VERIFIED_SEARCH_SYNTHESIS = "verified_search_synthesis"  # sourced but not a full direct fetch;
                                                               # flagged for follow-up verification
    GENERIC_LOW_CONFIDENCE = "generic_low_confidence"        # collapses several unclear sub-cases
                                                               # into one hedged entry (e.g. pre-issuance)

@dataclass(frozen=True)
class KnowledgeBaseSource:
    title: str
    url: str
    publisher: str              # "Los Angeles Department of Building and Safety" | "Los Angeles Municipal Code"
    source_type: SourceType
    retrieved_date: date

@dataclass(frozen=True)
class KnowledgeBaseEntry:
    entry_id: str                          # stable id, e.g. "no_inspection_since_issuance.generic"
    stall_category: StallCategory
    applies_to_dimension: str              # "status_desc" | "result_family" | "track" | "category_generic"
    applies_to_value: str | None           # e.g. "Corrections Issued", or None for category-generic

    explanation: str                       # section 2 content -- general process meaning only,
                                            # no permit-specific interpolation slots, ever
    developer_actionable_steps: list[str]
    city_dependent_steps: list[str]

    sources: list[KnowledgeBaseSource]     # never empty for a GROUNDED entry
    caveats: list[str]                     # KB-level caveats (distinct from a detection's own caveats)
    confidence: KBConfidence

    kb_version: str                        # semver-style, bumped on any content change
    last_reviewed: date
```

**Lookup key** = `(stall_category, applies_to_dimension, applies_to_value)`,
falling back to `(stall_category, "category_generic", None)` if a more
specific key isn't found (e.g. a `status_desc` not individually covered
still gets the category's generic entry, if one exists — this is how
`PRE_ISSUANCE_STATUS_DWELL`'s single generic entry covers every
`status_desc` value uniformly). If neither the specific nor the generic key
exists (the `REPEATED_NOT_READY_OUTCOMES` / `REPEATED_CANCELLATIONS` case),
lookup returns `None` and `grounding_status` becomes `NO_ENTRY_AVAILABLE`.

Stored as a versioned JSON file (`research/agent3_knowledge_base.json`),
same pattern as the two Agent 2 vocabulary mapping files — a `metadata`
block plus a list of entries, auditable and diffable independent of code.

---

## 4. Grounding rules

1. **Section 1 is a pure function of `StallDetection` fields.** `fact_
   renderer.py::render_what_the_data_shows(detection)` reads only
   `elapsed_days`/`observed_count`, `percentile_rank`, `cohort.n`,
   `cohort.benchmark_semantics`, `interval_state`, and `evidence` —
   no knowledge base, no LLM, no free text. This extends Agent 2's existing
   `render_dwell_statement()` pattern to every category, not just
   `PRE_ISSUANCE_STATUS_DWELL`.

2. **Sections 2–4 come only from a `KnowledgeBaseEntry` lookup.** No LLM
   call originates this content in the MVP design — see §5. If no entry
   matches, the fixed fallback text is used verbatim (below), never a
   best-guess paraphrase of nearby entries.

3. **A KB entry's `explanation` string contains no permit-specific
   interpolation points.** It is written once as a general-process
   statement and reused identically for every permit that hits that
   category/status — enforced by the schema (plain `str`, not an f-string
   template) and checked by a test that scans every KB entry for
   number-like patterns that would suggest a permit-specific value crept
   in (§7).

4. **Every `GROUNDED` entry carries at least one `KnowledgeBaseSource`.**
   No entry ships without a citation; `KBConfidence.GENERIC_LOW_CONFIDENCE`
   entries (currently just `pre_issuance.generic`) still cite the sources
   that informed the hedge, just carry a caveat about their generality.

5. **Section 5 is a deterministic passthrough**, never re-summarized:
   `limitations = detection.caveats + detection.cannot_infer + (kb_entry.
   caveats if grounded else [])`.

6. **The disclaimer is fixed, permit-level, and always present** —
   identical text on every `DeveloperExplanation`, not generated:
   > "This explanation is informational only and is not an official
   > determination by the Los Angeles Department of Building and Safety
   > (LADBS). Confirm current status directly with LADBS."

7. **Benchmark-semantics and interval-state rules from Agent 2 carry
   forward into section 1's renderer** (this is the same mechanism as
   `render_dwell_statement`, generalized):
   - `benchmark_semantics == ACTIVE_PEER_DWELL` → the only legal phrasing
     is "longer than X% of permits *currently observed* in this status" —
     never "typically takes," "normally completes in," or any phrase
     implying an estimate of normal completion time.
   - `benchmark_semantics == COMPLETED_INTERVAL` → may use "ranked at
     approximately the Nth percentile of M comparable completed
     intervals" — this cohort's intervals concluded, so a comparison
     against *typical* completed duration is licensed.
   - `interval_state == ONGOING` → the renderer never states or implies a
     final/total duration; only "elapsed so far."

**Fixed fallback text for `NO_ENTRY_AVAILABLE`**:
> "No approved knowledge-base entry exists for this stall pattern. This
> tool cannot currently provide a reliable general-process interpretation
> for it. [Section 1 facts are still shown above.] Consider contacting
> LADBS directly about this permit's status."
`developer_actionable_steps` and `city_dependent_steps` are both empty
lists in this case — not filled with generic filler.

---

## 5. Hallucination safeguards

- **No LLM in the MVP.** Sections 1–5 are all produced by deterministic
  Python (a fact renderer + a KB lookup + list concatenation). This is the
  safest starting point and matches what was recommended (and not
  contested) during Agent 2's design. An LLM-phrasing layer — restyling
  the deterministic output into more natural prose without changing its
  factual content — is a plausible phase-2 enhancement, explicitly **not
  designed in detail here**; if pursued later it would need its own
  no-new-facts validation pass (e.g., diffing the LLM output's factual
  tokens against the deterministic source), which doesn't exist yet.
- **Structural separation, not instructional separation.** Section 2 can't
  drift into permit-specific claims because its content literally comes
  from a different object (`KnowledgeBaseEntry`, not `StallDetection`) than
  section 1's. There's no shared prompt or generation step where the two
  could blend.
- **Missing-entry is a first-class state, not an error path bolted on.**
  `GroundingStatus.NO_ENTRY_AVAILABLE` is checked and tested like any other
  enum value, and every `explain_assessment` call that hits it still
  returns a well-formed `DeveloperExplanation` (with the fixed fallback
  text) rather than raising or silently omitting the detection.
- **Automated phrase scanning for the two benchmark-semantics rules**,
  mirroring what already exists in Agent 2's test suite for
  `render_dwell_statement`: a test asserts that no `ACTIVE_PEER_DWELL`
  output contains banned phrases ("normally takes," "typically completes
  in," "usually finished within," "expected to take"), and no `ONGOING`
  output contains banned duration-completion phrases ("will take," "should
  be done by," "total of," implying a known endpoint).
- **KB entries are auditable to source.** Every `GROUNDED` explanation
  carries `knowledge_base_entry_id` + `kb_entry_version` +
  `kb_entry_last_reviewed`, so any explanation shown to a developer can be
  traced back to the exact KB entry, its sources, and when it was last
  reviewed — same traceability ethos as Agent 1's snapshot provenance and
  Agent 2's evidence refs.
- **No entry ships without a citation** (grounding rule 4) — enforced by a
  test that fails the whole KB load if any entry has `sources == []`.

---

## 6. Example output for each major category

All using real numbers from the six permits already demonstrated against
Agent 2, except where noted as hypothetical (clearly labeled).

### `INTER_INSPECTION_GAP` — grounded, COMPLETED_INTERVAL (real: `21016-20000-20141`)

```
what_the_data_shows:
  "There were 84 days between these two recorded inspections
   ('BUILDING-Rough-Frame' Approved on 2021-09-15, then 'Smoke Detectors'
   Approved on 2021-12-08). This interval ranked at approximately the 97th
   percentile of 566 comparable completed inspection intervals for this
   permit type."

what_this_usually_means (grounded):
  "LADBS expects a permit holder to schedule and pass inspections for each
   phase of a project before moving on to the next one. A long gap between
   recorded inspections can occur when construction work between phases is
   slower than typical, when the next inspection hasn't been requested yet,
   or for reasons not visible in this data."
  grounding_status: GROUNDED
  knowledge_base_entry_id: "inter_inspection_gap.generic"

developer_actionable_steps:
  - "If the next phase of work is ready, request the next inspection through LADBS's inspection request service."
  - "Confirm the permit and approved plans are available on-site, as required for each inspection."

city_dependent_steps:
  - "Inspection scheduling and availability are managed by LADBS; scheduling windows and any backlog are outside the applicant's control."

limitations:
  - "Which party (applicant, contractor, or LADBS) is responsible for this gap cannot be determined from this data."
  - "Why this specific permit has not progressed further cannot be determined from this data -- this tool observes elapsed time and counts, not cause."

disclaimer: "This explanation is informational only and is not an official
             determination by the Los Angeles Department of Building and
             Safety (LADBS). Confirm current status directly with LADBS."
```

### `REPEATED_CORRECTIONS` — grounded, friction (real: `21010-10000-05865`)

```
what_the_data_shows:
  "17 of 62 recorded substantive inspections on this permit resulted in a
   corrections-related outcome (27.4%). This count ranked at approximately
   the 99th percentile of 76 comparable completed permits."

what_this_usually_means (grounded):
  "LADBS issues an Inspection Correction Notice when a site inspection
   finds items that need to be fixed before the work can be approved.
   Repeated correction cycles are generally associated with recurring
   compliance issues that take more than one inspection visit to resolve."
  knowledge_base_entry_id: "repeated_corrections.generic"

developer_actionable_steps:
  - "Review each Inspection Correction Notice with the contractor/tradesperson responsible for that item before requesting reinspection."
  - "Contact the plan check engineer for a verification appointment once corrections are addressed, per LADBS's standard correction process."

city_dependent_steps:
  - "Reinspection to confirm a correction has been resolved requires LADBS to visit the site again."

limitations:
  - "Which party is responsible for these outcomes cannot be determined from this data."
  - "Whether these outcomes reflect scheduling/access issues, technical compliance issues, or something else cannot be determined from the result label alone."
```

### `NO_INSPECTION_SINCE_ISSUANCE` — grounded, ONGOING (hypothetical: no real permit currently fires this after the Agent 2 fixes)

```
what_the_data_shows:
  "620 days have elapsed since issuance with no inspection record found.
   This is longer than 91% of comparable completed issuance-to-first-
   inspection intervals for this permit type. This interval is still open
   -- the eventual total, if any, is not yet known."

what_this_usually_means (grounded):
  "Under LAMC Sec. 98.0602, a follow-up inspection must generally be
   requested at least every 180 days to keep a permit active; a permit
   left without inspection activity risks expiration, and a project
   inactive for an extended period can trigger a formal inactivity notice
   under LAMC Sec. 106.4.4.3."
  knowledge_base_entry_id: "no_inspection_since_issuance.generic"

developer_actionable_steps:
  - "Request an inspection soon, even a partial/preliminary one, to keep the permit active and avoid expiration risk under LAMC Sec. 98.0602."
  - "If work has not started, consider whether an extension request is needed before the permit's 180-day/24-month validity window lapses."

city_dependent_steps:
  - "LADBS determines whether a permit has technically expired or is subject to the inactivity-notice process."

limitations:
  - "Whether this permit genuinely requires an inspection at all cannot be determined from this data (some permits legitimately need none)."
  - "LAMC Sec. 98.0602/106.4.4.3 citations were retrieved via search synthesis, not a full direct-text fetch -- recommended to verify exact current wording before relying on this for a specific compliance deadline."
```

### `PRE_ISSUANCE_STATUS_DWELL` — generic/low-confidence, ACTIVE_PEER_DWELL (hypothetical elapsed value on real cohort shape from `21030-20000-00256`)

```
what_the_data_shows:
  "2,200 days have elapsed since the published 'PC Approved' status_date
   (2021-08-04). This elapsed time is longer than approximately 92% of
   currently observed comparable permits with the same published status."
   [Note: 21030-20000-00256's actual elapsed value (1,833 days) ranked at
   the 74.6th percentile and did not clear Agent 2's reporting threshold --
   this example uses a hypothetical larger value on the same real cohort
   shape (n=1,652, Grading/PC Approved) purely to illustrate the template.]

what_this_usually_means (grounded, low confidence):
  "This status reflects a checkpoint in LADBS's plan check process (see
   dbs.lacity.gov/services/plan-review-permitting for the different review
   tracks). Publicly available sources do not clearly document what
   specifically causes a permit to remain in this particular status for an
   extended time before issuance."
  knowledge_base_entry_id: "pre_issuance.generic"
  confidence: GENERIC_LOW_CONFIDENCE

developer_actionable_steps:
  - "Contact LADBS or the assigned plan check engineer to ask what is needed to move this permit toward issuance."

city_dependent_steps:
  - "Advancing a permit past plan check review is a LADBS-side action."

limitations:
  - "This elapsed time is compared against permits currently sitting in the same status (an active-peer cohort), not permits whose time in this status has already concluded -- see caveats on the underlying detection. It does not estimate normal or expected completion time for this stage."
  - "This permit was observed in this status on a single occasion; continuous residence in this status is not confirmed by repeated observation." [when applicable]
```

### `REPEATED_CANCELLATIONS` — **NO_ENTRY_AVAILABLE** (real: `21010-10000-05865`, WATCH severity)

```
what_the_data_shows:
  "5 of 62 recorded substantive inspections on this permit resulted in a
   cancelled-related outcome (8.1%). This count ranked at approximately
   the 76th percentile of 76 comparable completed permits."

what_this_usually_means:
  "No approved knowledge-base entry exists for this stall pattern. This
   tool cannot currently provide a reliable general-process interpretation
   for it. Consider contacting LADBS directly about this permit's status."
  grounding_status: NO_ENTRY_AVAILABLE
  knowledge_base_entry_id: null

developer_actionable_steps: []
city_dependent_steps: []

limitations:
  - "Which party is responsible for these outcomes cannot be determined from this data."
  - "Whether these outcomes reflect scheduling/access issues, technical compliance issues, or something else cannot be determined from the result label alone."
```

---

## 7. Proposed implementation files (not yet created)

```
src/permit_stall_finder/
  schema/
    developer_explanation.py    # DeveloperExplanation, DeveloperExplanationSet,
                                 # GroundingStatus, KnowledgeBaseEntry, KnowledgeBaseSource,
                                 # SourceType, KBConfidence
  knowledge_base/
    __init__.py
    loader.py                   # loads + validates research/agent3_knowledge_base.json,
                                 # lookup(category, dimension, value) -> KnowledgeBaseEntry | None,
                                 # with generic-entry fallback (§3)
  rendering/
    fact_renderer.py            # render_what_the_data_shows(detection) -> str;
                                 # extends Agent 2's render_dwell_statement to all 9 categories;
                                 # enforces the benchmark_semantics / interval_state phrasing rules
  agents/
    developer_explainer.py      # Agent 3 entry point: explain_assessment(), explain_detection()
  cli.py                         # extend with an `explain` subcommand (Agent 1 + 2 + 3 pipeline)
research/
  agent3_knowledge_base.json    # the versioned KB data file (metadata + entries)
  AGENT3_DESIGN.md              # this document
tests/
  test_fact_renderer.py         # deterministic rendering, all 9 categories, both benchmark
                                 # semantics, both interval states
  test_knowledge_base.py        # every entry has required fields + >=1 source; lookup
                                 # fallback to generic; unknown category/status -> None
  test_developer_explainer.py   # end-to-end per category incl. the two NO_ENTRY_AVAILABLE cases;
                                 # passthrough of coverage_gaps and caveats/cannot_infer
  test_agent3_grounding_safeguards.py  # banned-phrase scanners for both benchmark_semantics
                                 # values and both interval_states; KB explanation strings
                                 # contain no permit-specific-looking interpolated values
```

---

## 8. Validation / test plan

1. **Grounding-safeguard tests** (§5) — banned-phrase scanning for
   `ACTIVE_PEER_DWELL` (no "normally take"/"typically completes"/"usually
   finished"/"expected to take") and for `ONGOING` (no "will take"/"should
   be done by"/implied known total).
2. **KB schema/completeness tests** — every entry has `stall_category`,
   `applies_to_dimension`, `explanation`, `sources` (non-empty for
   `GROUNDED`/`VERIFIED_*` confidence), `caveats`, `kb_version`,
   `last_reviewed`; entry lookup by exact key and by generic-fallback key
   both resolve correctly; an unmapped category/status combination resolves
   to `None`, not a guess.
3. **Missing-entry fallback test** — `REPEATED_NOT_READY_OUTCOMES` and
   `REPEATED_CANCELLATIONS` (and any synthetic category with no entry)
   produce `GroundingStatus.NO_ENTRY_AVAILABLE`, the fixed fallback text,
   and empty step lists — never fabricated guidance.
4. **No-interpolation test** — every KB `explanation`/step string is
   scanned for patterns that look like a specific date, percentile, or
   count (e.g. `\d+%`, `\d{4}-\d{2}-\d{2}`, "days" preceded by a number) —
   none should match, since KB text must never carry permit-specific
   values.
5. **Disclaimer-always-present test** — every `DeveloperExplanation` (incl.
   `NO_ENTRY_AVAILABLE` ones) has a non-empty `disclaimer` containing both
   "informational" and "LADBS."
6. **Passthrough tests** — a synthetic `StallDetection`'s `caveats` and
   `cannot_infer` appear verbatim in the resulting explanation's
   `limitations`; a `StallAssessment`'s `coverage_gaps` appear verbatim
   (unmodified) in `DeveloperExplanationSet.coverage_gaps`.
7. **Face-validity walkthrough against the 6 already-demonstrated real
   permits** — reuse the actual Agent 2 JSON output already captured (no
   new live queries needed) and confirm, by hand, that every real
   detection from that run produces a sensible `DeveloperExplanation`:
   `21016-20000-20141`'s `inter_inspection_gap` (grounded), `21010-
   10000-05865`'s four detections (three grounded, one — `repeated_
   cancellations` — `NO_ENTRY_AVAILABLE`), `20010-20000-02739`'s three
   detections (all grounded), and confirm the two permits with zero
   detections (`21030-20000-00256`, `18010-20001-05038`, `23014-
   20000-02923`) correctly produce an empty `explanations` list with their
   real `coverage_gaps` passed through unchanged.
8. **Benchmark-semantics coverage** — at least one test per (category ×
   benchmark_semantics × interval_state) combination that actually occurs
   in the 9-category taxonomy, not just the two illustrated in §6.

---

## 9. Pre-implementation verification pass (KB v0.2.0)

Before coding, made three more targeted attempts to directly verify the two
LAMC citations flagged in §0 as "search synthesis, not a full direct fetch."
`codelibrary.amlegal.com` blocked all three attempts (HTTP 403). A more
targeted search did surface a longer, quote-like passage for **§98.0602**
that turned out to **correct** the original entry rather than just confirm
it: the real figures are **2-year total validity, 12-month expiration if
work hasn't commenced, and 12-month continuous-abandonment expiration** —
not the "180 days" figure originally in KB v0.1.0-draft (likely conflated
with a different jurisdiction's default ICC/IBC period). **§106.4.4.3**
("project inactivity, 90-day cure window") could not be confirmed at all on
a second attempt — it wasn't present in the LABC administration chapter
fetched from `up.codes`, and no independent source confirmed it. **Dropped
from the KB entirely** rather than shipped as an unconfirmed specific legal
claim — see the KB file's `metadata.revision_notes` for the full account.

Also added per your four pre-coding requirements:

- **`verification_status` on every source** (`direct_primary_fetch` /
  `search_synthesis_detailed` / `search_synthesis_general` / `unverified`) —
  a source-level field, since confidence varies per citation even within
  one entry (e.g. `finalization_gap.cofo_track` now cites two sources, both
  directly fetched; `no_inspection_since_issuance.generic` cites one,
  search-synthesized).
- **A specifically-keyed entry**, `pre_issuance.corrections_issued`
  (`status_desc = "Corrections Issued"`), added alongside the
  category-generic `pre_issuance.generic` entry — demonstrates specific
  lookup taking precedence over category-only matching, backed by real
  grounding (the same G-49/verification-appointment sources already used
  for `repeated_corrections.generic`), not just illustrative padding.
- **`grounding_strength` per next-step** (`directly_supported` /
  `cautious_synthesis` / `not_available`), not one blanket label per entry —
  e.g. in `no_inspection_since_issuance.generic`, "the permit may expire 12
  months after issuance" is `directly_supported` (the code says this
  outright) while "consider starting inspectable work... before that window
  closes" is the synthesized action built on top of it.
- **Blame/causality/responsibility language is now a designed-against
  safeguard** (§5's hallucination-safeguards list gains a banned-phrase
  scanner for terms like "failed to," "non-compliant," "violation," "at
  fault," "should have" — implemented as `assert_no_blame_language()`
  alongside the existing benchmark-semantics scanners), and every KB entry
  was reviewed against it — none currently contain blame language, and
  `repeated_corrections.generic` gained an explicit caveat that a high
  count is a statistical outlier, not a non-compliance determination.

KB now at v0.2.0 (`research/agent3_knowledge_base.json`), 8 entries (was 7).

---

Design approved with the above verification pass folded in. Proceeding to
implementation.
