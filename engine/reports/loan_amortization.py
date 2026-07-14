"""Loan Amortization report (Phase 4 Step 3; spec §7 report 20)
[AE p. 593].

A per-loan monthly amortization schedule — opening balance, rate,
payment, interest, principal, additional principal, ending balance —
straight from the ``LoanSchedule.frame`` the debt engine already retains
on every run (Phase 3 Step 3; "no silent numbers"). A thin view: the
report IS the schedule frame, so nothing is recomputed.

:func:`reconcile_to_ledger` proves the schedules tie to the ledger's
financing section: summed across all loans, the in-window interest,
principal (scheduled + additional + balloon), and loan costs equal the
ledger's Interest Expense / Principal Payments / Loan Costs lines exactly
(the per-loan ``interest`` / ``principal`` / ``loan_costs`` series the
ledger was assembled from — spec §4.1 pass 12).

**EXTERNALLY UNVALIDATED** by any golden (no fixture has loans); the debt
engine is validated by worked-example tests and the owner's bank-
calculator hand-check (DEVIATIONS.md §18). This report adds no math. The
engine never imports UI code (Iron Rule 1).
"""
from __future__ import annotations

import pandas as pd

from engine.calc.ledger import (
    INTEREST_EXPENSE,
    LOAN_COSTS,
    PRINCIPAL_PAYMENTS,
)
from engine.reports.base import Report, ReportMeta


def loan_amortization(result, loan_index: int = 0) -> Report:
    """Loan Amortization report (#20) for one loan (default the first) —
    its full monthly schedule (funding through maturity) as a DataFrame
    indexed by month [AE p. 593]. ``meta.extra`` records the loan name,
    funding/maturity months, principal, and any balloon."""
    schedules = result.loan_schedules
    if not schedules:
        raise ValueError("this run has no loans (model.loans is empty); the "
                         "Loan Amortization report has nothing to present")
    if not 0 <= loan_index < len(schedules):
        raise ValueError(
            f"loan_index {loan_index} out of range (run has "
            f"{len(schedules)} loan(s))")
    schedule = schedules[loan_index]
    frame = schedule.frame.copy()
    meta = ReportMeta(
        name="Loan Amortization", number=20, monetary=False,
        citation="[AE p. 593]",
        extra={
            "loan_name": schedule.loan.name,
            "loan_index": loan_index,
            "loan_count": len(schedules),
            "principal": schedule.principal0,
            "funding_month": str(schedule.funding_month),
            "maturity_month": str(schedule.maturity_month),
            "balloon": schedule.balloon,
        },
    )
    return Report(frame=frame, meta=meta)


def reconcile_to_ledger(result) -> pd.Series:
    """Summed-over-all-loans financing series minus the ledger's financing
    lines — exact zeros when the amortization schedules tie to the Cash
    Flow's Interest Expense / Principal Payments / Loan Costs (spec §4.1
    pass 12). Independent of which loan's report was built; the whole
    financing section must reconcile."""
    schedules = result.loan_schedules
    if not schedules:
        raise ValueError("this run has no loans to reconcile")
    frame = result.ledger.frame
    zeros = pd.Series(0.0, index=frame.index)
    interest = sum((s.interest for s in schedules), zeros.copy())
    principal = sum((s.principal for s in schedules), zeros.copy())
    costs = sum((s.loan_costs for s in schedules), zeros.copy())
    return pd.Series({
        "interest_expense": float((interest - frame[INTEREST_EXPENSE]).abs().sum()),
        "principal_payments": float(
            (principal - frame[PRINCIPAL_PAYMENTS]).abs().sum()),
        "loan_costs": float((costs - frame[LOAN_COSTS]).abs().sum()),
    })
