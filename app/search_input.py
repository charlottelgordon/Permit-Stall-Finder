"""Unified-search input classifier -- decides whether what a user typed
into the single search bar (Phase 10 redesign) looks like one or more
LADBS permit numbers, or a street address, so streamlit_app.py can route
it to the right lookup path (the pipeline directly, vs.
fetch_permits_by_address() first). Pure text classification only: no
network call, no validation beyond shape -- the same "resolve, don't
analyze" spirit address_search.py and portfolio.parse_permit_numbers()
already follow.
"""

from __future__ import annotations

import re

from portfolio import parse_permit_numbers

_PERMIT_NUMBER_SHAPE = re.compile(r"^\d+-\d+-\d+$")


def classify(raw_text: str) -> tuple[str, list[str]]:
    """Returns ("permit_numbers", [...]) if every comma/newline-separated
    token in raw_text has the NNNNN-NNNNN-NNNNN shape LADBS permit
    numbers use (see i18n.py's unified_search_help string for the exact
    example), otherwise ("address", [raw_text.strip()]) -- a bare street
    address has no such delimiter-separated structure to split on, so
    it's kept whole rather than run through parse_permit_numbers()."""
    tokens = parse_permit_numbers(raw_text)
    if tokens and all(_PERMIT_NUMBER_SHAPE.match(tok) for tok in tokens):
        return "permit_numbers", tokens
    return "address", [raw_text.strip()]
