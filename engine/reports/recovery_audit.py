"""Recovery Audit report (spec §7 report 18) — per tenant per pool:
expenses, gross-up, stop, share, caps, fee.

"The make-or-break audit report" (spec §7): every recovery dollar in the
ledger traces to a (tenant, segment, pool, month) row here, and the
report **must reconcile exactly to the ledger** — enforced by
:func:`reconcile_to_ledger`, which BUILD_SCHEDULE Week 5 requires as the
standing debugging tool for everything recovery-shaped (owner
correction, NEXT_STEPS_TO_GATE2.md Step 5).

The builder consumes the ``PoolAudit`` detail run.py retains on every
run (spec §1.3 "no silent numbers"). DataFrame-only — no formatting, no
rounding (spec §4.3); export/formatting is Phase 4. The engine never
imports UI code (Iron Rule 1).
"""
from __future__ import annotations

import pandas as pd

from engine.calc.ledger import EXPENSE_RECOVERY_REVENUE

#: Report columns, one row per (tenant, segment, pool, month).
COLUMNS = [
    "tenant", "segment_start", "structure", "pool", "month",
    "expenses", "grossed", "admin_fee", "stop", "share",
    "pre_cap", "recovery",
]


def recovery_audit(result) -> pd.DataFrame:
    """Build the Recovery Audit report from a ``RunResult``.

    One row per (tenant, segment, pool, occupied month): the adjusted
    pool expenses, the grossed basis, the admin fee added, the monthly
    stop deducted, the tenant's share fraction, the post-share pre-cap
    amount, and the final posted recovery (post caps/floors and any
    free-rent abatement).
    """
    rows = []
    for entry in result.recovery_audit:
        for period in entry.recovery.index:
            if not (entry.start <= period <= entry.end):
                continue
            rows.append({
                "tenant": entry.tenant,
                "segment_start": entry.segment_start,
                "structure": entry.structure,
                "pool": entry.pool,
                "month": period,
                "expenses": float(entry.basis[period]),
                "grossed": float(entry.grossed[period]),
                "admin_fee": float(entry.admin_fee[period]),
                "stop": float(entry.stop[period]),
                "share": float(entry.share[period]),
                "pre_cap": float(entry.pre_cap[period]),
                "recovery": float(entry.recovery[period]),
            })
    return pd.DataFrame(rows, columns=COLUMNS)


def reconcile_to_ledger(report: pd.DataFrame, result) -> pd.Series:
    """The report's recovery total per month minus the ledger's Expense
    Recovery Revenue — exactly zero everywhere when the report reconciles
    (the Gate 2 requirement). Returns the difference series so a failure
    shows where."""
    ledger_line = result.ledger.frame[EXPENSE_RECOVERY_REVENUE]
    if report.empty:
        return -ledger_line
    totals = report.groupby("month")["recovery"].sum()
    return totals.reindex(ledger_line.index, fill_value=0.0) - ledger_line
