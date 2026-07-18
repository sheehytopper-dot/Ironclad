"""Shared nested-detail widgets for revenue/expense items (Phase 5 Step 3).

Each helper renders Streamlit inputs seeded from the item's current dump
and returns the model-shaped payload dict — validation happens in the
:func:`ui.state.updated_model` funnel, never here. Iron Rule 1: engine
imports only.
"""
from __future__ import annotations

from typing import Optional

import streamlit as st

from engine.models import TimingMethod
from ui import convert

TIMING_METHODS = [m.value for m in TimingMethod]


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
