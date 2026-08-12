# Permit Stall Finder — MVP UI Design

Status: **design only, not approved for implementation.** No UI code exists.
Agents 1–3 and the orchestrator are frozen; this document proposes a thin
Streamlit presentation layer over `orchestration.pipeline.run_pipeline()`
and identifies where a careless UI choice could misrepresent output that
Agents 1–3 already worked hard to keep honest.

---

## 1. File structure

Deliberately outside `src/permit_stall_finder/` — a UI is a *consumer* of
the installed package, not a member of it. This is a stronger separation
than a UI subpackage would give, and avoids any name collision with the
existing `rendering/` package (Agent 3's internal fact-rendering module —
unrelated to this UI layer despite the similar-sounding name).

```
app/
  streamlit_app.py       # entrypoint: st.set_page_config, header, input
                          # form, calls the orchestrator, dispatches to
                          # section renderers below
  sections/
    __init__.py
    top_level_result.py   # B
    permit_journey.py     # C
    stall_findings.py     # D + E (one card per finding contains both --
                           # E is nested inside D per your own spec)
    coverage_gaps.py      # F
    disclaimer.py         # G
  formatting.py           # shared presentation helpers: severity badge
                           # color/icon, ordinal-safe day/date phrasing,
                           # fixed short labels for enums (MatchStatus,
                           # DataQualityFlag, BenchmarkSemantics, ...)
  errors.py                # maps PipelineExecutionError / bad input to a
                            # user-safe message; never surfaces a
                            # traceback or a file path
  db.py                     # st.cache_resource-wrapped storage.db.connect()
                             # -- plumbing so the DuckDB connection survives
                             # Streamlit's rerun-the-whole-script model,
                             # not new analytical logic
```

`pyproject.toml` gains one new dependency: `streamlit`. Nothing else.

Every `sections/*.py` function takes a slice of `PermitAnalysisResult` (or
the whole object) and calls `st.*` — no function in `app/` calls into
`analysis/`, `knowledge_base/`, or recomputes anything Agents 1–3 already
computed, with one narrow, explicitly-flagged exception (§3, decision 5).

---

## 2. Field mapping: `PermitAnalysisResult` → interface

### A. Header
Static text (title + description you specified verbatim) + `st.text_input`
+ `st.button("Analyse Permit")`. No result field involved — this is the
pre-analysis state.

### B. Top-level result
| Source | Display |
|---|---|
| `result.outcome == NO_MATERIAL_STALL_DETECTED` | "No material stall signals identified" |
| `result.outcome == INSUFFICIENT_EVIDENCE` | "Insufficient evidence to reliably assess this permit" |
| `result.outcome == STALL_DETECTED` | `"{n} severe finding(s) · {m} elevated finding(s) · {k} watch finding(s)"` (zero-count tiers omitted), built by **counting** `result.stall_assessment.detections` by `.severity` — see decision 8, §3 |

Visual treatment is **the same neutral tone regardless of outcome** —
differentiated by icon and text only, never by red/green banner color at
this level (see decision 3, §3). Severity color-coding lives at the
finding-card level (section D), not here.

### C. Permit journey
All from `result.journey` (Agent 1's `PermitJourney`), split into three
visually distinct groups matching your OBSERVED / DERIVED / NOT-OBSERVED
requirement:

| Group | Source fields | Display |
|---|---|---|
| **Observed milestones** | `journey.latest_snapshot.{submitted_date, status_desc, status_date, issue_date, cofo_date}` | Discrete labeled points, e.g. "Submitted — 2020-11-16", "Current status: PC Approved (as of 2021-08-04)", "Issued — 2021-09-13" (only shown if the date exists — a `None` issue_date means no "Issued" point is rendered at all, not a greyed-out placeholder implying it's coming) |
| **Observed inspection events** | `journey.inspection_events[]` (`.inspection_date, .inspection_type, .inspection_result`) | Chronological table/list, already ordered by Agent 1 |
| **Derived elapsed-time metrics** | `journey.derived.{days_submitted_to_issuance, days_issuance_to_first_inspection, days_between_inspections, total_observed_elapsed_days}` | A visually separate "derived" box — each is `None`-safe (only rendered where Agent 1 actually computed it) |
| **Not observed** | `journey.not_observed_notes[]` | Its own labeled subsection, always shown when non-empty, verbatim strings — this is the section most directly protecting against the "fabricated intermediate stages" risk (decision 1, §3) |

`journey.reconstruction_notes` and `journey.source_provenance` go in a
small `st.expander("Technical details")` at the bottom of this section —
useful for a live demo audience who asks "where does this come from," not
needed for the main read.

### D. Stall findings + E. Developer explanation (one card per detection)

`result.stall_assessment.detections` and `result.developer_explanations.
explanations` are zipped 1:1 — Agent 3 guarantees same length, same order
(`explain_assessment` builds its list by iterating `assessment.detections`
directly). Per card:

**From the detection** (`DelayStallDetection` or `FrictionStallDetection`):

| Field | Display |
|---|---|
| `.category` | Fixed short label per `StallCategory` value (e.g. `inter_inspection_gap` → "Gap between inspections") — a presentation-only rename table, twelve fixed strings, no interpretation added |
| `.severity` | Badge: WATCH / ELEVATED / SEVERE, muted palette (no pure red — see decision 3) |
| `.elapsed_days` or `.observed_count` | Plain numeric fact, labeled by category |
| `.percentile_rank` | Shown as a **raw number** in a small metrics row ("Percentile rank: 97.6"), never re-narrated into a new sentence (decision 2) |
| `.cohort.n` | "Cohort size: 566 comparable permits" |
| `.cohort.benchmark_semantics` | Fixed badge: "Compared to: permits currently in this status" (ACTIVE_PEER_DWELL) vs. "Compared to: completed comparable intervals" (COMPLETED_INTERVAL) — preserves the distinction Agent 2/3 were built to protect |
| `.interval_state` | "Still ongoing" (ONGOING) vs. "Completed interval" (COMPLETED) small tag |

**From the explanation** (`DeveloperExplanation`), Agent 3's five sections
rendered **verbatim**, no UI-composed sentences:

1. **What the data shows** — `explanation.what_the_data_shows`, Agent 3's
   exact, safeguard-tested string.
2. **What this usually means** — `explanation.what_this_usually_means`.
   When `grounding_status == NO_ENTRY_AVAILABLE`: see decision 6, §3 for
   exactly how your specified sentence and Agent 3's own fallback text
   both appear.
3. **What you can do** — `explanation.developer_actionable_steps[]`
   (`.text` per `NextStep`); empty list → explicit "No developer-
   actionable guidance is available for this specific pattern," never a
   blank gap (decision 4).
4. **What depends on LADBS / the City** — `explanation.city_dependent_
   steps[]`, same empty-state handling.
5. **Limitations / what we cannot tell** — `explanation.limitations[]`,
   bulleted, always shown (Agent 2's `cannot_infer` guarantees this is
   never actually empty in practice).

Always shown per card, small text: `explanation.disclaimer` — actually
identical across every card since it's a fixed constant; see §3 decision
9 on whether to repeat it per-card or only once (section G).

**Expandable "Source & grounding"** (`st.expander`, collapsed by default):
`knowledge_base_entry_id`, `kb_entry_version`, `kb_entry_last_reviewed`,
plus the *resolved* KB entry's `sources[]` (title, url, publisher,
`verification_status`) — see decision 5, §3 for why this needs one
read-only lookup the UI performs itself.

Where a permit has both grounded and `NO_ENTRY_AVAILABLE` findings, one
line above the findings list, exactly as you specified: *"Some findings
have more detailed guidance because authoritative LADBS guidance was
available for those patterns."* — shown once per permit (computed by
checking whether `grounding_status` varies across `explanations`), not
repeated per card.

### F. Coverage / data-quality gaps
| Source | Display |
|---|---|
| `result.coverage_gaps[]` | Agent 2's own already-worded messages, shown verbatim, bulleted |
| `result.data_quality_flags[]` | Fixed short caption per `DataQualityFlag` value (three currently exist: `FIRST_OBSERVATION`, `STATUS_ISSUE_DATE_INCONSISTENT`, `INSPECTION_MATCH_UNCERTAIN_FOR_TYPE`), each paraphrased directly from that flag's own docstring — no new claims |

Shown only when either list is non-empty. Its own bordered/neutral-colored
section, physically separate from section B, with a fixed intro sentence
matching your instruction: *"The following signals could not be reliably
assessed due to limited or uncertain underlying data — this is not the
same as confirming there is no issue."*

### G. Disclaimer
`result.developer_explanations.disclaimer` — the fixed Agent 3 constant,
shown once, prominently, non-collapsible, at the page bottom.

---

## 3. Presentation decisions that could misrepresent the result

Nine, in descending order of how directly they touch analytical integrity:

1. **A visual "progress stepper"** (Submitted ✓ → Plan Check ✓ → Approved
   ✓ → Issued ✓, wizard-style) would fabricate exactly the intermediate
   pre-issuance events Agent 1 explicitly refuses to invent. **Decision:
   don't build one.** Section C renders only discretely-observed points;
   `not_observed_notes` stays visible, not hidden in an expander.

2. **Composing new sentences from raw numbers** (writing my own "this
   permit waited longer than most" from `percentile_rank`) risks
   reintroducing exactly the language bugs Agent 2/3's safeguard scanners
   exist to prevent — a hand-written UI sentence isn't covered by
   `rendering/safeguards.py`. **Decision: always render `what_the_data_
   shows` verbatim for narrative text; raw numbers/enums only appear in
   a structured metrics row, never re-narrated.**

3. **Severity color choices.** Red/error styling on a SEVERE badge, or a
   green success banner spanning the whole page when a stall exists,
   reads as an alarm or a compliance verdict — exactly what Agent 2/3
   were designed to avoid implying. **Decision: neutral top-level banner
   regardless of outcome (icon/text differ, color doesn't); a muted,
   non-red severity palette at the card level only; the "statistical
   tier" framing from Agent 3's own text stays visible next to the
   badge.**

4. **Empty step lists on `NO_ENTRY_AVAILABLE`** could look like a broken
   or half-loaded UI rather than a deliberate, honest state. **Decision:
   explicit placeholder text in that case, matching your instruction not
   to make the UI "look broken."**

5. **Full source citations aren't on `DeveloperExplanation`.** The schema
   only carries `knowledge_base_entry_id` (by design — Agent 3 doesn't
   duplicate the KB's own data). To show `sources[]` (url, publisher,
   `verification_status`) in the expandable grounding section, the UI
   must look the entry up by id against the same `KnowledgeBase` object
   Agent 3 already used (`knowledge_base.loader.default_knowledge_base()`
   — read-only, no re-deciding which entry applies, Agent 3 already
   decided that). **Flagging explicitly since it's the one place the UI
   reads from `knowledge_base/` directly rather than only from the
   orchestrator's result — confirm you're fine with this before I build
   it, or I can omit full citations from v1 and show only the entry id.**

6. **`NO_ENTRY_AVAILABLE` messaging — genuine judgment call.** Your
   specified sentence ("Authoritative LADBS guidance was not available...")
   is very close in meaning to Agent 3's own fixed fallback text ("No
   approved knowledge-base entry exists for this stall pattern..."), but
   not identical wording. Two options:
   - **(a)** Show your sentence as the primary section-2 text, with
     Agent 3's actual fallback string available underneath in small/muted
     text or an expander, so nothing from the real object is hidden.
   - **(b)** Show your sentence as a small labeled caption *above* Agent
     3's unmodified text, both visible at normal size.
   Neither edits the underlying `DeveloperExplanation` object — this is
   purely about which string is visually primary. **I'd lean (a)** (avoids
   showing two near-duplicate sentences at equal visual weight, which
   reads as redundant) but want your call before building it.

7. **A real, pre-existing input-handling gap, newly relevant.**
   `ingestion/permits.py`'s single-permit SoQL lookup interpolates
   `permit_number` into a `$where` clause **unescaped**
   (`f"permit_nbr='{permit_number}'"`), while `inspections.py` and
   `cohort_populations.py` both already escape the same kind of value
   (`.replace("'", "''")` / an existing `_esc()` helper). This was low-risk
   with CLI/test-only callers; a public text box is a different trust
   boundary. Blast radius is bounded (Socrata's API is read-only public
   data, so worst case is a malformed query or unexpected read, not data
   modification or exposure), but it's a real gap, not a hypothetical one.
   **This is a 2-line, precedented fix in already-established style** (the
   same `_esc()` pattern used three lines away in the same package), and
   squarely matches "unless UI integration exposes a genuine defect" —
   **I'd like your go-ahead to apply it as part of this milestone**,
   separately called out in the diff so it's not buried inside UI changes.
   Until then, I'll add basic input handling in `app/errors.py` (reject
   empty/whitespace-only input, strip surrounding whitespace) as a partial
   mitigation that doesn't touch Agent 1.

8. **Counting detections by severity for the top-level summary** ("3
   severe · 1 watch") is a presentation-layer tally of labels Agent 2
   already assigned — not new severity computation — but I want to name
   it explicitly as the one place the UI aggregates across multiple
   detections, so it's a conscious, approved choice and not something that
   crept in unnoticed.

9. **Disclaimer placement — repeat per card or show once?** Leaning
   toward once, prominently, at the page bottom (section G) rather than
   repeated on every finding card, to avoid the page feeling
   disclaimer-heavy for a live demo. Flagging since "always show" could
   be read either way.

---

## 4. Error handling (no analytical logic involved)

| Case | Handling |
|---|---|
| Empty/whitespace-only input | Inline validation message before calling the orchestrator at all — no pipeline run |
| Permit not found | **Not an error path** — `run_pipeline` already returns a valid `PermitAnalysisResult` with `outcome=INSUFFICIENT_EVIDENCE`; renders through the normal section F path |
| `PipelineExecutionError` (network/infra failure at any of the 3 stages) | Caught in `streamlit_app.py`, mapped via `app/errors.py` to a plain message ("We couldn't complete the analysis right now — the city's open data service may be temporarily unavailable. Please try again shortly.") — the underlying exception, stage name, and DB path are logged server-side only, never rendered to the page |
| Any other unhandled exception | Same generic message, `st.exception` never called in the default (non-debug) path — no traceback reaches the browser |

---

Waiting for your decisions on items 5, 6, 7, and 9 above (and general
approval of the rest) before writing any UI code.
