"""Dashboard tab (Phase 5 Step 6; spec §6 tab 9 — [AE pp. 532-534]).

KPI cards + charts, **every number read off RunResult / the report
builders — never recomputed UI-side**: year-1 NOI & occupancy via the
Step-1 ``state.dashboard_metrics`` (the ledger's own annual view),
purchase price + going-in cap from Executive Summary #2's frame, valuation
metrics straight off ``result.valuation``, the charts off the ledger's own
annual aggregation / the occupancy series / the #12 and #11 frames.

**Deliberately absent: the equity multiple.** Spec §6 lists it as a KPI,
but no engine surface computes it (neither RunResult nor any report), and
computing it UI-side would be exactly the recomputation this phase bans —
flagged as a post-Gate-5 owner decision (an engine/reports addition), not
quietly fabricated.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from engine.calc.ledger import CFBDS, NOI, to_annual
from engine.reports import executive_summary, lease_expiration, lease_summary
from ui import state


# ------------------------------------------------------------------ #
# Pure data assembly (browser-free, unit-tested)                      #
# ------------------------------------------------------------------ #

def dashboard_data(result, model) -> dict:
    """Everything the dashboard shows, from engine surfaces only."""
    exec_frame = executive_summary(result, model).frame
    exec_values = dict(zip(exec_frame["metric"], exec_frame["value"]))
    annual = to_annual(result.ledger.frame, model.property.analysis_begin)
    fye = model.property.fiscal_year_end_month
    return {
        "metrics": state.dashboard_metrics(result, model),
        "exec": exec_values,
        "valuation": result.valuation,
        "annual_noi_cf": annual[[NOI, CFBDS]],
        "occupancy": result.occupancy,
        "expiration": lease_expiration(result,
                                       fiscal_year_end_month=fye).frame,
        "top_tenants": lease_summary(result).frame.sort_values(
            "annual_base_rent", ascending=False).head(10).reset_index(
            drop=True),
    }


def _fmt_currency(value) -> str:
    return (state.format_currency(float(value))
            if value is not None and not pd.isna(value) else "—")


def _fmt_pct(value) -> str:
    return (f"{float(value):.2f}%"
            if value is not None and not pd.isna(value) else "—")


# ------------------------------------------------------------------ #
# Renderer                                                            #
# ------------------------------------------------------------------ #

def render() -> None:
    model = st.session_state.get("model")
    result = st.session_state.get("result")
    if model is None:
        st.info("Open or create a property in the sidebar to begin.")
        return
    st.subheader(model.property.name)
    path = st.session_state.get("model_path")
    st.caption(f"File: {path}" if path else "Not saved yet.")
    if result is None:
        st.info("Press **Calculate** in the sidebar to populate the "
                "dashboard.")
        return

    data = dashboard_data(result, model)
    metrics = data["metrics"]
    valuation = data["valuation"]

    # the mockup's six KPI cards (styled by ui/theme.py); the two
    # lower-traffic figures move to the caption line below
    row = st.columns(3)
    row[0].metric("Year-1 NOI", state.format_currency(metrics["year1_noi"]))
    row[1].metric("Year-1 Occupancy",
                  state.format_pct(metrics["year1_occupancy_pct"]))
    row[2].metric("Going-in Cap Rate",
                  _fmt_pct(data["exec"].get("Going-in Cap Rate (%)")))
    row = st.columns(3)
    row[0].metric("Purchase Price",
                  _fmt_currency(data["exec"].get("Purchase Price")))
    row[1].metric("Unleveraged PV",
                  _fmt_currency(getattr(valuation, "unleveraged_pv", None)))
    row[2].metric("IRR (unleveraged)",
                  _fmt_pct(getattr(valuation, "unleveraged_irr", None)))
    st.caption(
        "IRR (leveraged): "
        f"{_fmt_pct(getattr(valuation, 'leveraged_irr', None))} · "
        "Direct Cap Value: "
        f"{_fmt_currency(getattr(valuation, 'direct_cap_value', None))} · "
        "Equity multiple: not computed by the engine (no RunResult/report "
        "surface carries it) — flagged as a post-Gate-5 engine addition "
        "rather than recomputed UI-side.")

    import plotly.express as px

    from ui import theme

    chart_frame = data["annual_noi_cf"].reset_index(names="year").melt(
        id_vars="year", var_name="line", value_name="amount")
    noi_fig = px.bar(chart_frame, x="year", y="amount", color="line",
                     barmode="group",
                     title="Annual NOI & CFBDS (the ledger's own annual "
                     "view)")
    noi_fig.update_layout(**theme.plotly_layout())
    occupancy = data["occupancy"]
    occupancy_frame = pd.DataFrame(
        {"month": occupancy.index.astype(str),
         "occupancy_pct": occupancy.to_numpy() * 100.0})
    occ_fig = px.line(occupancy_frame, x="month", y="occupancy_pct",
                      title="Occupancy (monthly)")
    occ_fig.update_layout(**theme.plotly_layout(
        yaxis=dict(gridcolor=theme.HAIRLINE, range=[0, 105],
                   ticksuffix="%")))
    col_left, col_right = st.columns(2)
    with col_left:
        st.plotly_chart(noi_fig, key="chart_noi")
    with col_right:
        st.plotly_chart(occ_fig, key="chart_occ")
    expiration = data["expiration"]
    if not expiration.empty:
        exp_fig = px.bar(expiration, x="fiscal_year", y="expiring_sf",
                         color="status",
                         title="Lease expirations (SF by fiscal year; "
                         "Contractual vs Speculative)")
        exp_fig.update_layout(**theme.plotly_layout())
        st.plotly_chart(exp_fig, key="chart_exp")
    st.markdown("**Top tenants (by contractual annual base rent — report "
                "#11)**")
    from ui import format as fmt
    st.dataframe(fmt.frame_display(data["top_tenants"]), key="top_tenants",
                 width="stretch", row_height=theme.DENSE_ROW_HEIGHT)
