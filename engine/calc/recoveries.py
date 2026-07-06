"""Expense recoveries — system methods (Phase 1 net/none; Phase 2 Step 5
session 1 adds stops, base years, fixed) [AE pp. 404-413].

System methods, per the manual's definitions [AE pp. 405-406, 408-409]:

- ``net`` — "all recoverable expenses ... based on their proportionate
  share of the building area": recovery = pool × share.
- ``base_stop`` — a **building** $/SF stop: the tenant reimburses its
  share of recoverable expenses over the building stop amount
  (stop $/SF × denominator area), floored at 0.
- ``base_year`` / ``base_year_plus_1`` — the stop is the **actual
  recoverable expenses of the base year, frozen**: the lease-start
  calendar year (or the year after, for +1), or the explicit
  ``base_year``; "tenants with leases that begin before the analysis
  start will pay their pro-rata share of any increases over the amount of
  reimbursable expenses in the first year of the analysis" [AE p. 408] —
  pre-analysis starts use analysis year 1 for both variants (the manual's
  +1 fallback [AE p. 409]). A base-year window truncated by the timeline
  is annualized from its available months (a month-level convention
  annual golden data cannot discriminate; disputes go to owner per-cell
  adjudication).
- ``fixed`` — a **tenant** amount [AE p. 409]: ``fixed_amount`` $/yr or
  ``fixed_amount_per_area`` $/SF/yr × tenant area, flat unless
  ``fixed_inflation`` names an index or schedule (opt-in inflation).

Posting is straight monthly accrual (spec §3.14 v1 policy): monthly
recovery = max(0, pool_m − stop/12) × share — the annualized-with-true-up
computation is a deferred policy toggle. Recoveries floor at 0: a tenant
never pays the landlord's stop. Gross-up (including
``base_year_gross_up_pct``) is a user-structure feature — system
structures are never grossed up [AE p. 406] — and arrives with user
structures, caps/floors [AE pp. 411-412], admin fees [AE pp. 519-520],
denominators [AE p. 410], and adjustments in Step 5 session 2; until then
those inputs raise loudly.

Pool membership follows ``ExpenseItem.is_recoverable`` (spec §3.11).
%-of-EGR members enter at whatever series run.py's fixed point supplies
(spec §4.1 step 9, DEVIATIONS.md §6). **Convergence with stops:**
max(0, ·) is 1-Lipschitz, and a fee perturbation reaches a stop-method
recovery both directly (through the month's pool) and through the frozen
base-year stop (opposite sign), so the recovery response is bounded by
2 × share — the fee update stays a contraction with factor
≤ 2 × Σ(share × pct), far below 1 for any realistic fee, and run.py's
iteration cap still turns pathological inputs into a loud error.

Everything returns a monthly Period[M]-indexed Series (spec §2.3);
recoveries post to Expense Recovery Revenue. The engine never imports UI
code (Iron Rule 1).
"""
from __future__ import annotations

import datetime as dt
from typing import Iterable, Optional, Union

import pandas as pd

from engine.calc.inflation import index_schedule, inflation_factors
from engine.calc.leases import lease_term_periods
from engine.calc.timeline import snap_to_month_start
from engine.models import (
    ExpenseItem,
    Inflation,
    Lease,
    RecoveryAssignment,
    RecoverySystemMethod,
)

#: (item, projected monthly series) pairs, as produced by
#: engine.calc.expenses.project_expense over the same timeline.
ExpenseSeries = Iterable[tuple[ExpenseItem, pd.Series]]


def _area_at(rentable_area: Union[pd.Series, float], period: pd.Period) -> float:
    if isinstance(rentable_area, pd.Series):
        return float(rentable_area[period])
    return float(rentable_area)


def recoverable_pool(expenses: ExpenseSeries, months: pd.PeriodIndex) -> pd.Series:
    """Sum the recoverable expenses into one monthly pool series.

    Membership is ``ExpenseItem.is_recoverable`` — the explicit flag, else
    the category default (operating in; capital and non-operating out,
    spec §3.11). Series are taken as projected: a %-of-EGR fee contributes
    whatever fixed-point series the caller resolved (spec §4.1 step 9).
    """
    pool = pd.Series(0.0, index=months, name="recoverable_pool")
    for item, series in expenses:
        if item.is_recoverable:
            pool += series.reindex(months, fill_value=0.0)
    return pool


def net_recoveries(lease: Lease, months: pd.PeriodIndex, pool: pd.Series,
                   rentable_area: Union[pd.Series, float]) -> pd.Series:
    """Net system method [AE p. 405]: the tenant pays its proportionate
    share — lease area / rentable area — of the pool expense each occupied
    month of the contract term. No stop, no gross-up [AE p. 406], no cap;
    100% of the share, monthly accrual (spec §3.14 v1 policy)."""
    series = pd.Series(0.0, index=months, name="expense_recovery")
    start, end = lease_term_periods(lease)
    for period in months:
        if start <= period <= end:
            share = lease.area / _area_at(rentable_area, period)
            series[period] = float(pool[period]) * share
    return series


# ------------------------------------------------------------------ #
# System-method dispatch over an occupancy window                     #
# ------------------------------------------------------------------ #

def _base_year_window(assignment: RecoveryAssignment,
                      method: RecoverySystemMethod, start: pd.Period,
                      analysis_begin: Optional[dt.date],
                      where: str) -> tuple[pd.Period, pd.Period]:
    """The frozen base-year window [AE pp. 405-406, 408-409]: the explicit
    ``base_year`` (shifted +1 for the +1 method), else the lease-start
    calendar year (+1); leases starting before the analysis use analysis
    year 1 for both variants."""
    plus = 12 if method == RecoverySystemMethod.base_year_plus_1 else 0
    if assignment.base_year is not None:
        first = pd.Period(f"{assignment.base_year}-01", freq="M") + plus
        return first, first + 11
    if analysis_begin is None:
        raise ValueError(f"{where}: base-year recoveries need analysis_begin")
    begin = pd.Period(snap_to_month_start(analysis_begin), freq="M")
    if start < begin:
        return begin, begin + 11  # analysis year 1 [AE pp. 408-409]
    first = pd.Period(f"{start.year}-01", freq="M") + plus
    return first, first + 11


def _frozen_stop_annual(pool: pd.Series,
                        window: tuple[pd.Period, pd.Period],
                        where: str) -> float:
    """The base-year pool total, frozen. A window truncated by the
    timeline annualizes from its available months (module docstring)."""
    lo, hi = window
    available = pool[(pool.index >= lo) & (pool.index <= hi)]
    if available.empty:
        raise ValueError(
            f"{where}: base year {lo}..{hi} lies entirely outside the "
            "analysis timeline"
        )
    total = float(available.sum())
    if len(available) < 12:
        total *= 12.0 / len(available)
    return total


def _fixed_annual_series(assignment: RecoveryAssignment, area: float,
                         months: pd.PeriodIndex,
                         analysis_begin: Optional[dt.date],
                         inflation: Optional[Inflation],
                         where: str) -> pd.Series:
    """The fixed method's annual tenant amount per month [AE p. 409]:
    flat unless ``fixed_inflation`` opts into an index or schedule."""
    annual = (assignment.fixed_amount
              if assignment.fixed_amount is not None
              else assignment.fixed_amount_per_area * area)
    ref = assignment.fixed_inflation
    if ref is None:
        return pd.Series(float(annual), index=months)
    if analysis_begin is None:
        raise ValueError(f"{where}: inflated fixed recoveries need "
                         "analysis_begin")
    if isinstance(ref, list):
        rates = ref
        month = inflation.inflation_month if inflation is not None else None
        basis_kwargs = ({"timing_basis": inflation.timing_basis}
                        if inflation is not None else {})
    else:
        if inflation is None:
            raise ValueError(f"{where}: fixed_inflation {ref!r} needs the "
                             "property inflation assumptions")
        rates = index_schedule(inflation, ref)
        month = inflation.inflation_month
        basis_kwargs = {"timing_basis": inflation.timing_basis}
    factors = inflation_factors(rates, months, analysis_begin, month,
                                **basis_kwargs)
    return annual * factors


def _window_recoveries(assignment: RecoveryAssignment, area: float,
                       start: pd.Period, end: pd.Period,
                       months: pd.PeriodIndex, expenses: ExpenseSeries,
                       rentable_area: Union[pd.Series, float], where: str,
                       analysis_begin: Optional[dt.date],
                       inflation: Optional[Inflation]) -> pd.Series:
    method = assignment.method
    series = pd.Series(0.0, index=months, name="expense_recovery")
    if method == RecoverySystemMethod.none:
        return series

    if method == RecoverySystemMethod.fixed:
        annual = _fixed_annual_series(assignment, area, months,
                                      analysis_begin, inflation, where)
        for period in months:
            if start <= period <= end:
                series[period] = float(annual[period]) / 12.0
        return series

    if method == RecoverySystemMethod.structure:
        raise NotImplementedError(
            f"{where}: user recovery structures arrive in Phase 2 Step 5 "
            "session 2 (spec §10); system methods only until then"
        )

    pool = recoverable_pool(expenses, months)

    if method == RecoverySystemMethod.net:
        stop_monthly = pd.Series(0.0, index=months)
    elif method == RecoverySystemMethod.base_stop:
        # a building stop: $/SF × denominator area [AE p. 409]
        stop_monthly = pd.Series(
            [assignment.stop_amount_per_area * _area_at(rentable_area, p) / 12.0
             for p in months], index=months,
        )
    elif method in (RecoverySystemMethod.base_year,
                    RecoverySystemMethod.base_year_plus_1):
        if assignment.base_year_gross_up_pct is not None:
            raise NotImplementedError(
                f"{where}: base-year gross-up is a user-structure feature "
                "(system structures are never grossed up [AE p. 406]) and "
                "arrives in Phase 2 Step 5 session 2"
            )
        window = _base_year_window(assignment, method, start,
                                   analysis_begin, where)
        stop_annual = _frozen_stop_annual(pool, window, where)
        stop_monthly = pd.Series(stop_annual / 12.0, index=months)
    else:  # pragma: no cover - exhaustive over RecoverySystemMethod
        raise ValueError(f"unhandled recovery method {method!r}")

    for period in months:
        if start <= period <= end:
            share = area / _area_at(rentable_area, period)
            excess = float(pool[period]) - float(stop_monthly[period])
            series[period] = max(0.0, excess) * share  # never pay the stop
    return series


def project_recoveries(lease: Lease, months: pd.PeriodIndex,
                       expenses: ExpenseSeries,
                       rentable_area: Union[pd.Series, float],
                       analysis_begin: Optional[dt.date] = None,
                       inflation: Optional[Inflation] = None) -> pd.Series:
    """Project one lease's contract-term expense recoveries onto the
    monthly timeline (spec §4.1 step 6) per its system method
    [AE pp. 405-406, 408-409]. User structures arrive in Step 5
    session 2."""
    start, end = lease_term_periods(lease)
    return _window_recoveries(
        lease.recoveries, lease.area, start, end, months, expenses,
        rentable_area, where=f"lease {lease.tenant_name!r}",
        analysis_begin=analysis_begin, inflation=inflation,
    )


def project_segment_recoveries(segment, months: pd.PeriodIndex,
                               expenses: ExpenseSeries,
                               rentable_area: Union[pd.Series, float],
                               analysis_begin: Optional[dt.date] = None,
                               inflation: Optional[Inflation] = None,
                               ) -> pd.Series:
    """Recoveries for one resolved lease segment (contract or speculative).
    The segment's own ``RecoveryAssignment`` governs — speculative
    segments recover per their MLP (spec §3.6 [AE pp. 239-240]); a
    base-year segment's base year is its own start year (each segment is
    a new lease; the manual's Continue Prior carry-over is not modeled,
    DEVIATIONS.md §7). Recoveries post over occupied months only:
    downtime months post nothing (golden #1's FY2029 confirms)."""
    return _window_recoveries(
        segment.recoveries, segment.area, segment.start, segment.end,
        months, expenses, rentable_area,
        where=f"lease {segment.lease.tenant_name!r} segment {segment.start}",
        analysis_begin=analysis_begin, inflation=inflation,
    )
