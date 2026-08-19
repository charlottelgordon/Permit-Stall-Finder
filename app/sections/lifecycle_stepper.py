"""A compact "where is this permit in the big-picture process" stepper,
shown at the top of each permit card (drill_down.py's _render_one()) --
distinct from the finding cards below it, which explain *stalls*, not the
overall lifecycle. The 8 steps are the general LADBS permitting process
(zoning check through final inspection/closeout), not something this
app's own two datasets fully observe end to end -- see _infer_stage()'s
own docstring for exactly which steps are grounded in observed fields
versus structurally implied by later ones.
"""

from __future__ import annotations

import streamlit as st

from i18n import t
from permit_stall_finder.orchestration.pipeline import PermitAnalysisResult
from permit_stall_finder.schema.journey import MatchStatus

# Mirrors the _TERMINAL_STATUSES set already defined independently in
# stall_detector.py/cohort_populations.py -- same established pattern in
# this codebase (each module that needs this keeps its own copy rather
# than importing a shared one).
_TERMINAL_STATUSES = {
    "Permit Finaled",
    "CofO Issued",
    "CofC Issued",
    "Permit Closed",
    "Permit Expired",
    "Permit Withdrawn",
    "Permit Revoked",
}

_STEP_KEYS = [
    "lifecycle_step_1",
    "lifecycle_step_2",
    "lifecycle_step_3",
    "lifecycle_step_4",
    "lifecycle_step_5",
    "lifecycle_step_6",
    "lifecycle_step_7",
    "lifecycle_step_8",
]


def _infer_stage(result: PermitAnalysisResult) -> int | None:
    """0-based index into _STEP_KEYS for the step this permit has most
    recently reached. Returns None if there's nothing to place (permit
    not found in the source dataset at all).

    Grounded only in fields Agent 1 already observed, never a new
    judgment about where the permit "really" is:
    - Steps 1-3 (pre-submission: zoning check, gathering documents,
      submitting through ePlan) aren't independently observable in
      either dataset -- the permit record's own existence is the
      evidence they happened, so they're always shown complete once
      there's a record at all.
    - Step 4 (plan check + correction cycles) is "current" whenever
      issue_date is still null -- this dataset doesn't carry a field
      granular enough to place a still-unissued permit any more
      precisely within that phase than "not yet issued."
    - Step 5 (payment) isn't its own tracked field either, but LADBS
      requires payment before issuance, so an issue_date's presence is
      structural proof it happened -- not a guess about payment
      specifically.
    - Step 6 (issuance) is complete exactly when issue_date is present.
    - Step 7 (construction & inspections) is "current" once issued and
      not yet finaled -- individual inspection results are what the
      finding cards below already cover in detail; this stepper doesn't
      re-derive per-inspection sub-progress.
    - Step 8 (final inspection & closeout) is complete once the latest
      snapshot's status_desc is one of the dataset's own terminal
      values, or a cofo_date is present.
    """
    if result.journey.match_status == MatchStatus.PERMIT_NOT_FOUND:
        return None
    snapshot = result.journey.latest_snapshot
    if snapshot is None:
        return None

    if snapshot.status_desc in _TERMINAL_STATUSES or snapshot.cofo_date is not None:
        return 7
    if snapshot.issue_date is not None:
        return 6
    return 3


def render(result: PermitAnalysisResult) -> None:
    stage = _infer_stage(result)
    if stage is None:
        return

    business_unit = None
    snapshot = result.journey.latest_snapshot
    if stage == 3 and snapshot is not None and snapshot.business_unit:
        business_unit = snapshot.business_unit

    parts = ['<div class="lifecycle-stepper">']
    for i, key in enumerate(_STEP_KEYS):
        css_class = "complete" if i < stage else ("current" if i == stage else "upcoming")
        parts.append(
            f'<div class="lifecycle-step {css_class}">'
            f'<div class="lifecycle-step-dot">{i + 1}</div>'
            f'<div class="lifecycle-step-label">{t(key)}</div>'
            "</div>"
        )
        if i < len(_STEP_KEYS) - 1:
            connector_class = "complete" if i < stage else ""
            parts.append(f'<div class="lifecycle-step-connector {connector_class}"></div>')
    parts.append("</div>")

    caption = t("lifecycle_step_caption").format(n=stage + 1, total=len(_STEP_KEYS), label=t(_STEP_KEYS[stage]))
    if business_unit:
        caption += f" — {business_unit}"

    st.markdown("".join(parts), unsafe_allow_html=True)
    st.caption(caption)
