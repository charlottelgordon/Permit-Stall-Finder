"""Section 1 ("what the data shows") for every stall category. Extends
Agent 2's render_dwell_statement (schema/stall_detection.py) to all 9
categories, and carries forward its structural guarantees:

- benchmark_semantics == ACTIVE_PEER_DWELL never produces "normally
  takes"/"typically completes" language -- only "longer than X% of
  permits currently observed in this status."
- benchmark_semantics == COMPLETED_INTERVAL may describe the interval
  relative to completed comparable intervals ("ranked at the Nth
  percentile of M comparable completed intervals").
- interval_state == ONGOING never implies the eventual duration is known.
- Severity is stated as Agent 2's own statistical-tier label, never
  translated into a judgment ("this is a serious problem") -- the
  percentile_rank number already carries the magnitude; severity is named,
  not re-interpreted.

This module is a pure function of StallDetection fields. It never touches
the knowledge base and never calls an LLM -- see AGENT3_DESIGN.md §4/§5.
"""

from __future__ import annotations

from permit_stall_finder.schema.stall_detection import (
    BenchmarkSemantics,
    DelayStallDetection,
    FrictionStallDetection,
    IntervalState,
    StallCategory,
)

_FRICTION_FAMILY_LABEL = {
    StallCategory.REPEATED_CORRECTIONS: "corrections-related",
    StallCategory.REPEATED_NOT_READY_OUTCOMES: "not-ready-related",
    StallCategory.REPEATED_CANCELLATIONS: "cancelled-related",
}


def _ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def render_what_the_data_shows(detection: DelayStallDetection | FrictionStallDetection) -> str:
    if isinstance(detection, FrictionStallDetection):
        return _render_friction_facts(detection)
    return _render_delay_facts(detection)


def _delay_lead_sentence(d: DelayStallDetection) -> str:
    if d.category == StallCategory.PRE_ISSUANCE_STATUS_DWELL:
        return f"{d.elapsed_days} days have elapsed since the published '{d.stage_label}' status_date."
    if d.category == StallCategory.ISSUANCE_TO_FIRST_INSPECTION_GAP:
        return f"There were {d.elapsed_days} days between permit issuance and the first recorded substantive inspection."
    if d.category == StallCategory.NO_INSPECTION_SINCE_ISSUANCE:
        return f"{d.elapsed_days} days have elapsed since issuance with no inspection record found."
    if d.category == StallCategory.INTER_INSPECTION_GAP:
        return f"There were {d.elapsed_days} days between two recorded inspections ({d.stage_label})."
    if d.category == StallCategory.INACTIVITY_SINCE_LAST_INSPECTION:
        return (
            f"{d.elapsed_days} days have elapsed since the most recent recorded "
            f"inspection ('{d.stage_label}'), with no further inspection recorded since."
        )
    if d.category == StallCategory.FINALIZATION_GAP:
        return (
            f"There were {d.elapsed_days} days between the last recorded substantive "
            f"inspection and this permit's terminal outcome ({d.stage_label})."
        )
    raise ValueError(f"render_what_the_data_shows: unhandled delay category {d.category!r}")


def _render_delay_facts(d: DelayStallDetection) -> str:
    statement = _delay_lead_sentence(d)

    if d.percentile_rank is not None:
        if d.cohort.benchmark_semantics == BenchmarkSemantics.ACTIVE_PEER_DWELL:
            statement += (
                f" This elapsed time is longer than {d.percentile_rank:.0f}% of "
                "currently observed comparable permits with the same published status."
            )
        elif d.cohort.benchmark_semantics == BenchmarkSemantics.COMPLETED_INTERVAL:
            statement += (
                f" This interval ranked at approximately the {_ordinal(round(d.percentile_rank))} "
                f"percentile of {d.cohort.n} comparable completed intervals."
            )

    if d.interval_state == IntervalState.ONGOING:
        statement += " This interval has not closed -- the eventual total is not known."

    if d.status_persistence_confirmed_by_repeated_observation:
        statement += " This status has been confirmed present across repeated observation."

    statement += f" Agent 2 classified this measurement in its '{d.severity.value}' statistical tier."
    return statement


def _render_friction_facts(d: FrictionStallDetection) -> str:
    family_label = _FRICTION_FAMILY_LABEL[d.category]
    statement = (
        f"There were {d.observed_count} {family_label} outcome(s) out of "
        f"{d.total_inspection_opportunities} substantive inspection(s) recorded"
    )
    if d.correction_rate is not None:
        statement += f" ({d.correction_rate * 100:.1f}%)"
    statement += "."

    if d.percentile_rank is not None:
        statement += (
            f" This count ranked at approximately the {_ordinal(round(d.percentile_rank))} percentile "
            f"of {d.cohort.n} comparable {d.lifecycle_stage.value} permits."
        )

    statement += f" Agent 2 classified this measurement in its '{d.severity.value}' statistical tier."
    return statement
