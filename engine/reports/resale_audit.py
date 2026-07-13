"""Property Resale Audit report (Phase 3 Step 4; spec §7 report 21).

One row per line of the resale calculation cascade — the [AE pp.
464-471] Results-pane decomposition: income basis window and amount,
NOI adjustments (occupancy factor [AE p. 469], capital inclusion
[AE pp. 470-471]), capitalized/base value, each named adjustment
[AE p. 471], gross sale price, selling costs, net unleveraged proceeds,
each loan's payoff (Step 3's resale-month balance), and net leveraged
proceeds. Built from the ``ResaleResult`` retained on every run ("no
silent numbers") — never recomputed.

``reconcile_to_ledger`` proves the posted ledger columns match the
audit exactly: Net Resale Proceeds carries the net unleveraged amount
and Loan Payoff at Resale the summed payoffs, both only in the resale
month (zero everywhere when ``apply_resale_to_cash_flow`` is false —
the audit detail still populates).
"""
from __future__ import annotations

import pandas as pd

from engine.calc.ledger import LOAN_PAYOFF_AT_RESALE, NET_RESALE_PROCEEDS


def resale_audit(result) -> pd.DataFrame:
    """The cascade as a two-column DataFrame (``line``, ``amount``) with
    a ``detail`` column carrying windows/factors as text."""
    resale = result.resale
    if resale is None:
        raise ValueError("this run has no resale (model.valuation is unset)")
    rows: list[tuple[str, float, str]] = []
    if resale.noi_window is not None:
        window_text = (f"{resale.method.value}: {resale.noi_window[0]}"
                       f"..{resale.noi_window[-1]}")
        rows.append(("Income basis", resale.income_basis, window_text))
        if resale.occupancy_factor != 1.0:
            rows.append(("Occupancy gross-up factor",
                         resale.occupancy_factor,
                         "NOI × Gross Up % / Average Occupancy % [AE p. 469]"))
        rows.append(("Adjusted basis", resale.adjusted_basis, ""))
    rows.append(("Base value", resale.base_value,
                 f"method {resale.method.value}"))
    if resale.capital_adjustment:
        # one-time deduction from the sale value, not capitalized (§24 #5)
        rows.append(("Capital costs deducted", resale.capital_adjustment,
                     "exclude_capital=False [AE p. 471]"))
    for name, amount in resale.adjustments:
        rows.append((f"Adjustment: {name}", amount, "[AE p. 471]"))
    rows.append(("Gross sale price", resale.gross_sale_price, ""))
    rows.append(("Selling costs", -resale.selling_costs,
                 "pct of gross sale price"))
    rows.append(("Net unleveraged proceeds", resale.net_unleveraged, ""))
    for name, payoff in resale.loan_payoffs.items():
        rows.append((f"Loan payoff: {name}", -payoff,
                     f"outstanding balance at {resale.resale_month}"))
    rows.append(("Net leveraged proceeds", resale.net_leveraged, ""))
    frame = pd.DataFrame(rows, columns=["line", "amount", "detail"])
    frame.attrs["resale_month"] = str(resale.resale_month)
    frame.attrs["applied_to_cash_flow"] = resale.applied_to_cash_flow
    return frame


def reconcile_to_ledger(audit: pd.DataFrame, result) -> pd.Series:
    """Differences between the audit's proceeds/payoff lines and the
    ledger's posted columns (exactly zero when reconciled). When the
    resale was not applied to the cash flow, the ledger columns must be
    all-zero and the differences compare against zero postings."""
    resale = result.resale
    frame = result.ledger.frame
    posted_proceeds = float(frame[NET_RESALE_PROCEEDS].sum())
    posted_payoff = float(frame[LOAN_PAYOFF_AT_RESALE].sum())
    expected_proceeds = (resale.net_unleveraged
                         if resale.applied_to_cash_flow else 0.0)
    expected_payoff = (-sum(resale.loan_payoffs.values())
                       if resale.applied_to_cash_flow else 0.0)
    audit_net = float(
        audit.loc[audit["line"] == "Net unleveraged proceeds", "amount"].iloc[0]
    )
    return pd.Series({
        "net_resale_proceeds": posted_proceeds - expected_proceeds,
        "loan_payoff_at_resale": posted_payoff - expected_payoff,
        "audit_vs_result": audit_net - resale.net_unleveraged,
        "outside_resale_month": float(
            frame[NET_RESALE_PROCEEDS].drop(resale.resale_month).abs().sum()
            + frame[LOAN_PAYOFF_AT_RESALE].drop(resale.resale_month).abs().sum()
        ),
    })
