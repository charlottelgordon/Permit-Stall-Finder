# Permit Stall Finder

Reconstructs the observable journey of a Los Angeles building permit —
from submission through issuance, inspections, and finalization — by
joining two LA Open Data datasets that are published separately but share
a permit number. Built as three agents: Journey Reconstructor (Agent 1,
implemented), Stall Detector (Agent 2, not yet built), Developer Explainer
(Agent 3, not yet built).

See [`CLAUDE.md`](CLAUDE.md) for project scope and guiding principles, and
[`research/DATASET_VALIDATION.md`](research/DATASET_VALIDATION.md) for the
data investigation this implementation is grounded in — which datasets
were chosen, why, and what their real join quality and coverage limits
are.

## Data sources

- Permits: [`gwh9-jnip`](https://data.lacity.org/resource/gwh9-jnip.json)
  — "Building and Safety - Building Permits Submitted from 2020 to
  Present (N)". Includes both issued and not-yet-issued permits.
- Inspections: [`9w5z-rg2h`](https://data.lacity.org/resource/9w5z-rg2h.json)
  — "Building and Safety Inspections".

Both are public, unauthenticated Socrata endpoints — no app token is
required at this scale.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Usage

```bash
.venv/bin/python -m permit_stall_finder.cli journey <permit_number>
```

Example:

```bash
.venv/bin/python -m permit_stall_finder.cli journey 21030-20000-00256
```

Each run fetches the permit's current state and its inspection history,
persists a dated snapshot to a local DuckDB database (`data/permit_stall_finder.duckdb`,
gitignored), and prints the reconstructed `PermitJourney`.

## Tests

```bash
.venv/bin/pytest
```

Tests run offline against fixture data captured from real permits (see
`tests/fixtures/`) — no network access required.
