"""Audit tab (Phase 5 Step 6; spec §6 tab 10 — the drill-down).

Pick any ledger account + month → the per-tenant / per-item composition,
straight off the audit reports and the RunResult per-tenant detail (spec
§2.3 principle 3: no silent numbers). Plus the two remaining D6-amendment
inspection surfaces (NEXT_STEPS_TO_PHASE5.md Step 0 D6; Gate 5 criterion
6):

* **Freeport B — the General Vacancy basis decomposition**: the month's
  candidate bases (the six PGR components, amounts read from the LEDGER —
  never recomputed), which of them the model's method includes, the GV
  the ledger posted, and the implied rate on each candidate basis — so
  the "which basis makes the stated rate reconcile" question is
  inspectable.
* **Cedar Alt B — the recovery-timing drill**: the Recovery Audit
  filterable by tenant + ``segment_start`` (the audit already carries one
  row per (tenant, segment_start, pool, month)), so rollover recovery
  timing ([AE p. 520] Calculation Frequency) is inspectable per lease.

Everything here is presentation over existing engine output — no engine
change (the D6-amendment premise, verified in Step 0).
"""
from __future__ import annotations

from typing import Optional

import pandas as pd
import streamlit as st

from engine.calc.ledger import (
    ABSORPTION_TURNOVER_VACANCY,
    BASE_RENTAL_REVENUE,
    CPI_ADJUSTMENT_REVENUE,
    CREDIT_LOSS,
    EXPENSE_RECOVERY_REVENUE,
    FREE_RENT,
    GENERAL_VACANCY,
    INTEREST_EXPENSE,
    LEASING_COMMISSIONS,
    LOAN_COSTS,
    MISC_TENANT_REVENUE,
    PERCENTAGE_RENT,
    PRINCIPAL_PAYMENTS,
    PROPERTY_REVENUE,
    SCHEDULED_BASE_RENTAL_REVENUE,
    TENANT_IMPROVEMENTS,
    TOTAL_DEBT_SERVICE,
)
from engine.reports import lease_audit_report, recovery_audit_report
from ui import format as fmt

#: Ledger revenue account → its Lease Audit column (the [AE p. 538]
#: decomposition the audit carries per (tenant, month)).
LEASE_AUDIT_COLUMNS = {
    BASE_RENTAL_REVENUE: "base_rent",
    ABSORPTION_TURNOVER_VACANCY: "absorption_vacancy",
    FREE_RENT: "free_rent",
    SCHEDULED_BASE_RENTAL_REVENUE: "scheduled",
    CPI_ADJUSTMENT_REVENUE: "cpi",
    PERCENTAGE_RENT: "percentage_rent",
    MISC_TENANT_REVENUE: "misc",
    EXPENSE_RECOVERY_REVENUE: "recoveries",
}
_LOAN_ACCOUNTS = {INTEREST_EXPENSE: "interest", PRINCIPAL_PAYMENTS:
                  "principal", LOAN_COSTS: None, TOTAL_DEBT_SERVICE: None}
PGR_COMPONENTS = [SCHEDULED_BASE_RENTAL_REVENUE, CPI_ADJUSTMENT_REVENUE,
                  PERCENTAGE_RENT, EXPENSE_RECOVERY_REVENUE,
                  MISC_TENANT_REVENUE, PROPERTY_REVENUE]


# ------------------------------------------------------------------ #
# Pure composition                                                    #
# ------------------------------------------------------------------ #

def audit_composition(result, model, account: str, month
                      ) -> tuple[Optional[pd.DataFrame], str]:
    """The composition of ``ledger[account][month]``: a rows frame + a
    caption saying where the rows come from. ``(None, caption)`` when the
    account has no drill (a subtotal) or a dedicated panel (GV/CL)."""
    month = pd.Period(month, freq="M")
    ledger_value = float(result.ledger.frame.loc[month, account])

    if account in (GENERAL_VACANCY, CREDIT_LOSS):
        return None, (f"{account} {month}: {ledger_value:,.2f} — see the "
                      "General Vacancy basis panel below (the D6 Freeport B "
                      "surface).")

    if account in LEASE_AUDIT_COLUMNS:
        column = LEASE_AUDIT_COLUMNS[account]
        audit = lease_audit_report(result).frame
        rows = audit[audit["month"] == month][
            ["tenant", "phase", column]].copy()
        rows = rows[rows[column] != 0.0].sort_values(column,
                                                     ascending=False)
        caption = (f"{account} {month}: {ledger_value:,.2f} — per-tenant "
                   "rows from the Lease Audit ([AE p. 538] decomposition); "
                   "they sum to the ledger line exactly "
                   "(reconcile_lease_audit, 1e-9).")
        if account == EXPENSE_RECOVERY_REVENUE:
            caption += (" Pool-level detail: the recovery-timing drill "
                        "below (the D6 Cedar Alt B surface).")
        return rows.reset_index(drop=True), caption

    if account == PROPERTY_REVENUE:
        names = [f"{kind}: {item.name}" for kind, collection in
                 (("miscellaneous", model.miscellaneous_revenues),
                  ("parking", model.parking_revenues),
                  ("storage", model.storage_revenues))
                 for item in collection]
        return None, (f"{account} {month}: {ledger_value:,.2f} — the sum of "
                      f"the §3.10 revenue items ({', '.join(names) or 'none'}"
                      "); per-item monthly series are not retained on "
                      "RunResult, so no per-item drill exists (stated, not "
                      "fabricated).")

    if account in (TENANT_IMPROVEMENTS, LEASING_COMMISSIONS):
        source = (result.tenant_improvements
                  if account == TENANT_IMPROVEMENTS
                  else result.leasing_commissions)
        rows = pd.DataFrame(
            [{"tenant": tenant, "amount": float(series.loc[month])}
             for tenant, series in source.items()
             if float(series.loc[month]) != 0.0])
        return rows, (f"{account} {month}: {ledger_value:,.2f} — per-tenant "
                      "postings from RunResult (lump-sum at segment start, "
                      "[AE pp. 246-247]).")

    if account in _LOAN_ACCOUNTS:
        column = _LOAN_ACCOUNTS[account]
        rows = []
        for i, schedule in enumerate(result.loan_schedules):
            frame = schedule.frame
            if month in frame.index:
                value = (float(frame.loc[month, column]) if column
                         else float("nan"))
                rows.append({"loan": f"{i}: {schedule.loan.name}",
                             "amount": value})
        return (pd.DataFrame(rows) if rows else None), (
            f"{account} {month}: {ledger_value:,.2f} — per-loan schedule "
            "rows (report #20 has the full amortization).")

    # expense accounts: per-item projected series
    rows = [{"item": item.name, "category": item.category.value,
             "amount": float(series.loc[month])}
            for item, series in result.expense_series
            if (item.account or item.name) == account
            and float(series.loc[month]) != 0.0]
    if rows:
        return pd.DataFrame(rows), (
            f"{account} {month}: {ledger_value:,.2f} — the expense items "
            "posting to this account (projected series off RunResult; the "
            "series are positive amounts, the ledger posts expenses "
            "negative).")

    return None, (f"{account} {month}: {ledger_value:,.2f} — a subtotal or "
                  "single-source line; pick a component account for a "
                  "drill.")


def gv_basis_rows(result, model, month) -> tuple[pd.DataFrame, dict]:
    """The Freeport B panel data: candidate GV bases at ``month`` read from
    the LEDGER (never recomputed), the model's method/config, the posted
    GV, and the implied rate on each candidate basis."""
    month = pd.Period(month, freq="M")
    ledger = result.ledger.frame
    gv = model.general_vacancy
    method = gv.method.value if gv is not None else "none"
    include = set(gv.include_in_pgr_accounts) if gv is not None else set()
    if method == "percent_of_pgr":
        included = set(PGR_COMPONENTS)
    elif method == "percent_of_total_tenant_revenue":
        included = set(PGR_COMPONENTS) - {PROPERTY_REVENUE}
    elif method == "percent_of_scheduled_base_plus":
        included = {SCHEDULED_BASE_RENTAL_REVENUE} | include
    else:
        included = set()
    rows = pd.DataFrame(
        [{"component": account,
          "amount": float(ledger.loc[month, account]),
          "included_in_basis": account in included}
         for account in PGR_COMPONENTS])
    basis = float(rows.loc[rows["included_in_basis"], "amount"].sum())
    gv_posted = float(ledger.loc[month, GENERAL_VACANCY])
    summary = {
        "method": method,
        "reduce_by_absorption_turnover": (
            bool(gv.reduce_by_absorption_turnover) if gv else None),
        "excluded_tenants": ([o.tenant_ref for o in gv.tenant_overrides
                              if o.exclude] if gv else []),
        "gv_posted": gv_posted,
        "at_vacancy_posted": float(
            ledger.loc[month, ABSORPTION_TURNOVER_VACANCY]),
        "basis_total": basis,
        "implied_rate_pct": (-gv_posted / basis * 100.0) if basis else None,
    }
    return rows, summary


def recovery_drill_options(result) -> tuple[list[str], list[str]]:
    """(tenants, segment_starts) present in the Recovery Audit."""
    frame = recovery_audit_report(result).frame
    tenants = sorted(frame["tenant"].unique())
    starts = sorted(str(s) for s in frame["segment_start"].unique())
    return tenants, starts


def filter_recovery_audit(frame: pd.DataFrame, *,
                          tenant: Optional[str] = None,
                          segment_start=None,
                          month=None) -> pd.DataFrame:
    """The Cedar Alt B drill: a pure row filter over the Recovery Audit
    frame (tenant / segment_start / month)."""
    out = frame
    if tenant:
        out = out[out["tenant"] == tenant]
    if segment_start is not None:
        out = out[out["segment_start"].astype(str) == str(segment_start)]
    if month is not None:
        out = out[out["month"].astype(str) == str(month)]
    return out.reset_index(drop=True)


# ------------------------------------------------------------------ #
# Renderer                                                            #
# ------------------------------------------------------------------ #

def render() -> None:
    result = st.session_state.get("result")
    model = st.session_state.get("model")
    if model is None:
        st.info("Open or create a property in the sidebar first.")
        return
    if result is None:
        st.info("Press **Calculate** in the sidebar to populate the audit "
                "drill-down.")
        return
    st.subheader("Audit drill-down (§2.3: no silent numbers)")

    accounts = list(result.ledger.frame.columns)
    months = [str(p) for p in result.ledger.frame.index]
    col1, col2 = st.columns(2)
    with col1:
        account = st.selectbox("Account", accounts, key="audit_account")
    with col2:
        month = st.selectbox("Month", months, key="audit_month")
    rows, caption = audit_composition(result, model, account, month)
    st.caption(caption)
    if rows is not None and not rows.empty:
        # display-only formatting — the pure composition stays raw
        st.dataframe(fmt.frame_display(rows), key="audit_rows",
                     width="stretch")

    st.markdown("---")
    st.markdown("**General Vacancy basis decomposition** — the parked "
                "Freeport B inspection surface (D6 amendment)")
    gv_rows, summary = gv_basis_rows(result, model, month)
    st.dataframe(fmt.frame_display(gv_rows), key="gv_rows",
                 width="stretch")
    display_summary = dict(summary)
    for key in ("gv_posted", "at_vacancy_posted", "basis_total"):
        display_summary[key] = fmt.money(summary[key], 2)
    if summary["implied_rate_pct"] is not None:
        display_summary["implied_rate_pct"] = fmt.percent(
            summary["implied_rate_pct"], 2)
    st.json(display_summary)

    st.markdown("---")
    st.markdown("**Recovery-timing drill** — the parked Cedar Alt B "
                "inspection surface (D6 amendment; [AE p. 520] Calculation "
                "Frequency)")
    frame = recovery_audit_report(result).frame
    tenants, starts = recovery_drill_options(result)
    col1, col2 = st.columns(2)
    with col1:
        tenant = st.selectbox("Tenant", ["(all)"] + tenants,
                              key="drill_tenant")
    with col2:
        start = st.selectbox("Segment start", ["(all)"] + starts,
                             key="drill_start")
    drilled = filter_recovery_audit(
        frame,
        tenant=None if tenant == "(all)" else tenant,
        segment_start=None if start == "(all)" else start)
    st.dataframe(fmt.frame_display(drilled, decimals=2),
                 key="drill_rows", width="stretch")
    st.caption(f"{len(drilled)} Recovery Audit rows — one per (tenant, "
               "segment_start, pool, month); reconciles to the ledger "
               "exactly (reconcile_to_ledger, 1e-9).")
