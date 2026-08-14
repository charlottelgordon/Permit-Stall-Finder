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
explicit request -- the imagery read as overwhelming.

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


def render_switch_button() -> None:
    """A single button, labeled with the currently-selected role's own
    name plus a small down-caret (e.g. "Contractor ⌄") -- sits in the
    same row as the EN/ES toggle once a role is picked. The caret isn't
    functional (this doesn't open a dropdown, it clears the selection
    and reopens the picker) but is the common visual shorthand for "this
    shows your current choice and can be changed," which the bare name
    alone didn't communicate. Wrapped in its own keyed container so
    streamlit_app.py's stylesheet can give it the same pill-button
    treatment as the header's Home link, distinct from a plain default
    button. The caller controls outer layout/columns; this only renders
    the button itself."""
    label_key = next(lk for pk, lk in _PERSONAS if pk == st.session_state.selected_persona)
    with st.container(key="persona_switch_wrap"):
        if st.button(f"{t(label_key)} ⌄", key="persona_switch_button", width="stretch"):
            st.session_state.selected_persona = None
            st.rerun()
