"""Quick access -- starred permits/addresses and recent searches, shown
above the search tabs so a return user (someone checking the same
permit(s) every day for their job) can re-run yesterday's search in one
click instead of retyping it. Every value here comes straight from
storage/user_state.py; this module only lays out clickable pills and
reports which one (if any) was just clicked -- it never decides what to
do about that click. That decision (run a single permit directly, or
pre-fill and re-run an address search) belongs to streamlit_app.py, the
same "return the user's intent, let the entrypoint act on it" pattern
address_search.render() already follows.

render_star_toggle() is the other half of the same feature -- a small
star/unstar button placed next to whatever a user is currently looking
at (a single-permit result, or an address search query), so starring
something doesn't require a separate management screen for the common
case.
"""

from __future__ import annotations

from dataclasses import dataclass

import duckdb
import streamlit as st

from i18n import t
from permit_stall_finder.storage import user_state


@dataclass(frozen=True)
class QuickAccessSelection:
    kind: str  # "permit_number" or "address"
    value: str


def _pill_label(kind: str, value: str) -> str:
    icon = "📍" if kind == "address" else "🔖"
    return f"{icon} {value}"


def _render_pill_row(
    items: list[tuple[str, str]], *, key_prefix: str
) -> QuickAccessSelection | None:
    """items is a list of (kind, value). Renders in rows of up to 4 so a
    longer list wraps instead of squeezing every pill into one row."""
    clicked: QuickAccessSelection | None = None
    for i in range(0, len(items), 4):
        row = items[i : i + 4]
        cols = st.columns(len(row))
        for col, (kind, value) in zip(cols, row):
            if col.button(_pill_label(kind, value), key=f"{key_prefix}_{kind}_{value}"):
                clicked = QuickAccessSelection(kind, value)
    return clicked


def render(conn: duckdb.DuckDBPyConnection) -> QuickAccessSelection | None:
    """Renders the starred + recent panel and returns the pill the user
    just clicked (if any) so streamlit_app.py can run it. Starred and
    recent are read fresh from storage on every run -- cheap local
    queries, not a network call, so there's no reason to cache them."""
    starred = user_state.read_starred_items(conn)
    recent = user_state.read_recent_searches(conn)

    # Don't repeat something in "recent" that's already pinned in
    # "starred" -- one line per thing a user is tracking, not two.
    starred_keys = {(item.kind, item.value) for item in starred}
    recent = [r for r in recent if (r.kind, r.value) not in starred_keys]

    if not starred and not recent:
        return None

    selection: QuickAccessSelection | None = None

    if starred:
        st.caption(t("starred"))
        clicked = _render_pill_row(
            [(item.kind, item.value) for item in starred], key_prefix="qa_star"
        )
        selection = clicked or selection

        with st.expander(t("manage_starred")):
            for item in starred:
                label_col, action_col = st.columns([4, 1])
                label_col.write(_pill_label(item.kind, item.value))
                if action_col.button(t("unstar"), key=f"qa_unstar_{item.kind}_{item.value}"):
                    user_state.unstar_item(conn, item.kind, item.value)
                    st.rerun()

    if recent:
        st.caption(t("recent"))
        clicked = _render_pill_row(
            [(entry.kind, entry.value) for entry in recent], key_prefix="qa_recent"
        )
        selection = clicked or selection

    if starred or recent:
        st.divider()

    return selection


def render_star_toggle(conn: duckdb.DuckDBPyConnection, kind: str, value: str) -> None:
    """A single star/unstar button for one specific (kind, value) --
    dropped next to a single-permit result or an address search query so
    starring the thing you're already looking at takes one click."""
    starred = user_state.is_starred(conn, kind, value)
    label = t("starred_button") if starred else t("star_this_button")
    if st.button(label, key=f"star_toggle_{kind}_{value}"):
        if starred:
            user_state.unstar_item(conn, kind, value)
        else:
            user_state.star_item(conn, kind, value)
        st.rerun()
