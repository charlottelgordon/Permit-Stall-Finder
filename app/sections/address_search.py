"""Search-by-address -- an alternative to typing a permit number, for a
user who knows an address but not the permit number on it. A resolver
only: it never analyzes anything itself, it just helps a user find the
permit_number(s) to hand to the normal single-permit / portfolio flow in
streamlit_app.py, exactly the way parse_permit_numbers() hands typed text
to that same flow.

Calls ingestion.permits.fetch_permits_by_address() directly -- the same
kind of live network call run_pipeline() itself makes, just for a
different lookup. Every raw row it gets back is display-only here: no
analysis, no severity, no journey reconstruction -- selecting a result
below only queues its permit_number for the real pipeline to run.

Also records each successful search into storage/user_state.py's
search_history (so it shows up in quick_access.py's "Recent" row for a
return user) and offers a star toggle for the address query itself --
the same "log/star the thing you're doing here" pattern portfolio.py and
streamlit_app.py already follow for permit numbers, just for the address
half of the search flow.
"""

from __future__ import annotations

import duckdb
import streamlit as st

from errors import GENERIC_ERROR_MESSAGE
from sections import quick_access
from permit_stall_finder.ingestion.permits import fetch_permits_by_address
from permit_stall_finder.storage import user_state


def _format_match_label(row: dict) -> str:
    permit_nbr = row.get("permit_nbr") or "—"
    permit_type = row.get("permit_type") or "—"
    status_desc = row.get("status_desc") or "—"
    address = row.get("primary_address") or "—"
    return f"**{permit_nbr}** — {permit_type} — {status_desc} — {address}"


def render(conn: duckdb.DuckDBPyConnection, *, auto_run: bool = False) -> tuple[bool, list[str]]:
    """Returns (submitted, permit_numbers). submitted is True only on the
    Streamlit run where the user just clicked "Analyze selected" --
    callers should treat submitted=False as "nothing to do yet", not as
    "the search found nothing".

    auto_run=True re-runs the search immediately using whatever's already
    in the address input's session_state -- streamlit_app.py sets that
    when a user clicks a starred/recent address pill in quick_access.py,
    so picking a past address search behaves exactly like typing it and
    clicking "Search by address" again."""
    st.caption(
        "Don't know the permit number? Search by street address and pick the permit(s) "
        "you want analyzed."
    )
    address_query = st.text_input(
        "Street address", placeholder="e.g. 200 N Spring St", key="address_query_input"
    )
    search_clicked = st.button("Search by address", key="address_search_button")

    if search_clicked or auto_run:
        query = address_query.strip()
        if not query:
            st.session_state.address_matches = None
            if search_clicked:
                st.warning("Enter a street address to search.")
        else:
            try:
                st.session_state.address_matches = fetch_permits_by_address(query)
                user_state.record_search(conn, "address", query)
            except Exception:
                st.session_state.address_matches = None
                st.error(GENERIC_ERROR_MESSAGE)

    if address_query.strip():
        quick_access.render_star_toggle(conn, "address", address_query.strip())

    matches = st.session_state.get("address_matches")
    if matches is not None and not matches:
        st.info("No permits found for that address. Try a shorter or differently formatted address.")

    submitted = False
    selected: list[str] = []
    if matches:
        st.caption(f"{len(matches)} permit(s) found -- select which to analyze:")
        for row in matches:
            permit_nbr = row.get("permit_nbr")
            if not permit_nbr:
                continue
            if st.checkbox(_format_match_label(row), key=f"address_match_{permit_nbr}"):
                selected.append(permit_nbr)
        if selected:
            submitted = st.button("Analyze selected", type="primary", key="address_analyze_button")

    return submitted, selected
