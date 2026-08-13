"""Unified quick-glance results table -- shown at the top of the page
after any search, whether one permit or many resolved (Phase 10
redesign). Replaces both the earlier worst-first portfolio.render_table()
and the two-permit portfolio.render_two_panel() layout: every search
outcome now lands in the same 8-column table, with row selection driving
the tabbed drill-down section below (see app/drill_down.py) instead of a
separate "view full detail" selectbox.

Every column value is already computed on the PortfolioRow passed in --
this module only lays out an st.dataframe and reads back which row(s)
the user selected. See portfolio.py's summarize_result() for where each
column's value actually comes from; nothing here recomputes anything.
"""

from __future__ import annotations

import streamlit as st

from i18n import t
from portfolio import PortfolioRow


def render(rows: list[PortfolioRow], *, key: str = "results_table") -> list[str]:
    """Renders the table and returns the list of currently-selected
    permit numbers, in row order. Selection is driven entirely by
    Streamlit's own st.dataframe(on_select=...) widget state -- nothing
    here tracks selection itself across reruns; streamlit_app.py decides
    how to combine this with any prior/default selection."""
    st.subheader(t("results_table_header"))
    st.caption(f"{len(rows)} {t('results_table_caption_suffix')} · {t('results_table_hint')}")

    table_data = [
        {
            t("col_permit_number"): r.permit_number,
            t("col_submitted_date"): r.submitted_date.isoformat() if r.submitted_date else "—",
            t("col_time_since_submission"): r.time_since_submission,
            t("col_permit_type"): r.permit_type,
            t("col_issuance_status"): r.issuance_status,
            t("col_permit_status"): r.raw_status_desc,
            t("col_delay_status"): r.delay_status,
            t("col_last_update"): r.last_status_update,
        }
        for r in rows
    ]

    event = st.dataframe(
        table_data,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="multi-row",
        key=key,
    )

    selected_indices = event.selection["rows"] if event is not None else []
    return [rows[i].permit_number for i in selected_indices if 0 <= i < len(rows)]
