"""Landing screen: a large welcome banner shown above the search bar
before any search has run (and again after "Clear results"), plus an
optional "who are you" persona picker.

The persona choice (developer/contractor, city/government, or skipped)
changes exactly one thing: which welcome sentence is shown, via
i18n.audience_subtitle(). It never gates a feature, changes what data is
fetched, or alters the disclaimer -- a city/government visitor sees the
identical tool, results, caveats, and "informational only, not an
official LADBS determination" disclaimer as everyone else. See
i18n.get_audience()'s own docstring for why that boundary matters here
specifically.
"""

from __future__ import annotations

import streamlit as st

from i18n import (
    AUDIENCES,
    APP_NAME,
    audience_subtitle,
    get_audience,
    set_audience,
    t,
)

_PERSONA_LABELS = {
    "developer": "landing_persona_developer",
    "government": "landing_persona_government",
    "other": "landing_persona_other",
}


def render_landing() -> None:
    st.markdown(
        f'<h1 class="landing-title">{t("landing_title").format(app=APP_NAME)}</h1>'
        f'<p class="landing-subtitle">{audience_subtitle()}</p>',
        unsafe_allow_html=True,
    )

    audience = get_audience()
    if audience is None:
        st.markdown(f'<p class="landing-persona-prompt">{t("landing_persona_prompt")}</p>', unsafe_allow_html=True)
        _, picker_col, _ = st.columns([1, 3, 1])
        with picker_col:
            cols = st.columns(len(AUDIENCES))
            for col, persona in zip(cols, AUDIENCES):
                with col:
                    if st.button(t(_PERSONA_LABELS[persona]), key=f"landing_persona_{persona}", width="stretch"):
                        set_audience(persona)
                        st.rerun()
    else:
        _, change_col, _ = st.columns([1, 3, 1])
        with change_col:
            if st.button(t("landing_persona_change"), key="landing_persona_change_button"):
                set_audience(None)
                st.session_state.pop("landing_persona_picker", None)
                st.rerun()
