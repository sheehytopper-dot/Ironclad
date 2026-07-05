"""Operating, non-operating, and capital expense projection (Phase 1;
spec §4.1 step 5) [AE pp. 313-345].

Repeating payments follow the manual's calculation examples
[AE pp. 361-362]: each posting equals the item's monthly-equivalent amount
in the posting month (inflated as of that month) multiplied by the number of
months in the repeat interval — an annual $12,000 repeating quarterly posts
$3,000 every third month; a monthly amount repeating quarterly posts the
trigger month's inflated amount × 3; a single payment posts the amount
annualized at the trigger.

Unit semantics (spec §3.10/§3.11):
- the four fixed dollar/area units convert to a monthly equivalent, inflate
  on the item's index (default: the expense index), and scale for occupancy
  via ``pct_fixed`` — effective = amount × (fixed% + variable% × occupancy)
- ``per_occupied_area`` / ``per_available_area`` are $/SF/yr on the
  respective monthly area series (already occupancy-driven, so ``pct_fixed``
  does not apply again)
- the ``pct_of_*`` units are a percentage of a reference series (EGR, PGR,
  or another account) computed by the ledger's ordered passes (spec §4.1
  step 9); the reference already carries inflation and occupancy, so
  neither is reapplied

Limits clamp the monthly amount per period [AE p. 279], applied to the
months the item is active. Everything returns a monthly Period[M]-indexed
Series (spec §2.3); the engine never imports UI code (Iron Rule 1).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional, Union

import pandas as pd

from engine.calc.inflation import index_schedule, inflation_factors
from engine.calc.timeline import snap_to_month_start
from engine.models import (
    ExpenseItem,
    ExpenseUnit,
    Inflation,
    Timing,
    TimingMethod,
)

#: Units that are a percentage of another computed series (spec §3.10).
PCT_UNITS = frozenset(
    {ExpenseUnit.pct_of_egr, ExpenseUnit.pct_of_pgr, ExpenseUnit.pct_of_account}
)


def _factor_series(item: ExpenseItem, months: pd.PeriodIndex,
                   analysis_begin: dt.date, inflation: Inflation) -> pd.Series:
    """Monthly inflation factors for the item's index: a named index, an
    explicit YearRate schedule, or the expense index by default (spec §3.3,
    §3.11)."""
    if isinstance(item.inflation, list):
        rates = item.inflation
    else:
        rates = index_schedule(inflation, item.inflation, default="expense")
    return inflation_factors(
        rates, months, analysis_begin,
        inflation.inflation_month, inflation.timing_basis,
    )


def _occupancy_at(occupancy: Union[pd.Series, float], period: pd.Period) -> float:
    if isinstance(occupancy, pd.Series):
        return float(occupancy[period])
    return float(occupancy)


def _monthly_equivalent(item: ExpenseItem, period: pd.Period, factor: float,
                        area: float,
                        occupancy: Union[pd.Series, float],
                        occupied_area: Optional[pd.Series],
                        available_area: Optional[pd.Series],
                        reference: Optional[pd.Series]) -> float:
    """The item's monthly-equivalent amount in ``period`` — the accrual a
    continuous item posts monthly, and the per-month rate a repeating item
    multiplies by its interval [AE pp. 361-362]."""
    unit = item.unit
    if unit in PCT_UNITS:
        if reference is None:
            raise ValueError(
                f"expense {item.name!r}: unit '{unit.value}' requires a "
                "reference series (EGR / PGR / referenced account)"
            )
        return item.amount / 100.0 * float(reference[period])
    if unit == ExpenseUnit.per_occupied_area:
        if occupied_area is None:
            raise ValueError(
                f"expense {item.name!r}: 'per_occupied_area' requires an "
                "occupied-area series"
            )
        return item.amount * float(occupied_area[period]) / 12.0 * factor
    if unit == ExpenseUnit.per_available_area:
        if available_area is None:
            raise ValueError(
                f"expense {item.name!r}: 'per_available_area' requires an "
                "available-area series"
            )
        return item.amount * float(available_area[period]) / 12.0 * factor

    if unit == ExpenseUnit.dollars_per_year:
        base = item.amount / 12.0
    elif unit == ExpenseUnit.dollars_per_month:
        base = item.amount
    elif unit == ExpenseUnit.dollars_per_area_per_year:
        base = item.amount * area / 12.0
    elif unit == ExpenseUnit.dollars_per_area_per_month:
        base = item.amount * area
    else:  # pragma: no cover - exhaustive over ExpenseUnit
        raise ValueError(f"unhandled expense unit {unit!r}")

    fixed = item.pct_fixed / 100.0
    scale = fixed + (1.0 - fixed) * _occupancy_at(occupancy, period)
    return base * factor * scale


def _timing_window(timing: Timing, months: pd.PeriodIndex) -> tuple[pd.Period, pd.Period]:
    start = (
        pd.Period(snap_to_month_start(timing.start), freq="M")
        if timing.start is not None else months[0]
    )
    end = (
        pd.Period(snap_to_month_start(timing.end), freq="M")
        if timing.end is not None else months[-1]
    )
    return start, end


def _repeat_postings(timing: Timing, window: tuple[pd.Period, pd.Period],
                     months: pd.PeriodIndex) -> list[tuple[pd.Period, int]]:
    """Posting months and the number of accrual months each covers.

    ``repeat_every_months``: postings every N months from the trigger, each
    covering N months ("multiplied by three applied every third month from
    trigger" [AE p. 362]). ``repeat_months``: postings in the listed calendar
    months, each covering the cyclic gap since the previous listed month
    (e.g. [6, 12] → two postings of six months each year).
    """
    start, end = window
    postings: list[tuple[pd.Period, int]] = []
    if timing.repeat_every_months:
        interval = timing.repeat_every_months
        period = start
        while period <= end:
            if period in months:
                postings.append((period, interval))
            period += interval
    else:
        listed = sorted(set(timing.repeat_months))
        gaps = {}
        for i, month in enumerate(listed):
            prev = listed[i - 1]  # wraps: previous listed month in the cycle
            gaps[month] = (month - prev) % 12 or 12
        for period in months:
            if start <= period <= end and period.month in gaps:
                postings.append((period, gaps[period.month]))
    return postings


def project_expense(item: ExpenseItem, months: pd.PeriodIndex,
                    analysis_begin: dt.date, inflation: Inflation, *,
                    area: float = 0.0,
                    occupancy: Union[pd.Series, float] = 1.0,
                    occupied_area: Optional[pd.Series] = None,
                    available_area: Optional[pd.Series] = None,
                    reference: Optional[pd.Series] = None) -> pd.Series:
    """Project one expense item onto the monthly timeline (spec §4.1 step 5).

    ``area`` is the SF denominator for the per-area units; ``occupancy`` the
    monthly occupied fraction for ``pct_fixed`` scaling (spec §3.11);
    ``reference`` the series a ``pct_of_*`` item applies its percentage to.
    Continuous and date-range items post their monthly equivalent every
    active month; repeating items post per the manual's repeating-payment
    examples [AE pp. 361-362]; limits clamp per month [AE p. 279].
    """
    factors = _factor_series(item, months, analysis_begin, inflation)
    series = pd.Series(0.0, index=months, name=item.name)
    window = _timing_window(item.timing, months)
    start, end = window

    def equivalent(period: pd.Period) -> float:
        return _monthly_equivalent(
            item, period, float(factors[period]), area,
            occupancy, occupied_area, available_area, reference,
        )

    if item.timing.method == TimingMethod.repeating:
        active = []
        for period, interval in _repeat_postings(item.timing, window, months):
            series[period] = equivalent(period) * interval
            active.append(period)
    else:
        active = [p for p in months if start <= p <= end]
        for period in active:
            series[period] = equivalent(period)

    if item.limits is not None:
        for period in active:
            value = series[period]
            if item.limits.min is not None:
                value = max(value, item.limits.min)
            if item.limits.max is not None:
                value = min(value, item.limits.max)
            series[period] = value
    return series
