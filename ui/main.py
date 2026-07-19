"""IronClad Streamlit app (Phase 5 Step 1; spec §6).

Thin renderer over the pure helpers in :mod:`ui.state` — all logic that
can live outside Streamlit does, so it is unit-testable without a browser
(NEXT_STEPS_TO_PHASE5.md Step 1). **Iron Rule 1:** this package imports
the engine; the engine never imports this package. Zero changes under
``engine/`` in Phase 5 (git-log-checked from baseline ``62617f1``).

Step 1 scope: the app shell — sidebar (property selector over
``data/properties/``, Open / New / Save, the load-JSON intake surface,
the **Calculate** pipe with the RunResult cached in session state and
invalidated on any model change) and a minimal Dashboard (year-1 NOI,
year-1 occupancy) proving the pipe end-to-end. The remaining tabs are
placeholders labeled with the step that builds them.

Navigation (usability pass, Tier 1): a VERTICAL list in the left sidebar
below the property controls, visually grouped Inputs (Property …
Valuation) / Outputs (Reports, Dashboard, Audit), with **Dashboard
default-active** (Step 0 D5). One ``st.radio`` keyed ``active_tab`` with
the raw tab names as option values — the grouping lives in
``format_func`` display labels only, so the widget API (and every
AppTest flow driving it) is unchanged. A radio rather than ``st.tabs``
because Streamlit cannot set the active tab programmatically.
"""
from __future__ import annotations

import streamlit as st

from ui import session, state
from ui.tabs import (audit_tab, dashboard_tab, expenses_tab, investment_tab,
                     market_tab, property_tab, reports_tab, revenues_tab,
                     tenants_tab, valuation_tab)

#: Spec §6 tab order, verbatim. Dashboard is default-active (Step 0 D5).
TABS = ["Property", "Market", "Revenues", "Expenses", "Tenants",
        "Investment", "Valuation", "Reports", "Dashboard", "Audit"]
DEFAULT_TAB = "Dashboard"
INPUT_TABS = {"Property", "Market", "Revenues", "Expenses", "Tenants",
              "Investment", "Valuation"}


def _nav_label(tab: str) -> str:
    """Display-only group glyphs (option VALUES stay the raw tab names)."""
    return f"✏️ {tab}" if tab in INPUT_TABS else f"📊 {tab}"

#: All ten spec §6 tabs are built (Steps 1-6).
_TAB_RENDERERS = {"Property": property_tab.render, "Market": market_tab.render,
                  "Revenues": revenues_tab.render,
                  "Expenses": expenses_tab.render,
                  "Tenants": tenants_tab.render,
                  "Investment": investment_tab.render,
                  "Valuation": valuation_tab.render,
                  "Reports": reports_tab.render,
                  "Dashboard": dashboard_tab.render,
                  "Audit": audit_tab.render}


def _set_model(model, path) -> None:
    """Install a (new) current document — resets editors and invalidates
    the cached RunResult (ui.session.set_model)."""
    session.set_model(model, path)


def _sidebar() -> None:
    directory = state.properties_dir()
    st.sidebar.title("IronClad")

    files = state.list_property_files(directory)
    names = [state.property_display_name(p) for p in files]
    selected = st.sidebar.selectbox("Property", names, key="property_select",
                                    index=0 if names else None,
                                    placeholder="No properties yet")
    if st.sidebar.button("Open", key="open_btn", disabled=not names):
        path = files[names.index(selected)]
        model, error = state.load_model(path)
        if error:
            st.session_state.load_error = error
        else:
            st.session_state.load_error = None
            _set_model(model, path)

    with st.sidebar.expander("New property"):
        new_name = st.text_input("Name", key="new_name")
        if st.button("Create", key="create_btn"):
            _set_model(state.new_minimal_model(new_name), None)
            st.session_state.load_error = None

    with st.sidebar.expander("Load PropertyModel JSON"):
        uploaded = st.file_uploader("`.icprop.json` file", type=["json"],
                                    key="upload_json")
        if uploaded is not None and st.button("Load uploaded", key="load_upload_btn"):
            text = uploaded.getvalue().decode("utf-8")
            model, error = state.load_model_from_text(text, uploaded.name)
            if error:
                st.session_state.load_error = error
            else:
                st.session_state.load_error = None
                _set_model(model, None)

    model = st.session_state.get("model")
    if st.sidebar.button("Save", key="save_btn", disabled=model is None):
        path = (st.session_state.get("model_path")
                or state.default_save_path(model, directory))
        saved = state.save_model(model, path)
        st.session_state.model_path = saved
        st.sidebar.success(f"Saved {saved.name}")

    if st.sidebar.button("Calculate", key="calc_btn", type="primary",
                         disabled=model is None):
        with st.spinner("Calculating…"):
            result, error = state.run_model(model)
        st.session_state.result = result
        st.session_state.calc_error = error

    # Errors render as readable panels (§5.4), never tracebacks.
    if st.session_state.get("load_error"):
        st.sidebar.error(st.session_state.load_error)
    if st.session_state.get("calc_error"):
        st.sidebar.error(st.session_state.calc_error)

    st.sidebar.caption("Package export lives on the Reports tab.")


def render() -> None:
    st.set_page_config(page_title="IronClad", layout="wide")
    session.init()

    _sidebar()

    st.sidebar.divider()
    st.sidebar.markdown("**Navigation** — ✏️ Inputs · 📊 Outputs")
    active = st.sidebar.radio("Navigation", TABS,
                              index=TABS.index(DEFAULT_TAB),
                              key="active_tab", format_func=_nav_label,
                              label_visibility="collapsed")
    _TAB_RENDERERS[active]()
