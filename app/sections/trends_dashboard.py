"""Trends Dashboard -- reads the static artifact
scripts/generate_trends_artifact.py produces (config.TRENDS_ARTIFACT_PATH)
and renders three views: a year-over-year typical-duration trend, typical
duration by permit type for one chosen year, and that year's most common
delay reasons. Every number shown here already exists on the artifact --
this module computes no new statistics of its own, extending
stall_findings.py's "no UI-composed analytical sentences from raw
numbers" rule to "no UI-computed statistics from raw numbers" for
consistency.

Never live-queried: the deployed app has no persistent job scheduler or
filesystem guarantee across redeploys (see
scripts/generate_trends_artifact.py's own docstring), so this reads
whatever artifact shipped with the current deploy -- the disclaimer below
and the generated-at caption both exist so that's never hidden from the
user.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from i18n import category_label, t
from permit_stall_finder import config
from permit_stall_finder.analytics.trends import TrendsArtifact, load_artifact
from permit_stall_finder.schema.stall_detection import StallCategory
from sections import disclaimer


@st.cache_data
def _load_artifact_cached(path: str) -> TrendsArtifact:
    return load_artifact(path)


def _bucket_for(artifact: TrendsArtifact, year: int, permit_type: str):
    return next(
        (b for b in artifact.buckets if b.year == year and b.permit_type == permit_type), None
    )


def _duration_cell(days: float | None) -> str:
    return f"{days:.0f} {t('days_suffix')}" if days is not None else "—"


def render() -> None:
    try:
        artifact = _load_artifact_cached(config.TRENDS_ARTIFACT_PATH)
    except FileNotFoundError:
        st.subheader(t("trends_dashboard_header"))
        st.info(t("trends_no_artifact"))
        return

    st.subheader(t("trends_dashboard_header"))
    st.caption(
        t("trends_generated_caption").format(
            n=artifact.sample_size_per_bucket,
            generated=artifact.generated_at.strftime("%Y-%m-%d"),
        )
    )

    years = sorted({b.year for b in artifact.buckets})
    permit_types = artifact.permit_types
    if not years or not permit_types:
        st.info(t("trends_no_data_for_selection"))
        disclaimer.render(t("trends_disclaimer_text"))
        return

    # --- View 1: year-over-year duration trend -----------------------
    st.markdown(f"**{t('trends_year_over_year_header')}**")
    metric_options = {
        t("trends_metric_issuance"): "median_days_submitted_to_issuance",
        t("trends_metric_first_inspection"): "median_days_issuance_to_first_inspection",
        t("trends_metric_inter_inspection"): "median_inter_inspection_gap_days",
    }
    col_type, col_metric = st.columns(2)
    with col_type:
        selected_type = st.selectbox(t("trends_permit_type_label"), permit_types, key="trends_type_select")
    with col_metric:
        metric_label = st.selectbox(
            t("trends_metric_label"), list(metric_options.keys()), key="trends_metric_select"
        )
    metric_field = metric_options[metric_label]

    trend_values: dict[str, float] = {}
    for year in years:
        bucket = _bucket_for(artifact, year, selected_type)
        value = getattr(bucket, metric_field) if bucket else None
        if value is not None:
            trend_values[str(year)] = value
    if trend_values:
        st.line_chart(pd.Series(trend_values, name=metric_label))
    else:
        st.caption(t("trends_no_data_for_selection"))

    st.divider()

    # --- View 2: typical duration by permit type, one year -----------
    st.markdown(f"**{t('trends_duration_by_type_header')}**")
    selected_year = st.selectbox(
        t("trends_year_label"), years, index=len(years) - 1, key="trends_duration_year"
    )
    duration_rows = []
    for permit_type in permit_types:
        bucket = _bucket_for(artifact, selected_year, permit_type)
        if bucket is None:
            continue
        duration_rows.append(
            {
                t("col_permit_type"): permit_type,
                t("trends_metric_issuance"): _duration_cell(bucket.median_days_submitted_to_issuance),
                t("trends_metric_first_inspection"): _duration_cell(
                    bucket.median_days_issuance_to_first_inspection
                ),
                t("trends_metric_inter_inspection"): _duration_cell(bucket.median_inter_inspection_gap_days),
            }
        )
    if duration_rows:
        st.dataframe(duration_rows, hide_index=True, width="stretch")
    else:
        st.caption(t("trends_no_data_for_selection"))

    st.divider()

    # --- View 3: most common delay reasons, selected year --------------
    st.markdown(f"**{t('trends_delay_reasons_header')}**")
    combined_counts: dict[str, int] = {}
    for permit_type in permit_types:
        bucket = _bucket_for(artifact, selected_year, permit_type)
        if bucket is None:
            continue
        for category_value, count in bucket.stall_category_counts.items():
            combined_counts[category_value] = combined_counts.get(category_value, 0) + count

    if combined_counts:
        ranked = sorted(combined_counts.items(), key=lambda kv: kv[1], reverse=True)
        for category_value, count in ranked:
            label = category_label(StallCategory(category_value))
            st.markdown(f"- **{label}** — {count} {t('trends_delay_occurrences_suffix')}")
    else:
        st.caption(t("trends_no_data_for_selection"))

    disclaimer.render(t("trends_disclaimer_text"))
