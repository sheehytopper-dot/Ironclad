"""Expenses tab (Phase 5 Step 3; spec §6 tab 4 — §3.11).

Opex/capex/non-operating ``ExpenseItem`` grid + per-item detail editor
(amount, timing, limits, annual overrides, inflation) + ``ExpenseGroup``s.
Per Step 0 D2 the engine-refused ``pct_of_account`` unit renders
READ-ONLY with the engine's refusal message shown **verbatim** — including
its stale "until Phase 2" wording, which is deliberately NOT fixed here
(engine-frozen; on the post-Gate-5 wording-pass list in
NEXT_STEPS_TO_PHASE5.md). Same pattern as Step 2: pure ``apply_*``
functions through the :func:`ui.state.updated_model` funnel; every
success installs via :func:`ui.session.set_model` (RunResult invalidated).
"""
from __future__ import annotations

import streamlit as st

from engine.models import ExpenseCategory, ExpenseUnit
from ui import convert, session, state
from ui.tabs import common_widgets

CATEGORIES = [c.value for c in ExpenseCategory]
#: Editable units — the engine-refused pct_of_account is NOT offered.
EDITABLE_UNITS = [u.value for u in ExpenseUnit
                  if u.value != convert.REFUSED_UNIT]

#: The engine's refusal, verbatim (engine/calc/run.py `_phase_guards`) —
#: including the STALE "until Phase 2" label (deliberately surfaced as-is;
#: see the stale-message list in NEXT_STEPS_TO_PHASE5.md).
def refusal_text(name: str) -> str:
    return (f"expense {name!r}: unit 'pct_of_account' is not implemented "
            "until Phase 2; remove the input or wait for that phase")


# ------------------------------------------------------------------ #
# Pure commit functions                                               #
# ------------------------------------------------------------------ #

def apply_expense_grid(model, rows: list[dict]):
    """Scalar-grid merge by row order; nested detail preserved; refused
    (pct_of_account) items re-inserted untouched at their positions."""
    def mutate(data):
        data["expenses"] = convert.apply_grid_rows_with_refused(
            data["expenses"], rows, convert.EXPENSE_GRID_COLUMNS,
            convert.NEW_EXPENSE_TEMPLATE)
    return state.updated_model(model, mutate)


def apply_expense_detail(model, index: int, payload: dict):
    """Merge a detail payload (amount / timing / limits / annual_overrides /
    inflation …) into expense ``index`` (the model-list index)."""
    def mutate(data):
        if convert.is_refused_item(data["expenses"][index]):
            raise ValueError(
                "this expense uses the engine-refused 'pct_of_account' unit "
                "and is read-only (Step 0 D2)")
        data["expenses"][index].update(payload)
    return state.updated_model(model, mutate)


def apply_expense_groups(model, rows: list[dict]):
    def mutate(data):
        data["expense_groups"] = convert.rows_to_expense_groups(rows)
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


def render() -> None:
    model = st.session_state.model
    if model is None:
        st.info("Open or create a property in the sidebar first.")
        return
    rev = session.rev()
    data = model.model_dump(mode="json")
    expenses = data["expenses"]

    st.subheader("Expenses (§3.11)")
    st.caption("Scalar grid — timing, limits, annual overrides, and "
               "inflation are in the detail editor below. Add a row to add "
               "an expense; delete a row to delete one.")
    grid = st.data_editor(
        convert.items_to_grid_rows(expenses, convert.EXPENSE_GRID_COLUMNS)
        or [{c: None for c in convert.EXPENSE_GRID_COLUMNS}],
        num_rows="dynamic", key=f"exp_grid_{rev}",
        column_config={
            "category": st.column_config.SelectboxColumn(options=CATEGORIES),
            "unit": st.column_config.SelectboxColumn(options=EDITABLE_UNITS),
        })
    if st.button("Apply expense grid", key=f"exp_grid_apply_{rev}"):
        _apply_and_report(*apply_expense_grid(model, grid),
                          "Expenses updated.")

    refused = convert.refused_items(expenses)
    if refused:
        with st.expander("Engine-refused expenses — READ-ONLY "
                         f"({len(refused)})", expanded=False):
            for item in refused:
                st.warning(refusal_text(item["name"]))
                st.json(item)

    editable_indices = [i for i, e in enumerate(expenses)
                        if not convert.is_refused_item(e)]
    if editable_indices:
        options = [f"{i}: {expenses[i]['name']}" for i in editable_indices]
        chosen = st.selectbox("Detail editor — expense", options,
                              key=f"exp_pick_{rev}")
        index = int(chosen.split(":", 1)[0])
        item = expenses[index]
        key = f"exp_{index}_{rev}"

        col1, col2 = st.columns(2)
        with col1:
            amount = st.number_input("Amount", value=float(item["amount"]),
                                     key=f"{key}_amt")
        with col2:
            unit = st.selectbox(
                "Unit", EDITABLE_UNITS,
                index=EDITABLE_UNITS.index(item["unit"])
                if item["unit"] in EDITABLE_UNITS else 0,
                key=f"{key}_unit")
        timing = common_widgets.timing_inputs(item["timing"], f"{key}_tim")
        limits = common_widgets.limits_inputs(item["limits"], f"{key}_lim")
        inflation = common_widgets.inflation_inputs(item["inflation"],
                                                    f"{key}_inf")
        st.caption("Annual overrides (known amounts by year — "
                   "DEVIATIONS §12)")
        override_rows = st.data_editor(
            convert.overrides_to_override_rows(item["annual_overrides"])
            or [{"year": None, "amount": None}],
            num_rows="dynamic", key=f"{key}_ovr")
        if st.button("Apply expense detail", key=f"{key}_apply"):
            payload = {"amount": amount, "unit": unit, "timing": timing,
                       "limits": limits, "inflation": inflation,
                       "annual_overrides": convert.rows_to_annual_overrides(
                           override_rows)}
            _apply_and_report(*apply_expense_detail(model, index, payload),
                              f"Expense '{item['name']}' updated.")

    st.subheader("Expense groups")
    st.caption("Members: comma-separated expense names.")
    group_rows = st.data_editor(
        convert.expense_groups_to_rows(data["expense_groups"])
        or [{c: None for c in convert.EXPENSE_GROUP_COLUMNS}],
        num_rows="dynamic", key=f"expgrp_grid_{rev}")
    if st.button("Apply expense groups", key=f"expgrp_apply_{rev}"):
        _apply_and_report(*apply_expense_groups(model, group_rows),
                          "Expense groups updated.")
