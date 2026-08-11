"""Plumbing only: keeps one DuckDB connection alive across Streamlit's
rerun-the-whole-script-on-every-interaction model, using the same
storage.db.connect() Agent 1 already provides. No new analytical logic.

The database path is never surfaced to the page -- see errors.py and
research/UI_DESIGN.md's "never expose local database paths" requirement.
"""

from __future__ import annotations

import duckdb
import streamlit as st

from permit_stall_finder import config
from permit_stall_finder.knowledge_base.loader import KnowledgeBase, default_knowledge_base
from permit_stall_finder.storage.db import connect


@st.cache_resource
def get_connection() -> duckdb.DuckDBPyConnection:
    return connect(config.DEFAULT_DB_PATH)


@st.cache_resource
def get_knowledge_base() -> KnowledgeBase:
    """The same default knowledge base run_pipeline() falls back to when no
    explicit one is passed in -- loaded once here so the UI's read-only
    kb_entry_by_id() lookups (see formatting.py) resolve against the exact
    entries Agent 3 selected from, not a separately-loaded copy."""
    return default_knowledge_base()
