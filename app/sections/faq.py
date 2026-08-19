"""FAQ tab -- general reference content plus an infographic showing how
long a permit has typically taken at each phase of the LADBS process.

The infographic groups the 8-step process (same steps
lifecycle_stepper.py uses on each permit card) into four phases and
annotates only the phases the Trends Dashboard artifact actually has a
real median for -- config.TRENDS_ARTIFACT_PATH's medians cover
submission-to-issuance (spanning steps 4-6 as one combined interval, not
separable further with what's currently computed) and issuance-to-first-
inspection / between-inspections (step 7). Steps 1-3 (pre-submission) and
step 8 (finalization) have no duration metric in the artifact at all, and
are shown as such rather than filled in with an invented number -- same
"no UI-computed statistics, no speculation" rule trends_dashboard.py
already follows.
"""

from __future__ import annotations

import streamlit as st

from i18n import t
from permit_stall_finder import config
from permit_stall_finder.analytics.trends import load_artifact


@st.cache_data
def _load_artifact_cached(path: str):
    return load_artifact(path)


def _duration_text(days: float | None) -> str:
    if days is None:
        return t("faq_infographic_no_data")
    return f"{days:.0f} {t('days_suffix')}"


def _render_infographic() -> None:
    st.markdown(f"**{t('faq_infographic_header')}**")
    st.caption(t("faq_infographic_subtext"))

    try:
        artifact = _load_artifact_cached(config.TRENDS_ARTIFACT_PATH)
    except FileNotFoundError:
        st.info(t("trends_no_artifact"))
        return

    years = sorted({b.year for b in artifact.buckets})
    permit_types = artifact.permit_types
    if not years or not permit_types:
        st.info(t("trends_no_data_for_selection"))
        return

    col_type, col_year = st.columns(2)
    with col_type:
        selected_type = st.selectbox(t("trends_permit_type_label"), permit_types, key="faq_infographic_type")
    with col_year:
        selected_year = st.selectbox(t("trends_year_label"), years, index=len(years) - 1, key="faq_infographic_year")

    bucket = next(
        (b for b in artifact.buckets if b.year == selected_year and b.permit_type == selected_type), None
    )

    phases = [
        (
            t("faq_phase_1_title"),
            t("faq_phase_1_steps"),
            None,
        ),
        (
            t("faq_phase_2_title"),
            t("faq_phase_2_steps"),
            _duration_text(bucket.median_days_submitted_to_issuance if bucket else None),
        ),
        (
            t("faq_phase_3_title"),
            t("faq_phase_3_steps"),
            t("faq_phase_3_duration").format(
                first=_duration_text(bucket.median_days_issuance_to_first_inspection if bucket else None),
                between=_duration_text(bucket.median_inter_inspection_gap_days if bucket else None),
            ),
        ),
        (
            t("faq_phase_4_title"),
            t("faq_phase_4_steps"),
            None,
        ),
    ]

    for title, steps, duration in phases:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(steps)
            if duration:
                st.markdown(f"{t('faq_infographic_typical_label')} {duration}")
            else:
                st.caption(t("faq_infographic_no_data"))

    st.caption(t("trends_disclaimer_text"))


def render() -> None:
    st.subheader(t("nav_faq"))

    _render_infographic()

    st.divider()
    st.markdown(f"**{t('faq_questions_header')}**")
    for q_key, a_key in _FAQ_ENTRIES:
        with st.expander(t(q_key)):
            st.write(t(a_key))


_FAQ_ENTRIES = [
    ("faq_q_data_source", "faq_a_data_source"),
    ("faq_q_official", "faq_a_official"),
    ("faq_q_severity", "faq_a_severity"),
    ("faq_q_no_guidance", "faq_a_no_guidance"),
    ("faq_q_freshness", "faq_a_freshness"),
]
