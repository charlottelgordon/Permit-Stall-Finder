"""Persona-selection gate shown on first load, before the search bar --
lets a user identify as Contractor / Developer / Government Employee /
Individual by clicking one of four icons. Purely a display gate for now
(which screen shows next), not yet used to vary any content -- storing
the choice in st.session_state.selected_persona is enough for the
current request; a future personalization pass can read that value
without any changes here.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from i18n import t

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

# (session-state value, image filename, i18n label key)
_PERSONAS = [
    ("contractor", "Contractor.jpg", "persona_contractor"),
    ("developer", "Developer.jpg", "persona_developer"),
    ("government_employee", "Government Employee.jpg", "persona_government_employee"),
    ("individual", "Individual.jpg", "persona_individual"),
]


def render() -> None:
    """The picker itself -- shown instead of the search bar until a
    persona is chosen."""
    st.markdown(
        f'<p class="persona-picker-heading">{t("persona_picker_heading")}</p>',
        unsafe_allow_html=True,
    )
    cols = st.columns(4)
    for col, (persona_key, filename, label_key) in zip(cols, _PERSONAS):
        with col:
            st.image(str(_ASSETS_DIR / filename), width="stretch")
            if st.button(t(label_key), key=f"persona_select_{persona_key}", width="stretch"):
                st.session_state.selected_persona = persona_key
                st.rerun()


def render_change_link() -> None:
    """Small "Browsing as: X -- Change" affordance shown above the search
    bar once a persona is picked, so a wrong/accidental selection isn't a
    dead end."""
    label_key = next(lk for pk, _, lk in _PERSONAS if pk == st.session_state.selected_persona)
    left, right = st.columns([5, 1])
    with left:
        st.caption(t("persona_browsing_as").format(persona=t(label_key)))
    with right:
        if st.button(t("persona_change"), key="persona_change_button"):
            st.session_state.selected_persona = None
            st.rerun()
