"""Quick-glance overview -- the left-panel summary block of the two-panel
drill-down layout (Phase 11 redesign), stacked above Permit Journey/Other
Permits/Resources/the map. Every field is read directly off an
already-complete PermitAnalysisResult (address/type/status/issuance/last-
update via portfolio.summarize_result(), the same computation the results
table's own columns already use, so this block can't drift out of sync
with what the table shows for the same permit).

Was previously a horizontal st.columns(6) strip; the severity-count blue
banner that used to sit near the top of the tab (section B,
top_level_result.py) is now rendered once, above both panels, by
drill_down.py directly -- this block only repeats the identifying facts
plus the full list of this permit's own findings, not the tab-wide
severity summary.

"Total Number of Findings" deliberately shows only a count, not a
per-finding bullet list -- the individual findings are already fully
covered by the finding cards in the right panel, and listing them here
too was flagged as a third repeat of the same information.

Phase 16: "Type" now also carries the match-status line and work
description that used to open permit_journey.py's own view (moved, not
copied -- permit_journey.py no longer renders them).

Combined "Status" / "Issuance status" / "Last status update" into one
"Permit status" paragraph per explicit request -- three closely-related
facts about the same thing that read better as one narrative sentence
than three separately-labeled fields.
"""

from __future__ import annotations

import streamlit as st

import portfolio
from i18n import match_status_label, outcome_headline, status_last_reported_changed_phrase, t
from permit_stall_finder.orchestration.pipeline import AnalysisOutcome, PermitAnalysisResult

_OUTCOME_ICONS = {
    AnalysisOutcome.NO_MATERIAL_STALL_DETECTED: "✅",
    AnalysisOutcome.INSUFFICIENT_EVIDENCE: "🔍",
    AnalysisOutcome.STALL_DETECTED: "📋",
}


def _type_block(result: PermitAnalysisResult, row: portfolio.PortfolioRow) -> str:
    """Everything under "Type": match status (Phase 16 -- moved here
    from permit_journey.py's own opening caption), permit type + sub
    type, and the work description, e.g. "Issued, with inspections on
    record" / "Bldg-New — 1 or 2 Family Dwelling" / "(N) 2-story SFD &
    attached 2-car garage" as three stacked lines under one label."""
    snapshot = result.journey.latest_snapshot
    lines = [match_status_label(result.journey.match_status)]
    permit_type_line = row.permit_type
    if snapshot and snapshot.permit_sub_type:
        permit_type_line += f" — {snapshot.permit_sub_type}"
    lines.append(permit_type_line)
    if snapshot and snapshot.work_description:
        lines.append(snapshot.work_description)
    return "  \n".join(lines)


def _permit_status_block(row: portfolio.PortfolioRow) -> str:
    """Everything under "Permit status": issuance status, the permit's
    current status, and when that status was last reported changed, as
    one narrative paragraph, e.g. "Permit has been issued. Certificate
    of Occupancy issued. This permit's status was last reported as
    changed 2y 2m 3d ago." The third sentence is omitted (not shown as
    a broken fragment) when there's no status_date to compute it from."""
    sentences = [f"{row.issuance_status}.", f"{row.status_desc}."]
    if row.days_since_status_change is not None:
        sentences.append(status_last_reported_changed_phrase(row.days_since_status_change))
    return " ".join(sentences)


def render(result: PermitAnalysisResult) -> None:
    row = portfolio.summarize_result(result)
    detections = result.stall_assessment.detections

    with st.container(border=True):
        st.markdown(f"**{t('qg_address')}**  \n{row.address}")
        st.markdown(f"**{t('qg_type')}**  \n{_type_block(result, row)}")
        st.markdown(f"**{t('qg_permit_status_header')}**  \n{_permit_status_block(row)}")

        if detections:
            st.markdown(f"**{t('qg_top_findings')}**  \n{len(detections)}")
        else:
            icon = _OUTCOME_ICONS[result.outcome]
            st.markdown(f"**{t('qg_result')}**  \n{icon} {outcome_headline(result)}")

