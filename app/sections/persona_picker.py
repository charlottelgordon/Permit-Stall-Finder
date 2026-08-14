"""Persona-selection gate shown on first load, before the search bar --
lets a user identify as Contractor / Developer / Government Employee /
Individual by clicking one of four plain text buttons (styled orange
with blue text via streamlit_app.py's stylesheet, scoped to the
"persona_picker_row" container key so it doesn't affect any other
button on the page). Purely a display gate for now (which screen shows
next), not yet used to vary any content -- storing the choice in
st.session_state.selected_persona is enough for the current request; a
future personalization pass can read that value without any changes
here.

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

# (session-state value, i18n label key)
_PERSONAS = [
    ("contractor", "persona_contractor"),
    ("developer", "persona_developer"),
    ("government_employee", "persona_government_employee"),
    ("individual", "persona_individual"),
]


def render() -> None:
    """The picker itself -- shown instead of the search bar until a
    persona is chosen."""
    st.markdown(
        f'<p class="persona-picker-heading">{t("persona_picker_heading")}</p>',
        unsafe_allow_html=True,
    )
    with st.container(key="persona_picker_row"):
        cols = st.columns(4, gap="small")
        for col, (persona_key, label_key) in zip(cols, _PERSONAS):
            with col:
                if st.button(t(label_key), key=f"persona_select_{persona_key}", width="stretch"):
                    st.session_state.selected_persona = persona_key
                    st.rerun()
