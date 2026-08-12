"""Quick-glance horizontal summary card -- shown once at the top of a
completed single-permit analysis (below the persona switcher and any
portfolio table) so the highest-value facts are visible without
scrolling. Every field is read directly off an already-complete
PermitAnalysisResult; this module composes no new interpretation, only
lays out facts Agent 1/2/3 already produced across one row of
st.columns.

Deliberately separate from top_level_result.py (section B): that section
keeps the neutral, no-outcome-color-coding treatment UI_DESIGN.md decision
3 requires for the full-page summary. This card is a denser at-a-glance
strip meant to sit above it, not replace it -- the full section B/C/D/E/F/G
sequence still renders below for anyone who wants the complete picture.
"""

from __future__ import annotations

import streamlit as st

from formatting import SEVERITY_COLORS, SEVERITY_LABELS, outcome_headline
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
    status_desc = snapshot.status_desc if snapshot else "—"
    days = (
        result.journey.derived.days_submitted_to_current_status
        if result.journey.derived is not None
        else None
    )
    severity = _top_severity(result)

    with st.container(border=True):
        cols = st.columns(6)
        cols[0].markdown(f"**Permit**  \n{result.permit_number}")
        cols[1].markdown(f"**Address**  \n{address}")
        cols[2].markdown(f"**Type**  \n{permit_type}")
        cols[3].markdown(f"**Status**  \n{status_desc}")
        cols[4].markdown(f"**Days in status**  \n{days if days is not None else '—'}")

        if severity is not None:
            color = SEVERITY_COLORS[severity]
            badge = (
                f'<span style="background-color:{color};color:white;padding:2px 10px;'
                f'border-radius:4px;font-weight:600">{SEVERITY_LABELS[severity]}</span>'
            )
            cols[5].markdown(f"**Top finding**  \n{badge}", unsafe_allow_html=True)
        else:
            icon = _OUTCOME_ICONS[result.outcome]
            cols[5].markdown(f"**Result**  \n{icon} {outcome_headline(result)}")

