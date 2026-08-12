"""Section F — coverage / data-quality gaps.

Kept as its own visually distinct section (not folded into the top-level
result or a findings card) so that a coverage gap can never be mistaken for
a clean "no material stall" read -- see UI_DESIGN.md decision "a coverage
gap cannot visually resemble a clean/no-stall result". Uses st.warning,
never st.success, regardless of how many detections exist alongside it.
"""

from __future__ import annotations

import streamlit as st

from formatting import DATA_QUALITY_FLAG_LABELS
from permit_stall_finder.schema.journey import DataQualityFlag


def render(coverage_gaps: list[str], data_quality_flags: list[DataQualityFlag]) -> None:
    if not coverage_gaps and not data_quality_flags:
        return

    st.subheader("Coverage & data-quality notes")
    st.warning(
        "Parts of this permit could not be fully assessed, or the underlying data has "
        "known limitations. This is separate from -- and does not confirm or rule out -- "
        "a stall."
    )

    if coverage_gaps:
        st.markdown("**Coverage gaps**")
        for gap in coverage_gaps:
            st.markdown(f"- {gap}")

    if data_quality_flags:
        st.markdown("**Data-quality notes**")
        for flag in data_quality_flags:
            st.markdown(f"- {DATA_QUALITY_FLAG_LABELS.get(flag, flag.value)}")
