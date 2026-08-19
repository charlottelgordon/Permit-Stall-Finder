"""Trends Dashboard -- reads the static artifact
scripts/generate_trends_artifact.py produces (config.TRENDS_ARTIFACT_PATH)
and renders three views: a year-over-year typical-duration trend, typical
duration by permit type for one chosen year, and combined delay-reason
counts across the selected years. Every number shown here already exists
on the artifact -- this module computes no new statistics of its own
beyond plain sums of already-tallied counts (view 3's combine-across-
types-and-years step, the same kind of arithmetic view 3 already did
across types alone before filters existed) -- extending stall_findings.py's
"no UI-composed analytical sentences from raw numbers" rule to "no
UI-computed statistics from raw numbers" for consistency. It never
synthesizes a new median/percentile across a range the artifact didn't
already compute one for.

A filter bar (permit type, year range) sits above all three views and
drives what each one shows -- the same "one filter state, everything
below reacts to it" principle a full filterable trends dashboard spec
called for; map view, click-to-filter charts, saved searches with
alerts, and a contractor/developer scope selector are deliberately not
part of this pass (each has a real blocker: no live per-permit
geography/status breakdown in the artifact yet, no Streamlit-native way
to do click-to-filter or a side drawer without a custom component, and
open questions about auth/notifications the spec itself hadn't answered
by the current pass).

Never live-queried: the deployed app has no persistent job scheduler or
filesystem guarantee across redeploys (see
scripts/generate_trends_artifact.py's own docstring), so this reads
whatever artifact shipped with the current deploy -- the disclaimer below
and the generated-at caption both exist so that's never hidden from the
user.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

import portfolio
from i18n import category_label, t
from permit_stall_finder import config
from permit_stall_finder.analytics.trends import TrendsArtifact, aggregate_bucket, load_artifact
from permit_stall_finder.schema.journey import PermitJourney
from permit_stall_finder.schema.stall_detection import StallAssessment, StallCategory
from sections import disclaimer, my_permits


@st.cache_data
def _load_artifact_cached(path: str) -> TrendsArtifact:
    return load_artifact(path)


def _build_personal_artifact(conn, uid: str) -> TrendsArtifact | None:
    """The same TrendsArtifact shape scripts/generate_trends_artifact.py
    produces, built live from just this uid's starred permits instead of
    a citywide sample -- reuses aggregate_bucket() unchanged (the exact
    function the offline script calls), grouping by (submitted year,
    permit type) the same way that script does. Returns None if there's
    nothing to build one from (no starred permits, or none resolved to a
    permit with a known submitted_date/permit_type)."""
    permit_numbers = my_permits.resolve_starred_permit_numbers(conn, uid)
    if not permit_numbers:
        return None

    batch = portfolio.run_batch(
        conn, permit_numbers, sample_size=config.DEFAULT_COHORT_SAMPLE_SIZE, progress=True
    )
    groups: dict[tuple[int, str], list[tuple[PermitJourney, StallAssessment]]] = defaultdict(list)
    for result in batch.results_by_permit.values():
        snapshot = result.journey.latest_snapshot
        if snapshot is None or snapshot.submitted_date is None:
            continue
        groups[(snapshot.submitted_date.year, snapshot.permit_type)].append(
            (result.journey, result.stall_assessment)
        )
    if not groups:
        return None

    buckets = [
        aggregate_bucket(year, permit_type, n_sampled=len(pairs), journeys_and_assessments=pairs)
        for (year, permit_type), pairs in groups.items()
    ]
    years = sorted({b.year for b in buckets})
    return TrendsArtifact(
        generated_at=datetime.now(timezone.utc),
        start_year=years[0],
        end_year=years[-1],
        sample_size_per_bucket=len(permit_numbers),
        cohort_sample_size=config.DEFAULT_COHORT_SAMPLE_SIZE,
        permit_types=sorted({b.permit_type for b in buckets}),
        buckets=buckets,
    )


def _bucket_for(artifact: TrendsArtifact, year: int, permit_type: str):
    return next(
        (b for b in artifact.buckets if b.year == year and b.permit_type == permit_type), None
    )


def _duration_cell(days: float | None) -> str:
    return f"{days:.0f} {t('days_suffix')}" if days is not None else "—"


def render(conn=None, uid: str | None = None) -> None:
    st.subheader(t("trends_dashboard_header"))

    scope = st.radio(
        t("trends_scope_label"),
        ["citywide", "my_permits"],
        format_func=lambda v: t("trends_scope_citywide") if v == "citywide" else t("trends_scope_my_permits"),
        horizontal=True,
        key="trends_scope",
    )

    if scope == "my_permits":
        if not uid:
            st.info(t("my_permits_no_uid"))
            return
        artifact = _build_personal_artifact(conn, uid)
        if artifact is None:
            st.info(t("trends_my_permits_empty"))
            return
        st.caption(t("trends_my_permits_caption").format(n=artifact.sample_size_per_bucket))
    else:
        try:
            artifact = _load_artifact_cached(config.TRENDS_ARTIFACT_PATH)
        except FileNotFoundError:
            st.info(t("trends_no_artifact"))
            return
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

    # --- Filter bar: drives every view below --------------------------
    st.markdown(f"**{t('trends_filters_header')}**")
    filter_type_col, filter_year_col = st.columns(2)
    with filter_type_col:
        selected_types = st.multiselect(
            t("trends_permit_type_label"), permit_types, default=permit_types, key="trends_filter_types"
        )
    with filter_year_col:
        if len(years) > 1:
            year_range = st.select_slider(
                t("trends_date_range_label"), options=years, value=(years[0], years[-1]), key="trends_filter_years"
            )
        else:
            st.caption(f"{t('trends_date_range_label')}: {years[0]}")
            year_range = (years[0], years[0])

    # Empty selection reads as "nothing chosen yet," not "filter out
    # everything" -- falls back to every type, same spirit as leaving a
    # filter untouched.
    active_types = selected_types or permit_types
    active_years = [y for y in years if year_range[0] <= y <= year_range[1]]

    st.divider()

    if not active_types or not active_years:
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
        selected_type = st.selectbox(t("trends_permit_type_label"), active_types, key="trends_type_select")
    with col_metric:
        metric_label = st.selectbox(
            t("trends_metric_label"), list(metric_options.keys()), key="trends_metric_select"
        )
    metric_field = metric_options[metric_label]

    trend_values: dict[str, float] = {}
    for year in active_years:
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
        t("trends_year_label"), active_years, index=len(active_years) - 1, key="trends_duration_year"
    )
    duration_rows = []
    for permit_type in active_types:
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

    # --- View 3: most common delay reasons, combined across the
    # selected years (not just one) -- a plain sum of already-tallied
    # counts across both types and years, the same safe arithmetic this
    # view already did across types alone before the year-range filter
    # existed; never a synthesized rate or median across the range. ----
    st.markdown(f"**{t('trends_delay_reasons_header')}**")
    if active_years[0] != active_years[-1]:
        st.caption(t("trends_delay_reasons_range_caption").format(start=active_years[0], end=active_years[-1]))
    combined_counts: dict[str, int] = {}
    for permit_type in active_types:
        for year in active_years:
            bucket = _bucket_for(artifact, year, permit_type)
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
