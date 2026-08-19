"""Persona-selection gate shown on first load, before the search bar --
lets a user identify as Contractor / Developer / Government Employee /
Individual by clicking one of four bordered card buttons, each carrying
a small Material Symbols icon via st.button's own icon= parameter (no
raw HTML needed -- st.button doesn't support markup in its label, so
this is the one distinguishing touch available without restructuring
away from a plain button). Cards are styled via streamlit_app.py's
stylesheet, scoped to the "persona_picker_row" container key so it
doesn't affect any other button on the page. Purely a display gate for
now (which screen shows next), not yet used to vary any content --
storing the choice in st.session_state.selected_persona is enough for
the current request; a future personalization pass can read that value
without any changes here.

Previously these were image-buttons; switched back to plain buttons per
explicit request -- the imagery read as overwhelming. There was also
briefly a small "Role: X ⌄" control next to the EN/ES toggle for
switching roles without leaving the search page -- removed per explicit
request; the Home link (streamlit_app.py's header) is the only way back
to this picker now, which resets the whole session including the
selected role.

The word "persona" is internal terminology only -- never rendered in
any user-facing string here (see i18n.py's persona_* keys, none of
which say the word "persona" itself).
"""

from __future__ import annotations

import streamlit as st

from i18n import t
from permit_stall_finder.storage import search_counter

# (session-state value, i18n label key, Material Symbols icon shortcode)
_PERSONAS = [
    ("contractor", "persona_contractor", ":material/construction:"),
    ("developer", "persona_developer", ":material/code:"),
    ("government_employee", "persona_government_employee", ":material/account_balance:"),
    ("individual", "persona_individual", ":material/person:"),
]


def render(conn) -> None:
    """The picker itself -- shown instead of the search bar until a
    persona is chosen."""
    # Civic-impact stat: total search *actions* run on this app (see
    # storage/search_counter.py's own docstring for why this is a
    # separate append-only tally from search_history's distinct-value
    # table). Hidden at 0 rather than showing "0 searches run" -- that
    # reads as evidence of nothing happening, not as a real stat; it
    # only shows once there's an actual number to be proud of. Note for
    # whoever's reading this later: this resets to 0 on every redeploy,
    # the same known limitation every other table in this storage layer
    # already has (the local DuckDB file is gitignored and ephemeral).
    search_count = search_counter.count_search_events(conn)
    if search_count > 0:
        stat_text = t("impact_stat_text").format(
            n=f"{search_count:,}", plural="" if search_count == 1 else "s"
        )
        st.markdown(
            f'<div class="impact-stat-wrap"><span class="impact-stat">{stat_text}</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<p class="persona-picker-heading">{t("persona_picker_heading")}</p>',
        unsafe_allow_html=True,
    )
    with st.container(key="persona_picker_row"):
        cols = st.columns(4, gap="small")
        for col, (persona_key, label_key, icon) in zip(cols, _PERSONAS):
            with col:
                if st.button(t(label_key), icon=icon, key=f"persona_select_{persona_key}", width="stretch"):
                    st.session_state.selected_persona = persona_key
                    st.rerun()
