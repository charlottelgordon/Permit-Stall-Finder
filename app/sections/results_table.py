"""Unified quick-glance results table -- shown at the top of the page
after any search, whether one permit or many resolved (Phase 10
redesign). Replaces both the earlier worst-first portfolio.render_table()
and the two-permit portfolio.render_two_panel() layout: every search
outcome now lands in the same 7-column table, with row selection driving
the tabbed drill-down section below (see app/drill_down.py) instead of a
separate "view full detail" selectbox.

Every column value is already computed on the PortfolioRow passed in --
this module only lays out an st.dataframe and reads back which row(s)
the user selected. See portfolio.py's summarize_result() for where each
column's value actually comes from; nothing here recomputes anything.

Phase 14: the "Findings" column (r.severity_counts, e.g. "3 severe, 1
watch") gets a blue highlight on any row with at least one severe
finding, so a user scanning many rows can spot the ones that need
attention without reading every cell. Plain dict rows can't carry
per-cell styling, so this now goes through a pandas DataFrame + Styler
instead -- st.dataframe still accepts on_select/selection_mode the same
way on a Styler as it does on a plain list of dicts.

Every column header carries a plain-language hover explanation via
st.column_config's own `help=` (a small (i) icon Streamlit renders next
to the header text) -- someone unfamiliar with a term like "Issuance
status" can hover it instead of having to guess or ask.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from i18n import t
from portfolio import PortfolioRow
from permit_stall_finder.schema.stall_detection import Severity

# Matches the --sem-severe token in streamlit_app.py's stylesheet -- the
# same semantic red used for severity chips elsewhere, not the accent
# blue this used to be (semantic severity color is deliberately kept
# separate from the navy interactive accent, see that stylesheet's own
# token comments).
_SEVERE_HIGHLIGHT = "background-color: #A24638; color: white; font-weight: 600;"


def render(rows: list[PortfolioRow], *, key: str = "results_table") -> list[str]:
    """Renders the table and returns the list of currently-selected
    permit numbers, in row order. Selection is driven entirely by
    Streamlit's own st.dataframe(on_select=...) widget state -- nothing
    here tracks selection itself across reruns; streamlit_app.py decides
    how to combine this with any prior/default selection."""
    st.subheader(t("results_table_header"))
    st.caption(f"{len(rows)} {t('results_table_caption_suffix')} · {t('results_table_hint')}")

    findings_col = t("col_findings")
    table_data = [
        {
            t("col_permit_number"): r.permit_number,
            findings_col: r.severity_counts,
            t("col_submitted_date"): r.submitted_date.isoformat() if r.submitted_date else "—",
            t("col_permit_type"): r.permit_type,
            t("col_issuance_status"): r.issuance_status,
            t("col_permit_status"): r.raw_status_desc,
            t("col_last_update"): r.last_status_update,
        }
        for r in rows
    ]

    def _highlight_severe(row: pd.Series) -> list[str]:
        has_severe = rows[row.name].top_severity == Severity.SEVERE
        return [_SEVERE_HIGHLIGHT if (has_severe and col == findings_col) else "" for col in row.index]

    styled = pd.DataFrame(table_data).style.apply(_highlight_severe, axis=1)

    column_config = {
        t("col_permit_number"): st.column_config.TextColumn(help=t("col_permit_number_help")),
        findings_col: st.column_config.TextColumn(help=t("col_findings_help")),
        t("col_submitted_date"): st.column_config.TextColumn(help=t("col_submitted_date_help")),
        t("col_permit_type"): st.column_config.TextColumn(help=t("col_permit_type_help")),
        t("col_issuance_status"): st.column_config.TextColumn(help=t("col_issuance_status_help")),
        t("col_permit_status"): st.column_config.TextColumn(help=t("col_permit_status_help")),
        t("col_last_update"): st.column_config.TextColumn(help=t("col_last_update_help")),
    }

    event = st.dataframe(
        styled,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="multi-row",
        column_config=column_config,
        key=key,
    )

    selected_indices = event.selection["rows"] if event is not None else []
    return [rows[i].permit_number for i in selected_indices if 0 <= i < len(rows)]
