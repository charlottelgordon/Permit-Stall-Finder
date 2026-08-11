"""Derived status-transition view over accumulated permit_snapshots.

permit_snapshots is append-only and intentionally includes repeated
snapshots where nothing changed (see PermitSnapshot's docstring) — that
repetition is itself evidence a published state persisted. This module
collapses a permit's snapshot sequence into ObservedTransitions, e.g.:

    PC Approved -> Ready to Issue -> Issued

collapse_snapshots_to_transitions() only groups snapshots we actually
recorded. It never inserts a transition that wasn't backed by at least one
observed snapshot, and a single-snapshot history correctly produces a
single-element list rather than implying anything about what came before.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from permit_stall_finder.schema.journey import PermitSnapshot


@dataclass(frozen=True)
class ObservedTransition:
    """One run of consecutive snapshots sharing the same status_desc."""

    status_desc: str
    source_status_date: date | None
    """The source's own status_date for this state, as reported on the
    first snapshot in this run. This is when the source claims the status
    was reached — not when we first polled it."""
    first_observed_at: datetime
    """Our clock: the earliest snapshot in our own history showing this
    status."""
    last_observed_at: datetime
    """Our clock: the latest snapshot in our own history still showing
    this status. Equals first_observed_at when we've only observed it once."""
    observation_count: int
    """How many snapshots recorded this status. >1 supports a claim that
    the status persisted across polling dates; ==1 does not."""

    @property
    def confirmed_by_repeated_observation(self) -> bool:
        return self.observation_count > 1

    def describe(self) -> str:
        """Human-readable summary that respects the weak/strong distinction:
        a single observation only supports "current published status is X
        as of status_date Y" — never "has continuously remained in X since
        Y," which requires repeated observation."""
        status_date_part = (
            f", reported by the source as of {self.source_status_date}"
            if self.source_status_date
            else ""
        )
        if self.confirmed_by_repeated_observation:
            return (
                f"Status '{self.status_desc}' confirmed present across "
                f"{self.observation_count} observations from "
                f"{self.first_observed_at.date()} to {self.last_observed_at.date()}"
                f"{status_date_part}."
            )
        return (
            f"Current published status is '{self.status_desc}'"
            f"{status_date_part}. Observed once "
            f"({self.first_observed_at.date()}); persistence beyond this "
            f"observation is not yet confirmed by repeated polling."
        )


def collapse_snapshots_to_transitions(
    snapshots: list[PermitSnapshot],
) -> list[ObservedTransition]:
    """snapshots must be ordered oldest -> newest (by observed_at)."""
    if not snapshots:
        return []

    ordered = sorted(snapshots, key=lambda s: s.observed_at)
    transitions: list[ObservedTransition] = []
    run: list[PermitSnapshot] = [ordered[0]]

    def flush(run_snaps: list[PermitSnapshot]) -> ObservedTransition:
        first, last = run_snaps[0], run_snaps[-1]
        return ObservedTransition(
            status_desc=first.status_desc,
            source_status_date=first.status_date,
            first_observed_at=first.observed_at,
            last_observed_at=last.observed_at,
            observation_count=len(run_snaps),
        )

    for snap in ordered[1:]:
        if snap.status_desc == run[-1].status_desc:
            run.append(snap)
        else:
            transitions.append(flush(run))
            run = [snap]
    transitions.append(flush(run))

    return transitions
