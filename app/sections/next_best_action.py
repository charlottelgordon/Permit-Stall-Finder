"""Next Best Action -- links for a user to dive deeper than this tool's
own summary goes, shown inside the left panel's collapsed "Resources"
section. Two things, both sourced from data the pipeline already
produced, never invented here:

1. A fixed recommendation to confirm this permit's status directly on
   LADBS's own public Permit & Inspection Report tool -- the same action
   Agent 3's own DISCLAIMER text and the PRD's guiding principles already
   point to ("does not replace confirming status directly with LADBS").
   These are LADBS's own general tool URLs (verified live against
   dbs.lacity.gov), not permit-specific deep links -- LADBS's own lookup
   tool requires the user to enter the permit number or address
   themselves, so this module never constructs or guesses a
   permit-specific URL.

2. A "talk to a person" block -- not just a link. LADBS_311_LINE and
   LADBS_OUTSIDE_LA_PHONE are LADBS's own general customer-service contact,
   verified live against dbs.lacity.gov/contact ("Call 3-1-1 (within the
   City of Los Angeles). Callers from outside Los Angeles can call
   (213) 473-3231") and independently confirmed on the cover page of
   LADBS's own Organizational Chart & Telephone Directory PDF (last
   updated 7/23/2026). LADBS_CASE_MANAGEMENT_CONTACT is a more specific
   escalation contact for a case that needs deeper attention than a
   status lookup -- Development Services Case Management, the division
   that same directory (Chart 3) identifies as handling case management
   for development services -- included because it is a publicly
   published department contact for exactly this kind of case-level
   question, not scraped or private data. Both numbers can change; the
   directory itself is dated, so this is presented as a starting point,
   not a guarantee the same person still holds that role.

Phase 15: the per-finding source links this module used to surface as a
flat "Learn more about your N grounded findings" list moved into each
finding's own card in stall_findings.py (a "Learn more about this
finding" line right on that finding, rather than a list here a user has
to cross-reference back to the right panel to make sense of).
"""

from __future__ import annotations

import streamlit as st

from i18n import t

# Verified live against dbs.lacity.gov -- LADBS's own public tools, not
# permit-specific deep links.
LADBS_PERMIT_STATUS_URL = "https://www.ladbsservices2.lacity.org/OnlineServices/?service=plr"
LADBS_RECORDS_SEARCH_URL = "https://ladbsdoc.lacity.org/"

# Verified live against dbs.lacity.gov/contact.
LADBS_311_LINE = "3-1-1 (within the City of Los Angeles)"
LADBS_OUTSIDE_LA_PHONE = "(213) 473-3231 (from outside Los Angeles)"

# From LADBS's own published Organizational Chart & Telephone Directory
# (dbs.lacity.gov/our-organization/organizational-chart, last updated
# 7/23/2026) -- Development Services Case Management, the division that
# directory identifies as handling case-management and preliminary
# review for development services.
LADBS_CASE_MANAGEMENT_CONTACT = (
    "Minye Pak, Sr. Structural Engineer -- Development Services Case Management -- "
    "(213) 482-6877 -- minye.pak@lacity.org"
)


def render() -> None:
    st.markdown(f"**{t('next_best_action')}**")
    st.markdown(
        f"→ [{t('confirm_status_link')}]({LADBS_PERMIT_STATUS_URL}) "
        f"— {t('authoritative_source_note')}"
    )
    st.markdown(
        f"→ [{t('search_records_link')}]({LADBS_RECORDS_SEARCH_URL})"
    )

    st.markdown(f"**{t('talk_to_a_person')}**")
    st.markdown(
        f"{t('call_prefix')} {LADBS_311_LINE} {t('or')} {LADBS_OUTSIDE_LA_PHONE} {t('call_line_text')}"
    )
    st.markdown(f"{t('deeper_attention_prefix')} {LADBS_CASE_MANAGEMENT_CONTACT}")

