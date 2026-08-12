"""Section G — disclaimer. Shown once at page level on every completed
analysis, never inside an expander, never repeated per-card
(UI_DESIGN.md decision 4). Text is Agent 3's own DISCLAIMER constant,
never UI-composed.
"""

from __future__ import annotations

import streamlit as st


def render(disclaimer: str) -> None:
    st.divider()
    st.caption(disclaimer)
