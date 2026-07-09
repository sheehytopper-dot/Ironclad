"""Property revenues: miscellaneous / parking / storage (spec §3.10; §4.1
step 9) [AE pp. 273-296].

Same amount / unit / timing / inflation / occupancy / limits machinery as
expenses (the timing helpers are shared from ``engine.calc.expenses``), plus
the parking ``spaces_times_rate`` unit. The default inflation index is the
general rate (other-revenue growth), not the expense rate.

Two kinds, mirroring the expense passes (spec §4.1 step 9):

- **Absolute-amount** items (the four $/period units, ``per_occupied_area``,
  ``per_available_area``, ``spaces_times_rate``) are EGR-independent and
  project once.
- **%-of-EGR / %-of-PGR** items re-enter EGR through PGR, so they resolve
  inside run.py's %-of-revenue fixed point — the same shape as the
  recoverable %-of-EGR management fee (DEVIATIONS.md §6, §13), reusing that
  loop rather than a separate second pass.

``pct_of_account`` is deferred (no fixture needs it; run.py refuses it and
this module raises as a backstop — DEVIATIONS.md §13). Everything returns a
monthly Period[M] Series posting to the Parking / Storage / Miscellaneous
Property Revenue ledger line. The engine never imports UI code (Iron Rule 1).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional, Union

import pandas as pd

from engine.calc.expenses import (
    _occupancy_at,
    _repeat_postings,
    _timing_window,
)
from engine.calc.inflation import index_schedule, inflation_factors
from engine.models import Inflation, PropertyRevenue, RevenueUnit, TimingMethod

#: Units that are a percentage of a computed revenue series (resolved in the
#: run.py fixed point). ``pct_of_account`` is deliberately excluded — deferred.
PCT_UNITS = frozenset({RevenueUnit.pct_of_egr, RevenueUnit.pct_of_pgr})

#: EGR-independent units, projected once outside the fixed point.
ABSOLUTE_UNITS = frozenset({
    RevenueUnit.dollars_per_year,
    RevenueUnit.dollars_per_month,
    RevenueUnit.dollars_per_area_per_year,
    RevenueUnit.dollars_per_area_per_month,
    RevenueUnit.per_occupied_area,
    RevenueUnit.per_available_area,
    RevenueUnit.spaces_times_rate,
})


def _factor_series(item: PropertyRevenue, months: pd.PeriodIndex,
                   analysis_begin: dt.date, inflation: Inflation) -> pd.Series:
    """Monthly inflation factors for the item's index: a named index, an
    explicit YearRate schedule, or the general rate by default (spec §3.3,
    §3.10 — property revenue defaults to the general / other-revenue index,
    not the expense index)."""
    if isinstance(item.inflation, list):
        rates = item.inflation
    else:
        rates = index_schedule(inflation, item.inflation, default="general")
    return inflation_factors(
        rates, months, analysis_begin,
        inflation.inflation_month, inflation.timing_basis,
    )


def _monthly_equivalent(item: PropertyRevenue, period: pd.Period, factor: float,
                        area: float,
                        occupancy: Union[pd.Series, float],
                        occupied_area: Optional[pd.Series],
                        available_area: Optional[pd.Series],
                        reference: Optional[pd.Series]) -> float:
    """The item's monthly-equivalent amount in ``period`` (mirrors the expense
    unit semantics; spec §3.10)."""
    unit = item.unit
    if unit in PCT_UNITS:
        if reference is None:
            raise ValueError(
                f"property revenue {item.name!r}: unit '{unit.value}' requires "
                "a reference series (EGR / PGR)"
            )
        return item.amount / 100.0 * float(reference[period])
    if unit == RevenueUnit.pct_of_account:
        raise NotImplementedError(
            f"property revenue {item.name!r}: unit 'pct_of_account' is not "
            "modeled (DEVIATIONS.md §13)"
        )
    if unit == RevenueUnit.per_occupied_area:
        if occupied_area is None:
            raise ValueError(
                f"property revenue {item.name!r}: 'per_occupied_area' requires "
                "an occupied-area series"
            )
        return item.amount * float(occupied_area[period]) / 12.0 * factor
    if unit == RevenueUnit.per_available_area:
        if available_area is None:
            raise ValueError(
                f"property revenue {item.name!r}: 'per_available_area' requires "
                "an available-area series"
            )
        return item.amount * float(available_area[period]) / 12.0 * factor

    if unit == RevenueUnit.spaces_times_rate:
        # number_of_spaces × annual rate per space (period convention:
        # DEVIATIONS.md §13)
        base = item.number_of_spaces * item.amount / 12.0
    elif unit == RevenueUnit.dollars_per_year:
        base = item.amount / 12.0
    elif unit == RevenueUnit.dollars_per_month:
        base = item.amount
    elif unit == RevenueUnit.dollars_per_area_per_year:
        base = item.amount * area / 12.0
    elif unit == RevenueUnit.dollars_per_area_per_month:
        base = item.amount * area
    else:  # pragma: no cover - exhaustive over RevenueUnit
        raise ValueError(f"unhandled property-revenue unit {unit!r}")

    fixed = item.pct_fixed / 100.0
    scale = fixed + (1.0 - fixed) * _occupancy_at(occupancy, period)
    return base * factor * scale


def project_property_revenue(item: PropertyRevenue, months: pd.PeriodIndex,
                             analysis_begin: dt.date, inflation: Inflation, *,
                             area: float = 0.0,
                             occupancy: Union[pd.Series, float] = 1.0,
                             occupied_area: Optional[pd.Series] = None,
                             available_area: Optional[pd.Series] = None,
                             reference: Optional[pd.Series] = None,
                             ) -> pd.Series:
    """Project one property-revenue line onto the monthly timeline (spec §4.1
    step 9). ``reference`` is the series a ``pct_of_egr`` / ``pct_of_pgr`` item
    applies its percentage to (EGR or PGR, supplied by run.py's fixed point).
    Continuous and date-range items post their monthly equivalent every active
    month; repeating items post per the manual's repeating-payment examples
    [AE pp. 361-362]; limits clamp per month [AE p. 279]."""
    factors = _factor_series(item, months, analysis_begin, inflation)
    series = pd.Series(0.0, index=months, name=item.name)
    start, end = _timing_window(item.timing, months)

    def equivalent(period: pd.Period) -> float:
        return _monthly_equivalent(
            item, period, float(factors[period]), area,
            occupancy, occupied_area, available_area, reference,
        )

    if item.timing.method == TimingMethod.repeating:
        active = []
        for period, interval in _repeat_postings(item.timing, (start, end),
                                                 months):
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
