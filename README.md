# Permit Check LA

Reconstructs the observable journey of a Los Angeles building permit —
from submission through issuance, inspections, and finalization — by
joining two LA Open Data datasets that are published separately but share
a permit number, then identifies where and why a permit has stalled and
explains it in plain language. Built as three agents: Journey
Reconstructor, Stall Detector, and Developer Explainer (all implemented —
see [`CLAUDE.md`](CLAUDE.md) for what each one does and where its code
lives), plus a Streamlit UI ([`app/`](app/)) on top.

See [`CLAUDE.md`](CLAUDE.md) for project scope, guiding principles, and a
map of the codebase, and
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

## Running the app

```bash
.venv/bin/streamlit run app/streamlit_app.py
```

## CLI

Run any single stage of the pipeline directly (`journey` = Agent 1 only,
`stalls` = Agent 1+2, `explain` = Agent 1+2+3, `analyze` = the full
orchestrated pipeline — see `cli.py`):

```bash
.venv/bin/python -m permit_stall_finder.cli analyze 21030-20000-00256
```

Each run fetches the permit's current state and its inspection history,
persists a dated snapshot to a local DuckDB database (`data/permit_stall_finder.duckdb`,
gitignored), and prints the result as JSON.

## Tests

```bash
.venv/bin/pytest
```

Tests run offline against fixture data captured from real permits (see
`tests/fixtures/`) — no network access required.
