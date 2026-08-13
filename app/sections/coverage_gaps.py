"""Section F — coverage / data-quality gaps.

Kept as its own visually distinct section (not folded into the top-level
result or a findings card) so that a coverage gap can never be mistaken for
a clean "no material stall" read -- see UI_DESIGN.md decision "a coverage
gap cannot visually resemble a clean/no-stall result". Uses st.warning,
never st.success, regardless of how many detections exist alongside it.
"""

from __future__ import annotations

import streamlit as st

from i18n import data_quality_flag_label, plain_coverage_gap, t
from permit_stall_finder.schema.journey import DataQualityFlag


def render(coverage_gaps: list[str], data_quality_flags: list[DataQualityFlag]) -> None:
    if not coverage_gaps and not data_quality_flags:
        return

    st.subheader(t("coverage_notes_header"))
    st.warning(t("coverage_notes_warning"))

    if coverage_gaps:
        st.markdown(f"**{t('coverage_gaps_label')}**")
        for gap in coverage_gaps:
            st.markdown(f"- {plain_coverage_gap(gap)}")

    if data_quality_flags:
        st.markdown(f"**{t('data_quality_notes_label')}**")
        for flag in data_quality_flags:
            st.markdown(f"- {data_quality_flag_label(flag)}")
