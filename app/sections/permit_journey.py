"""Section C — permit journey. Renders only what Agent 1 actually
observed: no fabricated intermediate pre-issuance stages, no progress
stepper implying a known sequence between snapshots. Observed milestones,
observed inspection events, derived elapsed-time metrics, and explicit
not-observed notes are kept in visually distinct groups (UI_DESIGN.md §2,
decision 1).
"""

from __future__ import annotations

import streamlit as st

from formatting import MATCH_STATUS_LABELS
from permit_stall_finder.schema.journey import PermitJourney


def render(journey: PermitJourney) -> None:
    st.subheader("Permit journey")
    st.caption(MATCH_STATUS_LABELS.get(journey.match_status, journey.match_status.value))

    snapshot = journey.latest_snapshot
    if snapshot is None:
        st.write("No permit record was found to reconstruct a journey from.")
        return

    st.markdown(
        f"**{snapshot.permit_type}**"
        + (f" — {snapshot.permit_sub_type}" if snapshot.permit_sub_type else "")
    )
    if snapshot.work_description:
        st.caption(snapshot.work_description)

    st.markdown("**Observed milestones**")
    milestones = []
    if snapshot.submitted_date:
        milestones.append(("Submitted", snapshot.submitted_date))
    milestones.append((f"Current status — {snapshot.status_desc}", snapshot.status_date))
    if snapshot.issue_date:
        milestones.append(("Issued", snapshot.issue_date))
    if snapshot.cofo_date:
        milestones.append(("Certificate of Occupancy issued", snapshot.cofo_date))
    for label, dt in milestones:
        if dt is not None:
            st.markdown(f"- **{label}** — {dt.isoformat()}")

    if journey.inspection_events:
        st.markdown("**Observed inspection events**")
        st.dataframe(
            [
                {
                    "Date": e.inspection_date.isoformat(),
                    "Type": e.inspection_type,
                    "Result": e.inspection_result,
                }
                for e in journey.inspection_events
            ],
            hide_index=True,
            width="stretch",
        )

    derived = journey.derived
    if derived is not None:
        derived_rows = []
        if derived.days_submitted_to_issuance is not None:
            derived_rows.append(("Submitted → issued", f"{derived.days_submitted_to_issuance} days"))
        if derived.days_issuance_to_first_inspection is not None:
            derived_rows.append(
                ("Issued → first inspection", f"{derived.days_issuance_to_first_inspection} days")
            )
        if derived.total_observed_elapsed_days is not None:
            derived_rows.append(("Total observed span", f"{derived.total_observed_elapsed_days} days"))
        if derived_rows:
            st.markdown("**Derived elapsed-time metrics**")
            for label, value in derived_rows:
                st.markdown(f"- {label}: {value}")

    if journey.not_observed_notes:
        st.markdown("**Not observed**")
        for note in journey.not_observed_notes:
            st.markdown(f"- {note}")

    if journey.reconstruction_notes or journey.source_provenance:
        with st.expander("Technical details"):
            if journey.reconstruction_notes:
                st.markdown("Reconstruction notes:")
                for note in journey.reconstruction_notes:
                    st.markdown(f"- {note}")
            if journey.source_provenance:
                st.json(journey.source_provenance)
