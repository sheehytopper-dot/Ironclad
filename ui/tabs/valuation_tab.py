"""Valuation tab (Phase 5 Step 5; spec §6 tab 7 — §3.18).

``ValuationInputs``: DCF (discount rate / method / convention / pv_start),
direct cap, ``Resale`` with **method-appropriate field visibility across
all five methods**, and ``SensitivityIntervals``. The whole valuation block
is optional (an exit assumption is a deal input, never a silent default —
the ``Resale`` is required whenever valuation is set, spec §3.18). Same
funnel pattern as every tab; validation errors readable (§5.4).
"""
from __future__ import annotations

import streamlit as st

from engine.models import (
    DiscountMethod,
    NOIBasis,
    PeriodConvention,
    ResaleMethod,
)
from ui import convert, session, state

DISCOUNT_METHODS = [m.value for m in DiscountMethod]
CONVENTIONS = [c.value for c in PeriodConvention]
NOI_BASES = [b.value for b in NOIBasis]
RESALE_METHODS = [m.value for m in ResaleMethod]
#: Methods that capitalize income → need an exit cap ([AE p. 465]).
CAP_METHODS = {"cap_noi_forward_12", "cap_noi_current_year",
               "gross_value_less_costs"}
SENSITIVITY_COUNTS = [5, 7]


# ------------------------------------------------------------------ #
# Pure commit function                                                #
# ------------------------------------------------------------------ #

def apply_valuation(model, payload):
    """``payload`` = a full ValuationInputs dict, or None to clear the
    valuation block."""
    def mutate(data):
        data["valuation"] = payload
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


def _resale_inputs(current: dict, key: str) -> dict:
    """Resale editor — fields appear per the selected method's needs
    ([AE pp. 464-471]): cap methods need an exit cap; ``fixed_amount`` is
    the manual's Enter Sale Price (gross AND net — no selling costs or
    adjustments, the engine refuses them); ``pct_increase_over_price``
    inflates the purchase price and takes selling costs/adjustments."""
    method = st.selectbox("Resale method", RESALE_METHODS,
                          index=RESALE_METHODS.index(
                              current.get("method", "cap_noi_forward_12")),
                          key=f"{key}_method")
    payload: dict = {"method": method}
    if method in CAP_METHODS:
        payload["exit_cap_rate"] = st.number_input(
            "Exit cap rate %", value=float(current.get("exit_cap_rate")
                                           or 6.0), key=f"{key}_cap")
    elif method == "fixed_amount":
        payload["fixed_amount"] = st.number_input(
            "Sale price $ (gross AND net — [AE p. 465])",
            value=float(current.get("fixed_amount") or 0.0),
            key=f"{key}_fixed")
        st.caption("Enter Sale Price: no selling costs or adjustments apply "
                   "(the engine refuses them for this method).")
    else:                                       # pct_increase_over_price
        payload["pct_increase"] = st.number_input(
            "Total % increase over purchase price",
            value=float(current.get("pct_increase") or 0.0),
            key=f"{key}_pct")

    resale_date = st.text_input(
        "Resale date (YYYY-MM-DD; blank = analysis end)",
        value=current.get("resale_date") or "", key=f"{key}_date")
    payload["resale_date"] = resale_date or None
    payload["apply_resale_to_cash_flow"] = st.checkbox(
        "Apply resale to cash flow",
        value=bool(current.get("apply_resale_to_cash_flow", True)),
        key=f"{key}_apply")

    if method != "fixed_amount":
        payload["selling_costs_pct"] = st.number_input(
            "Selling costs % of gross",
            value=float(current.get("selling_costs_pct", 0.0)),
            key=f"{key}_selling")
        st.caption("Adjustment amounts (± $, before selling costs "
                   "[AE p. 471])")
        adjustment_rows = st.data_editor(
            convert.resale_adjustments_to_rows(
                current.get("adjustment_amounts") or [])
            or [{c: None for c in convert.RESALE_ADJUSTMENT_COLUMNS}],
            num_rows="dynamic", key=f"{key}_adj")
        payload["adjustment_amounts"] = convert.rows_to_resale_adjustments(
            adjustment_rows)
        if method in CAP_METHODS:
            noi = current.get("noi_adjustments") or {}
            exclude = st.checkbox(
                "Exclude capital from the NOI basis (True = ledger NOI "
                "as-is)", value=bool(noi.get("exclude_capital", True)),
                key=f"{key}_exclcap")
            stabilize_on = st.checkbox(
                "Stabilize occupancy ([AE p. 469])",
                value=noi.get("stabilize_occupancy") is not None,
                key=f"{key}_stab_on")
            stabilize = None
            if stabilize_on:
                pct = st.number_input(
                    "Stabilized occupancy %",
                    value=float((noi.get("stabilize_occupancy") or {})
                                .get("occupancy_pct", 95.0)),
                    key=f"{key}_stab_pct")
                stabilize = {"occupancy_pct": pct}
            payload["noi_adjustments"] = {"exclude_capital": exclude,
                                          "stabilize_occupancy": stabilize}
    return payload


def render() -> None:
    model = st.session_state.model
    if model is None:
        st.info("Open or create a property in the sidebar first.")
        return
    rev = session.rev()
    data = model.model_dump(mode="json")
    valuation = data.get("valuation")
    st.subheader("Valuation (§3.18)")

    enabled = st.checkbox("Valuation — set", value=valuation is not None,
                          key=f"val_on_{rev}")
    if not enabled:
        if st.button("Apply valuation", key=f"val_apply_{rev}"):
            _apply_and_report(*apply_valuation(model, None),
                              "Valuation cleared.")
        return
    current = valuation or {}

    st.markdown("**DCF**")
    col1, col2 = st.columns(2)
    with col1:
        discount = st.number_input("Discount rate % (APR, unleveraged)",
                                   value=float(current.get("discount_rate")
                                               or 8.0),
                                   key=f"val_disc_{rev}")
        method = st.selectbox("Discount method", DISCOUNT_METHODS,
                              index=DISCOUNT_METHODS.index(
                                  current.get("discount_method", "annual")),
                              key=f"val_method_{rev}")
    with col2:
        convention = st.selectbox("Period convention", CONVENTIONS,
                                  index=CONVENTIONS.index(
                                      current.get("period_convention",
                                                  "end_of_period")),
                                  key=f"val_conv_{rev}")
        pv_start = st.text_input("PV start (YYYY-MM-DD; blank = analysis "
                                 "begin)", value=current.get("pv_start") or "",
                                 key=f"val_pvstart_{rev}")

    st.markdown("**Direct capitalization**")
    dc_on = st.checkbox("Direct cap — set",
                        value=current.get("direct_cap") is not None,
                        key=f"val_dc_on_{rev}")
    direct_cap = None
    if dc_on:
        dc = current.get("direct_cap") or {}
        col1, col2 = st.columns(2)
        with col1:
            dc_rate = st.number_input("Cap rate %",
                                      value=float(dc.get("cap_rate") or 6.0),
                                      key=f"val_dc_rate_{rev}")
        with col2:
            dc_basis = st.selectbox("NOI basis", NOI_BASES,
                                    index=NOI_BASES.index(
                                        dc.get("noi_basis", "year_1")),
                                    key=f"val_dc_basis_{rev}")
        direct_cap = {"cap_rate": dc_rate, "noi_basis": dc_basis}

    st.markdown("**Resale ([AE pp. 464-471])**")
    resale = _resale_inputs(current.get("resale") or {}, f"val_res_{rev}")

    st.markdown("**Sensitivity intervals ([AE pp. 451-452])**")
    sens = current.get("sensitivity_intervals") or {}
    col1, col2, col3 = st.columns(3)
    with col1:
        d_step = st.number_input("Discount-rate step %",
                                 value=float(sens.get("discount_rate_step",
                                                      0.25)),
                                 key=f"val_sens_d_{rev}")
    with col2:
        c_step = st.number_input("Cap-rate step %",
                                 value=float(sens.get("cap_rate_step", 0.25)),
                                 key=f"val_sens_c_{rev}")
    with col3:
        count = st.selectbox("Grid count", SENSITIVITY_COUNTS,
                             index=SENSITIVITY_COUNTS.index(
                                 int(sens.get("count", 5))),
                             key=f"val_sens_n_{rev}")

    if st.button("Apply valuation", key=f"val_apply_{rev}"):
        payload = {"discount_rate": discount, "discount_method": method,
                   "period_convention": convention,
                   "pv_start": pv_start or None,
                   "direct_cap": direct_cap, "resale": resale,
                   "sensitivity_intervals": {"discount_rate_step": d_step,
                                             "cap_rate_step": c_step,
                                             "count": int(count)}}
        _apply_and_report(*apply_valuation(model, payload),
                          "Valuation updated.")
