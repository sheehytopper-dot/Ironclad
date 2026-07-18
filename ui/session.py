"""Session-state mutations shared by the sidebar and every tab (Phase 5).

The one place the current model is installed or replaced. Every model
change — open, new, upload, or a tab edit — goes through
:func:`set_model`, which (1) clears the cached ``RunResult`` so a stale
calculation can never render, and (2) bumps ``model_rev``, the nonce tab
renderers embed in widget keys so switching properties resets the editors
instead of showing the previous property's half-edited values.
"""
from __future__ import annotations

import streamlit as st

#: Sentinel: "keep the current path" (edits keep it; Open/New replace it).
KEEP = object()


def init() -> None:
    st.session_state.setdefault("model", None)
    st.session_state.setdefault("model_path", None)
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("model_rev", 0)
    st.session_state.setdefault("load_error", None)
    st.session_state.setdefault("calc_error", None)


def set_model(model, path=KEEP, *, reset_widgets: bool = True) -> None:
    """Install ``model`` as current; invalidate the cached RunResult.
    ``reset_widgets=False`` keeps widget state (a tab Apply — the user is
    mid-editing); the default resets it (a different/new document)."""
    st.session_state.model = model
    if path is not KEEP:
        st.session_state.model_path = path
    st.session_state.result = None
    if reset_widgets:
        st.session_state.model_rev += 1


def rev() -> int:
    return st.session_state.model_rev
