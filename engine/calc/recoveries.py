"""Simple net expense recoveries (Phase 1; spec §4.1 step 6)
[AE pp. 404-413].

The ``net`` system method recovers "all recoverable expenses ... based on
their proportionate share of the building area" [AE p. 405]:

    recovery[m] = pool expense[m] × lease area / rentable area[m]

posted as straight monthly accrual (the spec §3.14 v1 policy — no
reconciliation-month true-up) for each month of the contract term, zero
outside it and outside the analysis window.

Pool membership follows ``ExpenseItem.is_recoverable`` (spec §3.11:
operating expenses default recoverable; capital and non-operating default
not). %-of-EGR members — the Clorox-shape management fee — enter the pool
at whatever projected series the caller supplies; the circularity
(recoveries feed EGR, EGR feeds the fee, the fee feeds recoveries) is
resolved by run.py's ordered/two-pass fixed point (spec §4.1 step 9),
never inside this module.

System recovery structures are never grossed up [AE p. 406]; gross-up
belongs to user structures only, and then only to expenses' variable
portions [AE p. 407] — a net tenant reimburses its share of the *actual*
(occupancy-scaled) expense. Stops, base years, fixed amounts, user
structures (pools, caps/floors, admin fees, expense adjustments), and
free-rent abatement of recoveries (``FreeRentProfile.abate_recoveries``)
are Phase 2 (spec §10).

Everything returns a monthly Period[M]-indexed Series (spec §2.3);
recoveries post to Expense Recovery Revenue. The engine never imports UI
code (Iron Rule 1).
"""
from __future__ import annotations

from typing import Iterable, Union

import pandas as pd

from engine.calc.leases import lease_term_periods
from engine.models import ExpenseItem, Lease, RecoverySystemMethod

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


def project_recoveries(lease: Lease, months: pd.PeriodIndex,
                       expenses: ExpenseSeries,
                       rentable_area: Union[pd.Series, float]) -> pd.Series:
    """Project one lease's contract-term expense recoveries onto the
    monthly timeline (spec §4.1 step 6). Dispatch: ``none`` posts nothing
    [AE p. 406]; ``net`` posts the pro-rata pool share [AE p. 405]; every
    other method arrives with full recovery structures (Phase 2 Step 5,
    spec §10, Iron Rule 2)."""
    start, end = lease_term_periods(lease)
    return _window_recoveries(
        lease.recoveries.method, lease.area, start, end,
        months, expenses, rentable_area,
        where=f"lease {lease.tenant_name!r}",
    )


def project_segment_recoveries(segment, months: pd.PeriodIndex,
                               expenses: ExpenseSeries,
                               rentable_area: Union[pd.Series, float],
                               ) -> pd.Series:
    """Recoveries for one resolved lease segment (contract or speculative;
    Phase 2 Step 2). The segment's own ``RecoveryAssignment`` governs —
    speculative segments recover per their MLP (spec §3.6 [AE pp. 239-240]).
    Recoveries post over occupied months only: downtime months post
    nothing (the space is vacant; golden #1's FY2029 Expense Recoveries
    confirm)."""
    return _window_recoveries(
        segment.recoveries.method, segment.area, segment.start, segment.end,
        months, expenses, rentable_area,
        where=f"lease {segment.lease.tenant_name!r} segment {segment.start}",
    )


def _window_recoveries(method: RecoverySystemMethod, area: float,
                       start: pd.Period, end: pd.Period,
                       months: pd.PeriodIndex, expenses: ExpenseSeries,
                       rentable_area: Union[pd.Series, float],
                       where: str) -> pd.Series:
    if method == RecoverySystemMethod.none:
        return pd.Series(0.0, index=months, name="expense_recovery")
    if method == RecoverySystemMethod.net:
        pool = recoverable_pool(expenses, months)
        series = pd.Series(0.0, index=months, name="expense_recovery")
        for period in months:
            if start <= period <= end:
                series[period] = float(pool[period]) * area / _area_at(
                    rentable_area, period
                )
        return series
    raise NotImplementedError(
        f"{where}: recovery method '{method.value}' arrives with full "
        "recovery structures (Phase 2 Step 5, spec §10); 'net' and 'none' "
        "only until then"
    )
