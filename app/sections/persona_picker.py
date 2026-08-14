"""Persona-selection gate shown on first load, before the search bar --
lets a user identify as Contractor / Developer / Government Employee /
Individual by clicking one of four square image-buttons. Purely a
display gate for now (which screen shows next), not yet used to vary
any content -- storing the choice in st.session_state.selected_persona
is enough for the current request; a future personalization pass can
read that value without any changes here.

Each "card" is an st.image with a real st.button stretched over it via
CSS (position: absolute, opacity: 0) so the image itself is the click
target -- Streamlit has no native clickable-image widget. The button's
own text stays as its accessible name (screen readers still get it) even
though it's visually invisible; the image supplies the visible label.
st.container(key=...) is what makes this possible: it's the only way to
get a stable, per-card CSS hook (a "st-key-<key>" class) to scope the
overlay to just that one card instead of every button on the page.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from i18n import t

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_IMAGE_WIDTH = 130
"""Square-button sizing per explicit request -- small enough to read as
a row of buttons, not a row of full photos."""

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
            with st.container(key=f"persona_card_{persona_key}"):
                st.image(str(_ASSETS_DIR / filename), width=_IMAGE_WIDTH)
                if st.button(t(label_key), key=f"persona_select_{persona_key}"):
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
