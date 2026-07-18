"""Shared nested-detail widgets for revenue/expense items (Phase 5 Step 3).

Each helper renders Streamlit inputs seeded from the item's current dump
and returns the model-shaped payload dict — validation happens in the
:func:`ui.state.updated_model` funnel, never here. Iron Rule 1: engine
imports only.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from engine.models import RecoverySystemMethod, TimingMethod
from ui import convert

TIMING_METHODS = [m.value for m in TimingMethod]
RECOVERY_METHODS = [m.value for m in RecoverySystemMethod]
TI_UNITS = ["dollars_per_area", "dollars"]


def timing_inputs(current: dict, key: str) -> dict:
    """Timing editor (§3.11 ``Timing``): method + date range + repeating."""
    method = st.selectbox("Timing method", TIMING_METHODS,
                          index=TIMING_METHODS.index(current["method"]),
                          key=f"{key}_method")
    col1, col2 = st.columns(2)
    with col1:
        start = st.text_input("Start (YYYY-MM-DD, blank = none)",
                              value=current["start"] or "",
                              key=f"{key}_start")
        repeat_months = st.text_input(
            "Repeat months (1-12, comma-separated; blank = none)",
            value=", ".join(str(m) for m in current["repeat_months"] or []),
            key=f"{key}_repeat")
    with col2:
        end = st.text_input("End (YYYY-MM-DD, blank = none)",
                            value=current["end"] or "", key=f"{key}_end")
        every = st.number_input("Repeat every N months (0 = none)",
                                value=int(current["repeat_every_months"] or 0),
                                step=1, key=f"{key}_every")
    months = [int(m) for m in repeat_months.replace(" ", "").split(",")
              if m] or None
    return {"method": method, "start": start or None, "end": end or None,
            "repeat_months": months,
            "repeat_every_months": int(every) or None}


def limits_inputs(current: Optional[dict], key: str) -> Optional[dict]:
    """Limits editor (monthly min/max clamp; 0 = no bound; both 0 = no
    limits)."""
    current = current or {}
    col1, col2 = st.columns(2)
    with col1:
        minimum = st.number_input("Monthly minimum (0 = none)",
                                  value=float(current.get("min") or 0.0),
                                  key=f"{key}_min")
    with col2:
        maximum = st.number_input("Monthly maximum (0 = none)",
                                  value=float(current.get("max") or 0.0),
                                  key=f"{key}_max")
    if not minimum and not maximum:
        return None
    return {"min": minimum or None, "max": maximum or None}


def inflation_inputs(current, key: str):
    """Inflation editor: the field is ``str`` (a named series/index) |
    ``list[YearRate]`` (a custom schedule) | ``None`` (the general rate)."""
    if isinstance(current, list):
        mode_index = 2
    elif current:
        mode_index = 1
    else:
        mode_index = 0
    mode = st.radio("Inflation", ["general (default)", "named index",
                                  "custom schedule"],
                    index=mode_index, horizontal=True, key=f"{key}_mode")
    if mode == "general (default)":
        return None
    if mode == "named index":
        name = st.text_input(
            "Index name (expense / market_rent / cpi / a custom index)",
            value=current if isinstance(current, str) else "",
            key=f"{key}_name")
        return name or None
    rows = st.data_editor(
        convert.year_rates_to_rows(current if isinstance(current, list)
                                   else None)
        or [{"year": None, "rate": None}],
        num_rows="dynamic", key=f"{key}_rows")
    return convert.rows_to_year_rates(rows) or None


def money_rate_inputs(label: str, current: Optional[dict], units: list[str],
                      key: str, *, optional: bool = False) -> Optional[dict]:
    """Amount + unit → MoneyRate dict (None when optional and disabled)."""
    enabled = True
    if optional:
        enabled = st.checkbox(f"{label} — set", value=current is not None,
                              key=f"{key}_on")
    if not enabled:
        return None
    amount = st.number_input(f"{label} amount",
                             value=float((current or {}).get("amount", 0.0)),
                             key=f"{key}_amt")
    unit_now = (current or {}).get("unit", units[0])
    unit = st.selectbox(f"{label} unit", units,
                        index=units.index(unit_now) if unit_now in units else 0,
                        key=f"{key}_unit")
    return {"amount": amount, "unit": unit}


def lc_spec_inputs(label: str, current: Optional[dict], key: str,
                   *, refusal_note=None) -> Optional[dict]:
    """LCSpec editor: none | % of rent (+ years) | rate. A ``category_ref``
    is engine-refused — shown via ``refusal_note`` (verbatim), preserved
    untouched (the payload never includes it)."""
    modes = ["none", "% of rent", "rate"]
    if current is None:
        mode_now = "none"
    elif current.get("pct") is not None:
        mode_now = "% of rent"
    else:
        mode_now = "rate"
    mode = st.selectbox(f"{label} method", modes, index=modes.index(mode_now),
                        key=f"{key}_mode")
    if current and current.get("category_ref") and refusal_note:
        st.warning(refusal_note)
    if mode == "none":
        return None
    if mode == "% of rent":
        pct = st.number_input(f"{label} % of rent",
                              value=float((current or {}).get("pct") or 0.0),
                              key=f"{key}_pct")
        years_text = st.text_input(
            f"{label} % applies to lease years (blank = all)",
            value=",".join(str(y) for y in (current or {}).get("pct_years")
                           or []),
            key=f"{key}_years")
        years = [int(y) for y in years_text.replace(" ", "").split(",")
                 if y] or None
        return {"pct": pct, "pct_years": years}
    rate = money_rate_inputs(f"{label} rate", (current or {}).get("rate"),
                             TI_UNITS, f"{key}_rate")
    return {"rate": rate}


def recovery_assignment_inputs(current: dict, key: str,
                               structure_names: list[str]) -> dict:
    """RecoveryAssignment editor (§3.7 system methods + structure ref) —
    shared by the Tenants tab (the MLP editor keeps its own copy)."""
    method = st.selectbox("Recovery method", RECOVERY_METHODS,
                          index=RECOVERY_METHODS.index(current["method"]),
                          key=f"{key}_method")
    col1, col2, col3 = st.columns(3)
    with col1:
        stop = st.number_input("Stop $/SF (base_stop)",
                               value=float(current["stop_amount_per_area"]
                                           or 0.0), key=f"{key}_stop")
        options = [""] + structure_names
        structure = st.selectbox(
            "Structure ref", options,
            index=(options.index(current["structure_ref"])
                   if current["structure_ref"] in options else 0),
            key=f"{key}_struct")
    with col2:
        base_year = st.number_input("Base year (0 = default)",
                                    value=int(current["base_year"] or 0),
                                    step=1, key=f"{key}_baseyear")
        gross_up = st.number_input("Base-year gross-up % (0 = none)",
                                   value=float(
                                       current["base_year_gross_up_pct"]
                                       or 0.0), key=f"{key}_gross")
    with col3:
        fixed_amount = st.number_input("Fixed $ (0 = none)",
                                       value=float(current["fixed_amount"]
                                                   or 0.0),
                                       key=f"{key}_fixed")
        fixed_psf = st.number_input("Fixed $/SF (0 = none)",
                                    value=float(
                                        current["fixed_amount_per_area"]
                                        or 0.0), key=f"{key}_fixedpsf")
    return {"method": method, "stop_amount_per_area": stop or None,
            "base_year": int(base_year) or None,
            "base_year_gross_up_pct": gross_up or None,
            "base_year_amount": current["base_year_amount"],
            "fixed_amount": fixed_amount or None,
            "fixed_amount_per_area": fixed_psf or None,
            "fixed_inflation": current["fixed_inflation"],
            "structure_ref": structure or None}
