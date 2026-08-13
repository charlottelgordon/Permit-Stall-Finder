"""Quick-glance overview -- the left-panel summary block of the two-panel
drill-down layout (Phase 11 redesign), stacked above Permit Journey/Other
Permits/Resources/the map. Every field is read directly off an
already-complete PermitAnalysisResult (address/type/status/issuance/last-
update via portfolio.summarize_result(), the same computation the results
table's own columns already use, so this block can't drift out of sync
with what the table shows for the same permit); this module composes no
new interpretation of its own beyond wrapping each finding's own
already-computed severity/category/percentile/count into one bullet line
via i18n.top_finding_bullet().

Was previously a horizontal st.columns(6) strip; the severity-count blue
banner that used to sit near the top of the tab (section B,
top_level_result.py) is now rendered once, above both panels, by
drill_down.py directly -- this block only repeats the identifying facts
plus the full list of this permit's own findings, not the tab-wide
severity summary.
"""

from __future__ import annotations

import streamlit as st

import portfolio
from i18n import outcome_headline, t, top_finding_bullet
from permit_stall_finder.orchestration.pipeline import AnalysisOutcome, PermitAnalysisResult

_OUTCOME_ICONS = {
    AnalysisOutcome.NO_MATERIAL_STALL_DETECTED: "✅",
    AnalysisOutcome.INSUFFICIENT_EVIDENCE: "🔍",
    AnalysisOutcome.STALL_DETECTED: "📋",
}


def render(result: PermitAnalysisResult) -> None:
    row = portfolio.summarize_result(result)
    detections = result.stall_assessment.detections

    with st.container(border=True):
        st.markdown(f"**{t('qg_address')}**  \n{row.address}")
        st.markdown(f"**{t('qg_type')}**  \n{row.permit_type}")
        st.markdown(f"**{t('qg_status')}**  \n{row.status_desc}")
        st.markdown(f"**{t('qg_issuance_status')}**  \n{row.issuance_status}")
        st.markdown(f"**{t('qg_last_update')}**  \n{row.last_status_update}")

        if detections:
            st.markdown(f"**{t('qg_top_findings')}**")
            for detection in detections:
                st.markdown(f"- {top_finding_bullet(detection)}")
        else:
            icon = _OUTCOME_ICONS[result.outcome]
            st.markdown(f"**{t('qg_result')}**  \n{icon} {outcome_headline(result)}")

