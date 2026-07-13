"""Lease Audit report (spec §7 report 16) — per-tenant monthly rent
build-up.

The Cash Flow's Potential Base Rent line hyperlinks here: "clicking on
Potential Base Rent leads to the Lease Audit report, where you can
examine potential rent on a tenant by tenant basis" [AE p. 535]. Each
row decomposes one tenant-month into the rental-revenue section's lines
[AE p. 538]: base rent (potential — in-place rent, downtime market rent,
and pre-absorption vacant space at market), absorption & turnover
vacancy, free rent, the Scheduled Base Rent identity (base + A&T + free),
CPI, percentage rent (Step 8; externally unvalidated pending golden #3 —
CLAUDE.md standing gap), miscellaneous tenant items (§4.1 pass 8; also
externally unvalidated — no golden uses them), and expense recoveries,
with a phase label from the resolved chain (contract / speculative /
downtime / reabsorbed / vacant).

Built from the detail ``RunResult`` retains on every run (spec §1.3 "no
silent numbers") and **reconciling exactly to the ledger's revenue
lines** via :func:`reconcile_to_ledger` — owner review of this report
and the Recovery Audit is a Gate 2 criterion (NEXT_STEPS_TO_GATE2.md).
DataFrame-only, full precision (spec §4.3); export/formatting is
Phase 4. The engine never imports UI code (Iron Rule 1).
"""
from __future__ import annotations

import pandas as pd

from engine.calc.ledger import (
    ABSORPTION_TURNOVER_VACANCY,
    BASE_RENTAL_REVENUE,
    CPI_ADJUSTMENT_REVENUE,
    EXPENSE_RECOVERY_REVENUE,
    FREE_RENT,
    MISC_TENANT_REVENUE,
    PERCENTAGE_RENT,
)

#: Report columns, one row per (tenant, month) with activity.
COLUMNS = [
    "tenant", "month", "phase", "base_rent", "absorption_vacancy",
    "free_rent", "scheduled", "cpi", "percentage_rent", "misc",
    "recoveries", "total_tenant_revenue",
]

#: report column → ledger Cash Flow line it must sum to.
_RECONCILED_LINES = {
    "base_rent": BASE_RENTAL_REVENUE,
    "absorption_vacancy": ABSORPTION_TURNOVER_VACANCY,
    "free_rent": FREE_RENT,
    "cpi": CPI_ADJUSTMENT_REVENUE,
    "percentage_rent": PERCENTAGE_RENT,
    "misc": MISC_TENANT_REVENUE,
    "recoveries": EXPENSE_RECOVERY_REVENUE,
}


def _phase(segments, period: pd.Period) -> str:
    """Lease-phase label for one month from the resolved chain: contract
    or speculative occupancy, rollover downtime, reabsorbed (months after
    a 'reabsorb' lease expires — the space carries its market value in
    base rent and A&T until absorption re-leases it, DEVIATIONS.md §8),
    else vacant (which for a not-yet-absorbed space still carries its
    market value in base rent and A&T [AE p. 538]). An
    absorption-generated lease's first generation is the chain's contract
    segment mechanically, but the manual shows absorption leases as
    speculative [AE p. 398] — the lease's own status wins the label."""
    for segment in segments:
        if segment.start <= period <= segment.end:
            if segment.speculative or segment.lease.status.value == "speculative":
                return "speculative"
            return "contract"
        if (segment.downtime_months
                and segment.downtime_start <= period < segment.start):
            return "downtime"
    last = segments[-1] if segments else None
    if (last is not None and period > last.end
            and last.lease.upon_expiration.value == "reabsorb"):
        return "reabsorbed"
    return "vacant"


def lease_audit(result) -> pd.DataFrame:
    """Build the Lease Audit report from a ``RunResult``: one row per
    (tenant, month) with any activity, decomposing the tenant's revenue
    per the Cash Flow rental-revenue definitions [AE p. 538] — Scheduled
    Base Rent is "the potential rent minus vacancy and free rent", CPI
    posts separately, recoveries join as other tenant revenue."""
    rows = []
    for tenant, rents in result.lease_rents.items():
        vacancy = result.absorption_vacancy[tenant]
        recoveries = result.recoveries[tenant]
        pct_rent = result.percentage_rent[tenant]
        misc_series = result.misc_tenant_revenue[tenant]
        segments = result.segments[tenant]
        for period in result.months:
            base = float(rents.base_rent[period])
            at = float(vacancy[period])
            free = float(rents.free_rent[period])
            cpi = float(rents.cpi_adjustment[period])
            pct = float(pct_rent[period])
            misc = float(misc_series[period])
            recovery = float(recoveries[period])
            if not any((base, at, free, cpi, pct, misc, recovery)):
                continue
            scheduled = base + at + free
            rows.append({
                "tenant": tenant,
                "month": period,
                "phase": _phase(segments, period),
                "base_rent": base,
                "absorption_vacancy": at,
                "free_rent": free,
                "scheduled": scheduled,
                "cpi": cpi,
                "percentage_rent": pct,
                "misc": misc,
                "recoveries": recovery,
                "total_tenant_revenue": scheduled + cpi + pct + misc + recovery,
            })
    return pd.DataFrame(rows, columns=COLUMNS)


def lease_audit_report(result):
    """The Lease Audit as a :class:`~engine.reports.base.Report` (spec §7
    report 16), conforming to the Phase 4 builder contract. Per-tenant
    per-month detail — not an account-tree ledger view — so ``monetary``
    is False and the unit/period toggles pass it through untouched; the
    frame and :func:`reconcile_to_ledger` are unchanged."""
    from engine.reports.base import Report, ReportMeta

    frame = lease_audit(result)
    meta = ReportMeta(name="Lease Audit", number=16, monetary=False,
                      citation="[AE pp. 535, 538]")
    return Report(frame=frame, meta=meta)


def reconcile_to_ledger(report: pd.DataFrame, result) -> pd.DataFrame:
    """Per-month report totals minus the ledger's revenue lines — a frame
    of exact zeros when the report reconciles (the Gate 2 requirement).
    Columns are the reconciled report columns; a nonzero cell names the
    month and line that disagree."""
    frame = result.ledger.frame
    differences = {}
    for column, account in _RECONCILED_LINES.items():
        ledger_line = frame[account]
        if report.empty:
            differences[column] = -ledger_line
            continue
        totals = report.groupby("month")[column].sum()
        differences[column] = (
            totals.reindex(ledger_line.index, fill_value=0.0) - ledger_line
        )
    return pd.DataFrame(differences)
