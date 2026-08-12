"""Persona presets for the top-of-page persona switcher.

Presentation-only: a persona selects which view (portfolio triage vs.
single-permit deep dive) opens by default and a short framing caption. It
never changes what Agents 1-3 compute -- see research/UI_DESIGN.md's
framing that everything under app/ is a thin consumer of
PermitAnalysisResult, never a source of new analysis. Persona identity
only affects which existing view is shown first and how it's captioned.

The four personas here mirror the ones discussed with the product owner
alongside the PRD's named primary user ("developers and general
contractors tracking active LA building permits") and its TBD secondary
personas (expediters, architects, property owners).
"""

from __future__ import annotations

from dataclasses import dataclass

# "portfolio" -> app/portfolio.py's batch triage table.
# "single" -> the original single-permit deep-dive form.
ViewName = str


@dataclass(frozen=True)
class Persona:
    persona_id: str
    icon: str
    label: str
    tagline: str
    default_view: ViewName


PERSONAS: list[Persona] = [
    Persona(
        persona_id="contractor",
        icon="\U0001F3D7️",
        label="General Contractor",
        tagline="Scanning active projects for the ones that need attention today.",
        default_view="portfolio",
    ),
    Persona(
        persona_id="owner",
        icon="\U0001F3E0",
        label="Property Owner / Developer",
        tagline="Tracking one project closely and deciding whether to escalate.",
        default_view="single",
    ),
    Persona(
        persona_id="expediter",
        icon="\U0001F4CB",
        label="Permit Expediter",
        tagline="Explaining delays across multiple clients' permits.",
        default_view="portfolio",
    ),
    Persona(
        persona_id="architect",
        icon="✏️",
        label="Architect / Designer of Record",
        tagline="Checking whether a stall traces back to plan-check corrections.",
        default_view="single",
    ),
]

DEFAULT_PERSONA_ID = "owner"

_BY_ID: dict[str, Persona] = {p.persona_id: p for p in PERSONAS}


def get_persona(persona_id: str) -> Persona:
    """Falls back to the first persona if persona_id is somehow unknown
    (e.g. stale session state after a code change) rather than raising."""
    return _BY_ID.get(persona_id, PERSONAS[0])

