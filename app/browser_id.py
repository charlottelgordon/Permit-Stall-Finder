"""Anonymous per-browser identity for starred searches -- no login system
anywhere in this app (see storage/starred.py), so "the same browser
coming back" is established via a long-lived cookie instead.

Reads via st.context.cookies -- Streamlit's own read-only cookie API
(added after this app's original components.html-bridge idioms were
written, e.g. i18n.py's _sync_html_lang() and streamlit_app.py's header
Home-link handler both predate it and still need their own bridges for
what they do). Two earlier approaches to this specific problem were tried
and abandoned before landing here, worth recording so they aren't
re-attempted:

  1. Bridging the id in via window.parent.location + a query-param
     reload: fails outright, because components.html's iframe sandbox has
     no allow-top-navigation, so the browser blocks the parent-window
     navigation entirely (confirmed via a console "Unsafe attempt to
     initiate navigation ... frame is sandboxed" error).
  2. Bridging it in by driving a hidden st.text_input's value via a
     native-setter + dispatched input/keydown events (the same class of
     DOM-mutation trick the Home-link bridge uses for a button click):
     the DOM value visibly updates, but never commits back to Python --
     Streamlit's controlled-input commit path isn't triggered by
     dispatched (non-trusted) events in this version, confirmed by
     testing the identical dispatch sequence from the real top-level page
     context, not just from inside the sandboxed iframe.

st.context.cookies only reflects cookies present on the *initial* request
that opened the current session, so a cookie set mid-session (this
browser's very first visit) won't be readable via st.context.cookies
until a later session/reload -- handled here by having Python itself
generate the id up front for that first visit (no round trip needed to
"learn" a value Python already chose) and simply asking the browser, via
a components.html script that only ever mutates document.cookie (no
navigation, no widget-event trickery -- the same safe class of DOM
mutation _sync_html_lang() already relies on), to remember it for next
time.
"""

from __future__ import annotations

import uuid

import streamlit as st
import streamlit.components.v1 as components

_COOKIE_NAME = "pcla_uid"


def _set_cookie_script(uid: str) -> None:
    components.html(
        f"""
        <script>
        try {{
            document.cookie = {_COOKIE_NAME!r} + '=' + {uid!r} + '; max-age=63072000; path=/; SameSite=Lax';
        }} catch (e) {{}}
        </script>
        """,
        height=0,
        width=0,
    )


def get_or_bootstrap_uid() -> str:
    """Returns this browser's anonymous id -- generating and persisting
    one via a cookie on its very first visit, and reading the existing
    cookie back (via st.context.cookies) on every visit after that.
    Unlike the persona-picker's "None means not chosen yet" pattern, this
    always returns a real value the same render pass -- there's no
    round trip Python has to wait on, since it either reads an existing
    cookie directly or generates the value itself."""
    if "pcla_uid" in st.session_state:
        return st.session_state.pcla_uid

    existing = st.context.cookies.get(_COOKIE_NAME)
    if existing:
        st.session_state.pcla_uid = existing
        return existing

    new_uid = str(uuid.uuid4())
    st.session_state.pcla_uid = new_uid
    _set_cookie_script(new_uid)
    return new_uid
