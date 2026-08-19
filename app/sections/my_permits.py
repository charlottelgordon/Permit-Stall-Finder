"""My Permits -- a personal dashboard auto-populated from every search the
current browser has starred (see storage/starred.py, app/browser_id.py).
Each starred entry is re-expanded back into permit numbers exactly the way
the main search flow in streamlit_app.py already resolves that same kind
of query (parse_permit_numbers for a starred permit-number query,
fetch_permits_by_address for a starred address), then run through the
same portfolio.run_batch() + results_table.render() pipeline the search
page uses -- no separate rendering logic invented here.

No caching layer is added in this pass: every open of this view re-runs
the full pipeline live for every resolved permit. Flagged as a candidate
follow-up (st.cache_data keyed on (uid, tuple(permit_numbers)) with a
short TTL), not built now since it wasn't asked for.
"""

from __future__ import annotations

import streamlit as st

import portfolio
from i18n import t
from permit_stall_finder import config
from permit_stall_finder.ingestion.permits import fetch_permits_by_address
from permit_stall_finder.storage import starred
from sections import results_table


def _resolve_entry(entry: starred.StarredSearchEntry) -> list[str]:
    if entry.kind == "permit_query":
        return portfolio.parse_permit_numbers(entry.value)
    try:
        matches = fetch_permits_by_address(entry.value)
    except Exception:
        return []
    return [m["permit_nbr"] for m in matches if m.get("permit_nbr")]


def resolve_starred_permit_numbers(conn, uid: str) -> list[str]:
    """Every permit number behind this uid's starred searches, resolved
    and de-duplicated (order preserved) -- the same expansion render()
    below does for its own results table, exposed here so
    trends_dashboard.py's "my saved permits" scope can reuse it rather
    than re-implementing entry resolution a second time."""
    entries = starred.read_starred_searches(conn, uid)
    permit_numbers: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        for permit_number in _resolve_entry(entry):
            if permit_number not in seen:
                seen.add(permit_number)
                permit_numbers.append(permit_number)
    return permit_numbers


def render(conn, uid: str | None) -> None:
    st.subheader(t("my_permits_header"))

    if uid is None:
        st.info(t("my_permits_no_uid"))
        return

    entries = starred.read_starred_searches(conn, uid)
    if not entries:
        st.info(t("my_permits_empty"))
        return

    st.markdown(f"**{t('my_permits_starred_searches_header')}**")
    for entry in entries:
        col_label, col_unstar = st.columns([5, 1])
        with col_label:
            st.write(f"{entry.value}  \n:gray[{entry.starred_at.strftime('%Y-%m-%d')}]")
        with col_unstar:
            if st.button(t("unstar_button"), key=f"my_permits_unstar_{entry.kind}_{entry.value}"):
                starred.unstar_search(conn, uid, entry.kind, entry.value)
                st.rerun()

    st.divider()

    permit_numbers = resolve_starred_permit_numbers(conn, uid)
    if not permit_numbers:
        st.info(t("info_no_permits_found"))
        return

    batch = portfolio.run_batch(
        conn, permit_numbers, sample_size=config.DEFAULT_COHORT_SAMPLE_SIZE, progress=True
    )
    results_table.render(batch.rows, key="my_permits_results_table")
