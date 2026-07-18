"""Revenues tab (Phase 5 Step 3; spec §6 tab 3 — §3.10).

Miscellaneous / parking / storage ``PropertyRevenue`` grids + per-item
detail (timing, limits, inflation, spaces). Per Step 0 D2 the
engine-refused ``pct_of_account`` unit renders READ-ONLY with the engine's
refusal message verbatim. Same funnel pattern as the other tabs.
"""
from __future__ import annotations

import streamlit as st

from engine.models import RevenueUnit
from ui import convert, session, state
from ui.tabs import common_widgets

#: The three §3.10 collections and their display names.
KINDS = [("miscellaneous_revenues", "Miscellaneous"),
         ("parking_revenues", "Parking"),
         ("storage_revenues", "Storage")]
EDITABLE_UNITS = [u.value for u in RevenueUnit
                  if u.value != convert.REFUSED_UNIT]


def refusal_text(name: str) -> str:
    """The engine's refusal, verbatim (engine/calc/run.py `_phase_guards`;
    DEVIATIONS §13)."""
    return (f"property revenue {name!r}: unit 'pct_of_account' is not "
            "implemented until a later phase (DEVIATIONS.md §13); remove "
            "the input or wait for that phase")


# ------------------------------------------------------------------ #
# Pure commit functions                                               #
# ------------------------------------------------------------------ #

def apply_revenue_grid(model, kind: str, rows: list[dict]):
    """``kind`` ∈ miscellaneous_revenues / parking_revenues /
    storage_revenues."""
    def mutate(data):
        data[kind] = convert.apply_grid_rows_with_refused(
            data[kind], rows, convert.REVENUE_GRID_COLUMNS,
            convert.NEW_REVENUE_TEMPLATE)
    return state.updated_model(model, mutate)


def apply_revenue_detail(model, kind: str, index: int, payload: dict):
    def mutate(data):
        if convert.is_refused_item(data[kind][index]):
            raise ValueError(
                "this revenue uses the engine-refused 'pct_of_account' unit "
                "and is read-only (Step 0 D2)")
        data[kind][index].update(payload)
    return state.updated_model(model, mutate)


# ------------------------------------------------------------------ #
# Renderer                                                            #
# ------------------------------------------------------------------ #

def _apply_and_report(new_model, error, success_message: str) -> None:
    if error:
        st.error(error)
    else:
        session.set_model(new_model, reset_widgets=False)
        st.success(success_message)


def _render_kind(model, data, kind: str, title: str, rev: int) -> None:
    items = data[kind]
    with st.expander(f"{title} revenues", expanded=False):
        grid = st.data_editor(
            convert.items_to_grid_rows(items, convert.REVENUE_GRID_COLUMNS)
            or [{c: None for c in convert.REVENUE_GRID_COLUMNS}],
            num_rows="dynamic", key=f"rev_{kind}_grid_{rev}",
            column_config={"unit": st.column_config.SelectboxColumn(
                options=EDITABLE_UNITS)})
        if st.button(f"Apply {title.lower()} grid",
                     key=f"rev_{kind}_apply_{rev}"):
            _apply_and_report(*apply_revenue_grid(model, kind, grid),
                              f"{title} revenues updated.")

        refused = convert.refused_items(items)
        for item in refused:
            st.warning(refusal_text(item["name"]))
            st.json(item)

        editable_indices = [i for i, e in enumerate(items)
                            if not convert.is_refused_item(e)]
        if editable_indices:
            options = [f"{i}: {items[i]['name']}" for i in editable_indices]
            chosen = st.selectbox(f"Detail editor — {title.lower()} revenue",
                                  options, key=f"rev_{kind}_pick_{rev}")
            index = int(chosen.split(":", 1)[0])
            item = items[index]
            key = f"rev_{kind}_{index}_{rev}"
            timing = common_widgets.timing_inputs(item["timing"],
                                                  f"{key}_tim")
            limits = common_widgets.limits_inputs(item["limits"],
                                                  f"{key}_lim")
            inflation = common_widgets.inflation_inputs(item["inflation"],
                                                        f"{key}_inf")
            if st.button("Apply revenue detail", key=f"{key}_apply"):
                payload = {"timing": timing, "limits": limits,
                           "inflation": inflation}
                _apply_and_report(
                    *apply_revenue_detail(model, kind, index, payload),
                    f"Revenue '{item['name']}' updated.")


def render() -> None:
    model = st.session_state.model
    if model is None:
        st.info("Open or create a property in the sidebar first.")
        return
    rev = session.rev()
    data = model.model_dump(mode="json")
    st.subheader("Property revenues (§3.10)")
    st.caption("Absolute-amount lines project once; %-of-EGR/PGR lines "
               "resolve inside the engine's fixed point (DEVIATIONS §13).")
    for kind, title in KINDS:
        _render_kind(model, data, kind, title, rev)
