# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

All three agents are implemented, with a Streamlit UI on top and a full offline test suite. Layout:

- `src/permit_stall_finder/` — the agent pipeline (`agents/`, `schema/`, `ingestion/`, `analysis/`, `analytics/`, `knowledge_base/`, `storage/`, `orchestration/`) and `cli.py` for running any stage from the command line.
- `app/` — the Streamlit app (`streamlit_app.py` is the entrypoint; `sections/` holds per-view render modules). Search, a Trends Dashboard (backed by a static artifact `scripts/generate_trends_artifact.py` generates offline — see that script's own docstring for why it can't run live on Streamlit Community Cloud), and a starred-searches / My Permits view.
- `tests/` — offline, fixture-backed (`tests/fixtures/`), no network access required.
- `research/` — the design docs each module's own comments cite (`DATASET_VALIDATION.md`, `AGENT2_DESIGN.md`, `AGENT3_DESIGN.md`, `UI_DESIGN.md`).

Run the app: `streamlit run app/streamlit_app.py`. Run tests: `pytest`.

## Project: Permit Stall Finder

A multi-agent tool that reconstructs the full lifecycle of a Los Angeles building permit — from submission through every inspection — by joining two datasets from `data.lacity.org` that are published separately but share a common permit number (LA Building Permits and LA Building Inspections). It identifies where and for how long a project has stalled in the permitting process, then produces a plain-language explanation of what the stall typically means and what tends to unblock it, aimed at developers and contractors managing active projects.

### Data sources
- **LA Building Permits** — `data.lacity.org`
- **LA Building Inspections** — `data.lacity.org`
- Join key: permit number (present in both datasets, not natively joined by the source)
- Datasets update on different cadences and require domain knowledge to interpret correctly (e.g. what a given inspection result or gap between stages normally means)

### Agent architecture (per PRD)

The system is three agents operating in a pipeline, each consuming the prior agent's structured output (see `orchestration/pipeline.py` for how they're wired together, and `cli.py` for running any single stage in isolation):

1. **Agent 1 — Journey Reconstructor** (`agents/journey_reconstructor.py`): Joins the two datasets by permit number into one ordered timeline (submission, plan check milestones, issuance, every inspection event with date/type/result). Handles permits with missing or partial inspection records without failing. Defines a shared schema for a "permit journey" (`schema/journey.py`'s `PermitJourney`) that Agents 2 and 3 consume — this schema is the core internal contract between agents. Logs unmatched/unreconstructable permits to `reconstruction_log` (`storage/db.py`) rather than dropping them silently.

2. **Agent 2 — Stall Detector** (`agents/stall_detector.py`, see `research/AGENT2_DESIGN.md` for the full design): Analyzes a reconstructed journey to identify where a permit has stopped progressing and for how long. Flags a permit as "stalled" against a threshold, and distinguishes stall types where data supports it (see `schema/stall_detection.py`'s `StallCategory`). Thresholds are configurable per permit type / work description category (`config.py`), and threshold changes are auditable (`storage/cohort_cache.py`).

3. **Agent 3 — Developer Explainer** (`agents/developer_explainer.py`, see `research/AGENT3_DESIGN.md`): Takes a stall type + stage from Agent 2 and produces a plain-language, non-jargon explanation of the likely cause, grounded in observed historical data patterns (not speculation) via `knowledge_base/`, plus a short list of typical next steps — distinguishing developer-actionable steps from city-dependent ones. Explanations are never presented as an official LADBS determination and always carry a disclaimer that the tool is informational only.

### Guiding principles (from PRD — apply these when designing agent behavior)
- Explanations are grounded in observed data patterns, not speculation.
- The tool is informational and does not replace confirming status directly with LADBS.
- Stall detection should be transparent: a developer can see *why* a permit was flagged (i.e. Agent 2's reasoning/inputs should be inspectable, not a black box).

### Scope boundaries (from PRD)
- In scope: City of Los Angeles building permits only, using the two named `data.lacity.org` datasets.
- Out of scope: direct integration with LADBS systems or taking action on a developer's behalf, jurisdictions outside LA, legal/regulatory advice.
- The MVP permit-type scope, geographic/date scope, and number of stall types covered by Agent 3 are still TBD in the PRD — check with the user before assuming coverage.

See `Permit_Stall_Finder_PRD_Template.docx` for the full PRD, including requirements, acceptance criteria, and success metrics (several fields are still marked TBD/placeholder in the current draft).
