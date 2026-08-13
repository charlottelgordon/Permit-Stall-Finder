"""Quick-glance overview -- the left-panel summary block of the two-panel
drill-down layout (Phase 11 redesign), stacked above the map. Every field
is read directly off an already-complete PermitAnalysisResult; this module
composes no new interpretation, only lays out facts Agent 1/2/3 already
produced as a vertical list of labeled facts.

Was previously a horizontal st.columns(6) strip; the severity-count blue
banner that used to sit near the top of the tab (section B,
top_level_result.py) is now rendered once, above both panels, by
drill_down.py directly -- this block only repeats the identifying facts
(permit, address, type, status, days in status) plus this permit's own
top finding, not the tab-wide severity summary.
"""

from __future__ import annotations

import streamlit as st

from formatting import SEVERITY_COLORS
from i18n import outcome_headline, plain_status_desc, severity_label, t
from permit_stall_finder.orchestration.pipeline import AnalysisOutcome, PermitAnalysisResult
from permit_stall_finder.schema.stall_detection import Severity

_OUTCOME_ICONS = {
    AnalysisOutcome.NO_MATERIAL_STALL_DETECTED: "✅",
    AnalysisOutcome.INSUFFICIENT_EVIDENCE: "🔍",
    AnalysisOutcome.STALL_DETECTED: "📋",
}

_SEVERITY_RANK: dict[Severity, int] = {
    Severity.SEVERE: 3,
    Severity.ELEVATED: 2,
    Severity.WATCH: 1,
    Severity.UNSCORED: 0,
}


def _top_severity(result: PermitAnalysisResult) -> Severity | None:
    """Same plain max()-over-already-assigned-labels approach as
    portfolio._max_severity() -- kept as a small local copy rather than a
    cross-import so this card has no dependency on the portfolio module
    (it's also used from the single-permit view, which doesn't otherwise
    need portfolio.py at all)."""
    severities = [d.severity for d in result.stall_assessment.detections]
    if not severities:
        return None
    return max(severities, key=lambda s: _SEVERITY_RANK[s])


def render(result: PermitAnalysisResult) -> None:
    snapshot = result.journey.latest_snapshot
    address = (snapshot.raw.get("primary_address") if snapshot else None) or "—"
    permit_type = snapshot.permit_type if snapshot else "—"
    status_desc = plain_status_desc(snapshot.status_desc) if snapshot else "—"
    days = (
        result.journey.derived.days_submitted_to_current_status
        if result.journey.derived is not None
        else None
    )
    severity = _top_severity(result)

    with st.container(border=True):
        st.markdown(f"**{t('qg_permit')}**  \n{result.permit_number}")
        st.markdown(f"**{t('qg_address')}**  \n{address}")
        st.markdown(f"**{t('qg_type')}**  \n{permit_type}")
        st.markdown(f"**{t('qg_status')}**  \n{status_desc}")
        st.markdown(f"**{t('qg_days_in_status')}**  \n{days if days is not None else '—'}")

        if severity is not None:
            color = SEVERITY_COLORS[severity]
            badge = (
                f'<span style="background-color:{color};color:white;padding:2px 10px;'
                f'border-radius:4px;font-weight:600">{severity_label(severity)}</span>'
            )
            st.markdown(f"**{t('qg_top_finding')}**  \n{badge}", unsafe_allow_html=True)
        else:
            icon = _OUTCOME_ICONS[result.outcome]
            st.markdown(f"**{t('qg_result')}**  \n{icon} {outcome_headline(result)}")

