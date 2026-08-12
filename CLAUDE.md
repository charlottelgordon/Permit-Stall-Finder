# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository state

This repository currently contains no source code — only `Permit_Stall_Finder_PRD_Template.docx`, the product requirements document for the project. There is no build system, package manifest, test suite, or application code yet. When the user asks you to start implementing, you are building the project from scratch and should propose a stack/architecture rather than assume one exists.

## Project: Permit Stall Finder

A multi-agent tool that reconstructs the full lifecycle of a Los Angeles building permit — from submission through every inspection — by joining two datasets from `data.lacity.org` that are published separately but share a common permit number (LA Building Permits and LA Building Inspections). It identifies where and for how long a project has stalled in the permitting process, then produces a plain-language explanation of what the stall typically means and what tends to unblock it, aimed at developers and contractors managing active projects.

### Data sources
- **LA Building Permits** — `data.lacity.org`
- **LA Building Inspections** — `data.lacity.org`
- Join key: permit number (present in both datasets, not natively joined by the source)
- Datasets update on different cadences and require domain knowledge to interpret correctly (e.g. what a given inspection result or gap between stages normally means)

### Agent architecture (per PRD)

The system is designed as three agents operating in a pipeline, each consuming the prior agent's structured output:

1. **Agent 1 — Journey Reconstructor**: Joins the two datasets by permit number into one ordered timeline (submission, plan check milestones, issuance, every inspection event with date/type/result). Must handle permits with missing or partial inspection records without failing. Defines a shared schema for a "permit journey" (stages, timestamps, statuses) that Agents 2 and 3 consume — this schema is the core internal contract between agents. Logs unmatched/unreconstructable permits for review rather than dropping them silently.

2. **Agent 2 — Stall Detector**: Analyzes a reconstructed journey to identify where a permit has stopped progressing and for how long. Flags a permit as "stalled" against a threshold (e.g. no movement for X days at a stage), and distinguishes stall types where data supports it (e.g. awaiting reinspection, awaiting correction, awaiting plan check). Thresholds must be configurable per permit type / work description category, and threshold changes must be auditable.

3. **Agent 3 — Developer Explainer**: Takes a stall type + stage from Agent 2 and produces a plain-language, non-jargon explanation of the likely cause, grounded in observed historical data patterns (not speculation), plus a short list of typical next steps — distinguishing developer-actionable steps from city-dependent ones. Explanations must never be presented as an official LADBS determination and must include a disclaimer that the tool is informational only.

### Guiding principles (from PRD — apply these when designing agent behavior)
- Explanations are grounded in observed data patterns, not speculation.
- The tool is informational and does not replace confirming status directly with LADBS.
- Stall detection should be transparent: a developer can see *why* a permit was flagged (i.e. Agent 2's reasoning/inputs should be inspectable, not a black box).

### Scope boundaries (from PRD)
- In scope: City of Los Angeles building permits only, using the two named `data.lacity.org` datasets.
- Out of scope: direct integration with LADBS systems or taking action on a developer's behalf, jurisdictions outside LA, legal/regulatory advice.
- The MVP permit-type scope, geographic/date scope, and number of stall types covered by Agent 3 are still TBD in the PRD — check with the user before assuming coverage.

See `Permit_Stall_Finder_PRD_Template.docx` for the full PRD, including requirements, acceptance criteria, and success metrics (several fields are still marked TBD/placeholder in the current draft).
