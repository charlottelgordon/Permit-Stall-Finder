"""Section C — permit journey. Renders only what Agent 1 actually
observed: no fabricated intermediate pre-issuance stages, no progress
stepper implying a known sequence between snapshots. Observed milestones,
observed inspection events, derived elapsed-time metrics, and explicit
not-observed notes are kept in visually distinct groups (UI_DESIGN.md §2,
decision 1).
"""

from __future__ import annotations

import streamlit as st

from i18n import match_status_label, t
from permit_stall_finder.schema.journey import PermitJourney


def render(journey: PermitJourney) -> None:
    st.subheader(t("permit_journey_header"))
    st.caption(match_status_label(journey.match_status))

    snapshot = journey.latest_snapshot
    if snapshot is None:
        st.write(t("no_journey_record"))
        return

    st.markdown(
        f"**{snapshot.permit_type}**"
        + (f" — {snapshot.permit_sub_type}" if snapshot.permit_sub_type else "")
    )
    if snapshot.work_description:
        st.caption(snapshot.work_description)

    st.markdown(f"**{t('observed_milestones')}**")
    milestones = []
    if snapshot.submitted_date:
        milestones.append((t("submitted"), snapshot.submitted_date))
    milestones.append((f"{t('current_status_prefix')} — {snapshot.status_desc}", snapshot.status_date))
    if snapshot.issue_date:
        milestones.append((t("issued"), snapshot.issue_date))
    if snapshot.cofo_date:
        milestones.append((t("cofo_issued"), snapshot.cofo_date))
    for label, dt in milestones:
        if dt is not None:
            st.markdown(f"- **{label}** — {dt.isoformat()}")

    if journey.inspection_events:
        st.markdown(f"**{t('observed_inspections')}**")
        st.dataframe(
            [
                {
                    t("col_date"): e.inspection_date.isoformat(),
                    t("col_type"): e.inspection_type,
                    t("col_result"): e.inspection_result,
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
            derived_rows.append(
                (t("submitted_to_issued"), f"{derived.days_submitted_to_issuance} {t('days_suffix')}")
            )
        if derived.days_issuance_to_first_inspection is not None:
            derived_rows.append(
                (t("issued_to_first_inspection"), f"{derived.days_issuance_to_first_inspection} {t('days_suffix')}")
            )
        if derived.total_observed_elapsed_days is not None:
            derived_rows.append(
                (t("total_observed_span"), f"{derived.total_observed_elapsed_days} {t('days_suffix')}")
            )
        if derived_rows:
            st.markdown(f"**{t('derived_metrics')}**")
            for label, value in derived_rows:
                st.markdown(f"- {label}: {value}")

    if journey.not_observed_notes:
        st.markdown(f"**{t('not_observed')}**")
        for note in journey.not_observed_notes:
            st.markdown(f"- {note}")

    if journey.reconstruction_notes or journey.source_provenance:
        with st.expander(t("technical_details")):
            if journey.reconstruction_notes:
                st.markdown(t("reconstruction_notes"))
                for note in journey.reconstruction_notes:
                    st.markdown(f"- {note}")
            if journey.source_provenance:
                st.json(journey.source_provenance)
