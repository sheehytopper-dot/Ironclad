"""Cash Flow report (spec §7 report 1; [AE pp. 535-539]) — the flagship
property report and the §2.3 canonical presentation of the ledger.

"Line names/order must match the ARGUS Cash Flow report so exports diff
cleanly" (CLAUDE.md; spec §2.3). This builder is a **pure view of
``ledger.frame``**: it aggregates the monthly ledger to the requested
period with the Step-1 primitives (:func:`
engine.reports.base.build_monetary_report`, which delegates to the
ledger's own ``to_annual``/``to_quarterly``/``to_fiscal_annual`` — never
separately computed, spec §2.3), applies the unit toggle, and presents
the accounts as rows in Cash Flow tree order with per-row indent / subtotal
metadata for the "expandable detail" the UI and exporter render.

Because it only re-expresses the ledger, it **reconciles to the ledger
exactly** (:func:`reconcile_to_ledger`, the pattern the audit reports
already prove). The four goldens' fiscal cash flows are the external
ARGUS-based anchor (spec §9.1) — the Benchmark Comparison report
(``engine/reports/benchmark.py``) does that line-by-line diff.

DataFrame-only, full precision (rounding is report-level, §4.3); export/
formatting is Step 6. The engine never imports UI code (Iron Rule 1).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from engine.calc.ledger import (
    CFADS,
    CFBDS,
    EGR,
    NOI,
    SCHEDULED_BASE_RENTAL_REVENUE,
    TOTAL_CAPITAL_COSTS,
    TOTAL_DEBT_SERVICE,
    TOTAL_OPERATING_EXPENSES,
    TOTAL_PGR,
)
from engine.reports.base import (
    ModelingPolicies,
    Period,
    Report,
    Unit,
    aggregate_period,
    build_monetary_report,
)

#: Rollup lines rendered flush-left (level 0); every other ledger account
#: is an indented detail line (level 1) feeding the next subtotal. These
#: are the [AE p. 538-539] Cash Flow subtotals (spec §2.3 tree).
SUBTOTAL_ACCOUNTS = frozenset({
    SCHEDULED_BASE_RENTAL_REVENUE,
    TOTAL_PGR,
    EGR,
    TOTAL_OPERATING_EXPENSES,
    NOI,
    TOTAL_CAPITAL_COSTS,
    CFBDS,
    TOTAL_DEBT_SERVICE,
    CFADS,
})


def _analysis_begin(result, analysis_begin: Optional[dt.date]) -> dt.date:
    """The analysis begin date: honored if passed, else the first ledger
    month (``result.months[0]``)."""
    if analysis_begin is not None:
        return analysis_begin
    return result.months[0].to_timestamp().date()


def _tree(accounts, ledger) -> list[dict]:
    """Per-account presentation metadata in row order: indent ``level``
    (0 subtotal, 1 detail), ``is_subtotal``, and the ``section`` the
    account belongs to (operating / capital / non_operating expense detail
    from the ledger's own column lists, else a structural section by
    position). Drives the UI's expand/collapse and the exporter's
    indentation."""
    operating = set(ledger.operating_columns)
    capital = set(ledger.capital_columns)
    non_operating = set(ledger.non_operating_columns)
    rows = []
    for account in accounts:
        is_subtotal = account in SUBTOTAL_ACCOUNTS
        if account in operating:
            section = "operating_expense"
        elif account in capital:
            section = "capital"
        elif account in non_operating:
            section = "non_operating"
        else:
            section = "structural"
        rows.append({
            "account": account,
            "level": 0 if is_subtotal else 1,
            "is_subtotal": is_subtotal,
            "section": section,
        })
    return rows


def cash_flow(result, *, unit: Unit = Unit.total, period: Period = Period.fiscal,
              policies: Optional[ModelingPolicies] = None,
              fiscal_year_end_month: int = 12,
              analysis_begin: Optional[dt.date] = None) -> Report:
    """Build the Cash Flow report (§7 report 1) from a ``RunResult``.

    Accounts run down the rows in ledger (Cash Flow tree) order; the
    requested ``period`` runs across the columns; the ``unit`` toggle
    re-expresses each cell (Total $ / per-SF / per-month / per-occupied-SF).
    ``meta.extra['tree']`` carries the per-row indent / subtotal / section
    metadata for expandable detail (spec §7 report 1)."""
    begin = _analysis_begin(result, analysis_begin)
    # Reuse the Step-1 monetary path (period aggregation + unit + rounding),
    # then transpose to the accounts-as-rows Cash Flow presentation.
    monetary = build_monetary_report(
        result.ledger.frame, name="Cash Flow", number=1, result=result,
        unit=unit, period=period, policies=policies, analysis_begin=begin,
        fiscal_year_end_month=fiscal_year_end_month,
        citation="[AE pp. 535-539]",
    )
    frame = monetary.frame.T
    frame.index.name = "account"
    meta = monetary.meta
    meta.extra["tree"] = _tree(list(frame.index), result.ledger)
    meta.extra["fiscal_year_end_month"] = fiscal_year_end_month
    return Report(frame=frame, meta=meta)


def reconcile_to_ledger(report: Report, result, *,
                        fiscal_year_end_month: int = 12,
                        analysis_begin: Optional[dt.date] = None
                        ) -> pd.DataFrame:
    """Report cells minus the ledger's own period aggregation — a frame of
    exact zeros when the Cash Flow report reconciles (the same guarantee
    the audit reports give). Defined on the **Total-$** view (per-SF / per-
    month views are that view divided by an area/count and do not tie
    dollar-for-dollar); raises if handed a non-Total report."""
    if report.meta.unit != Unit.total:
        raise ValueError(
            "reconcile_to_ledger compares Total-$ cells; rebuild the report "
            f"with unit=Unit.total (got {report.meta.unit})"
        )
    begin = _analysis_begin(result, analysis_begin)
    expected = aggregate_period(
        result.ledger.frame, report.meta.period, analysis_begin=begin,
        fiscal_year_end_month=fiscal_year_end_month,
    ).T
    expected.index.name = "account"
    return report.frame - expected.reindex(index=report.frame.index,
                                           columns=report.frame.columns)
