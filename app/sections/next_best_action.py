"""Next Best Action -- links for a user to dive deeper than this tool's
own summary goes. Two kinds of link, both sourced from data the pipeline
already produced, never invented here:

1. A fixed recommendation to confirm this permit's status directly on
   LADBS's own public Permit & Inspection Report tool -- the same action
   Agent 3's own DISCLAIMER text and the PRD's guiding principles already
   point to ("does not replace confirming status directly with LADBS").
   These are LADBS's own general tool URLs (verified live against
   dbs.lacity.gov), not permit-specific deep links -- LADBS's own lookup
   tool requires the user to enter the permit number or address
   themselves, so this module never constructs or guesses a
   permit-specific URL.

2. Per-finding source links, read from the same KnowledgeBaseEntry.sources
   list stall_findings.py's "Source & grounding" expander already shows
   via formatting.kb_entry_by_id() -- surfaced here as a flatter,
   above-the-fold list so a user isn't required to open every finding
   card's expander individually to find them.
"""

from __future__ import annotations

import streamlit as st

from formatting import CATEGORY_LABELS, kb_entry_by_id
from permit_stall_finder.knowledge_base.loader import KnowledgeBase
from permit_stall_finder.orchestration.pipeline import PermitAnalysisResult
from permit_stall_finder.schema.developer_explanation import GroundingStatus

# Verified live against dbs.lacity.gov -- LADBS's own public tools, not
# permit-specific deep links.
LADBS_PERMIT_STATUS_URL = "https://www.ladbsservices2.lacity.org/OnlineServices/?service=plr"
LADBS_RECORDS_SEARCH_URL = "https://ladbsdoc.lacity.org/"


def render(result: PermitAnalysisResult, kb: KnowledgeBase) -> None:
    st.markdown("**Next best action**")
    st.markdown(
        f"→ [Confirm this permit's current status directly on LADBS]({LADBS_PERMIT_STATUS_URL}) "
        "— the authoritative source; this tool is informational only."
    )
    st.markdown(
        f"→ [Search LADBS's online building records for this address]({LADBS_RECORDS_SEARCH_URL})"
    )

    seen_entry_ids: set[str] = set()
    source_links: list[tuple[str, str, str]] = []  # (category label, source title, url)
    for explanation in result.developer_explanations.explanations:
        if explanation.grounding_status != GroundingStatus.GROUNDED:
            continue
        entry = kb_entry_by_id(kb, explanation.knowledge_base_entry_id)
        if entry is None or entry.entry_id in seen_entry_ids:
            continue
        seen_entry_ids.add(entry.entry_id)
        for source in entry.sources:
            source_links.append(
                (CATEGORY_LABELS[explanation.stall_category], source.title, source.url)
            )

    if source_links:
        with st.expander(f"Learn more about your {len(source_links)} grounded finding(s)"):
            for category_label, title, url in source_links:
                st.markdown(f"- **{category_label}**: [{title}]({url})")

