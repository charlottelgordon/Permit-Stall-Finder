# [PRD] Permit Stall Finder

**POCs:** [Name], [Name]
**Status:** Draft
**Sector:** Construction
**Data source:** [data.lacity.org](https://data.lacity.org) (LA Building Permits, LA Building Inspections)

## Executive Summary

Permit Stall Finder is a multi-agent tool that reconstructs the full lifecycle of a Los Angeles building permit — from submission through every inspection — by joining two datasets from data.lacity.org that are published separately but share a common permit number. It identifies where and for how long a project has stalled in the permitting process, then translates that stall into a plain-language explanation of what it typically means and what tends to unblock it, aimed at developers and contractors managing active projects.

*[2-3 sentences on the business case: why this matters now, who asked for it, and what changes if it ships]*

## Vision

Vision for the future state is to give developers and contractors a single, always-current view of where their LA building permit stands — replacing manual cross-referencing of two disconnected city datasets with a plain-English answer to "where is my project stuck, and what do I do about it."

*[1-2 sentences describing the north-star experience once this is fully realized]*

## Background

LA Building Permits and LA Building Inspections are published as separate datasets on data.lacity.org. They share a permit number but are not natively joined, updated on different cadences, and require domain knowledge to interpret correctly. Today, understanding whether a specific permit is progressing normally or stuck — and why — requires manually pulling both datasets, reconciling them by hand, and knowing enough about the permitting process to recognize an abnormal gap.

*[Add any prior attempts, related tools, or context on why this hasn't been solved already]*

## Problem: issues with the current state

- Two datasets, one problem: permits and inspections live in separate tables with no reconstructed, end-to-end timeline
- No definition of "stalled": there is no existing signal for when a permit has stopped moving relative to what's normal for its type
- No explanation layer: even a developer who notices a delay has no plain-language guidance on what it usually means or what unblocks it
- Manual, one-off investigation: today this requires downloading raw city data and interpreting it without domain-specific tooling

*[Add or adjust issues based on developer/contractor research]*

## Pillars of the solution

### 1. Journey reconstruction (Agent 1)

- Joins LA Building Permits and LA Building Inspections by permit number into one ordered timeline
- Captures submission, plan check, issuance, and every inspection event with date, type, and result

### 2. Stall detection (Agent 2)

- Analyzes the reconstructed journey to identify where a permit has stopped progressing
- Quantifies how long the permit has been stalled at that stage

### 3. Developer-facing explanation (Agent 3)

- Translates a detected stall into a plain-language explanation of what it usually means
- Surfaces the actions that typically unblock that type of stall

## Target user

- Developers and general contractors tracking active LA building permits
- *[Add secondary personas, e.g. expediters, architects, property owners]*

## Success metrics

- *[North star metric, e.g. reduction in median time developers spend diagnosing a stall]*
- *[Adoption metric, e.g. weekly active permits tracked]*
- *[Quality metric, e.g. accuracy of stall detection validated against known cases]*

## Guiding principles

- Explanations are grounded in observed data patterns, not speculation
- The tool is informational and does not replace confirming status directly with LADBS
- Stall detection should be transparent: a developer can see why a permit was flagged
- *[Add or adjust principles specific to this project]*

## Metrics to track (TBD)

| Metric | Type (leading / lagging) | Baseline | Target | Definition |
| --- | --- | --- | --- | --- |
| % of open permits with a detected stall | Tool success | TBD | TBD | Permits flagged by Agent 2 as currently stalled, over all open permits in scope |
| Median time-to-first-explanation | Tool success | TBD | TBD | Time from a permit stalling to Agent 3 producing a developer-facing explanation |
| Developer-reported usefulness of explanation | User success | TBD | TBD | Survey / feedback rating on whether the explanation helped the developer act |
| Journey reconstruction accuracy | Tool success | TBD | TBD | % of permits where Agent 1's reconstructed timeline matches source records |
| Stall detection precision / recall | Tool success | TBD | TBD | Accuracy of Agent 2's stall flags against a labeled validation set |

## Launch plan

- *[Phase 1: Agent 1 (journey reconstruction) validated against a sample of known permits]*
- *[Phase 2: Agent 2 (stall detection) with configurable thresholds, internal review only]*
- *[Phase 3: Agent 3 (developer explanations) + limited external pilot]*
- *[Phase 4: General availability]*

## Scope of MVP

- *[Permit types included, e.g. residential alteration/addition permits]*
- *[Geographic / dataset scope, e.g. permits issued within [date range]]*
- *[Agent 1 output: reconstructed journey for in-scope permits]*
- *[Agent 2 output: stalled / not-stalled flag with stage and duration]*
- *[Agent 3 output: explanation for the most common [N] stall types]*

## Out of scope

- *[Permit types not yet covered, e.g. [commercial / demolition / electrical-only]]*
- *[Direct integration with LADBS systems or ability to take action on a developer's behalf]*
- *[Jurisdictions outside the City of Los Angeles]*
- *[Legal or regulatory advice]*

## Requirements

| # | Agent / Area | User Story | Acceptance Criteria |
| --- | --- | --- | --- |
| 1 | Agent 1 — Journey Reconstructor | As a developer, I want to see the full lifecycle of my permit — from submission through every scheduled and completed inspection — reconstructed from the two source datasets, so I have one timeline instead of two disconnected records. | Joins LA Building Permits and LA Building Inspections datasets on permit number. Timeline includes submission, plan check milestones, issuance, and every inspection event with date, type, and result. Handles permits with missing or partial inspection records without failing. Output is structured (e.g., ordered list of events) and reusable by Agents 2 and 3. |
| 2 | Agent 1 — Journey Reconstructor | As a system, I need a consistent internal representation of a permit's journey so downstream agents can reason about it without re-parsing raw records. | Defines a shared schema for a permit journey (stages, timestamps, statuses). Refreshes on a defined cadence aligned to data.lacity.org update frequency. Logs permits that could not be reconstructed (e.g., unmatched permit numbers) for review. |
| 3 | Agent 2 — Stall Detector | As a developer, I want the tool to tell me where my project has stalled in the permitting process and for how long, so I know where to focus my attention. | Identifies gaps between expected and actual stage transitions using the reconstructed journey. Flags a permit as "stalled" against a defined threshold (e.g., no movement for [X] days at a given stage). Reports which stage the stall is occurring at and elapsed time in that stage. Distinguishes stall types (e.g., awaiting reinspection, awaiting correction, awaiting plan check) where the data supports it. |
| 4 | Agent 2 — Stall Detector | As a product owner, I want stall thresholds to be configurable, so we can tune sensitivity as we learn what "normal" looks like for different permit types. | Thresholds can be set per permit type / work description category. Changes to thresholds are auditable. |
| 5 | Agent 3 — Developer Explainer | As a developer, I want a plain-language explanation of what my specific type of stall usually means, so I understand why my project isn't moving. | Takes the stall type and stage from Agent 2 as input. Generates a plain-language, non-jargon explanation of the likely cause(s). Explanation is grounded in patterns observed in historical permit data, not speculation. Avoids presenting the explanation as an official determination from LADBS. |
| 6 | Agent 3 — Developer Explainer | As a developer, I want to know what typically unblocks this kind of stall, so I know what action to take next. | Provides a short list of common next steps associated with resolving that stall type. Distinguishes actions the developer/applicant can take vs. actions that depend on the city. Includes a disclaimer that guidance is informational and not a substitute for confirming with LADBS. |

## Data requirements

- Source: LA Building Permits dataset — data.lacity.org
- Source: LA Building Inspections dataset — data.lacity.org
- Join key: permit number, present in both datasets
- *[Define refresh cadence based on each dataset's update frequency on data.lacity.org]*
- *[Define handling for records with missing, malformed, or unmatched permit numbers]*

## Artifacts

- LA Building Permits dataset — [data.lacity.org](https://data.lacity.org)
- LA Building Inspections dataset — [data.lacity.org](https://data.lacity.org)
- *[Add links to design mockups, agent architecture diagram, or related docs as they're created]*
