"""Monthly inflation factor tables per index (spec §3.3, §4.1 step 2)
[AE pp. 219-223].

Normative logic (spec §3.3): the inflation factor for month m is
Π(1 + rate_y) over completed inflation anniversaries before or at m.
Anniversaries fall on ``inflation_month`` (default: the analysis begin
month) — **mid-year analysis starts must respect ``inflation_month``**:
rates step on that month, not necessarily January and not necessarily the
analysis anniversary.

Rate lookup per anniversary:

- ``analysis_year`` basis: the i-th anniversary after analysis begin applies
  the rate for analysis year i+1 (year-1 amounts are stated in year-1
  dollars, so year 1's factor is 1.0).
- ``calendar_year`` basis: an anniversary falling in calendar year Y applies
  the rate entered for year Y.

Schedules carry the last entered rate forward; years before the first entry
contribute 0%.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from engine.models import Inflation, TimingBasis, YearRate

#: Built-in index names resolvable by :func:`factor_table` (spec §3.3).
BUILTIN_INDEX_NAMES = ("general", "market_rent", "expense", "cpi")


def rate_for_year(rates: list[YearRate], year: int) -> float:
    """Rate (percent) applicable to ``year``: the entry with the largest
    ``year`` <= the requested year (carry-forward), else 0.0."""
    applicable = [r.rate for r in sorted(rates, key=lambda r: r.year) if r.year <= year]
    return applicable[-1] if applicable else 0.0


def inflation_factors(
    rates: list[YearRate],
    months: pd.PeriodIndex,
    analysis_begin: dt.date,
    inflation_month: Optional[int] = None,
    timing_basis: TimingBasis = TimingBasis.analysis_year,
) -> pd.Series:
    """Monthly multiplicative factor series for one rate schedule.

    Factors are 1.0 until the first anniversary strictly after the analysis
    begin month, then compound by the anniversary's applicable rate at each
    subsequent occurrence of ``inflation_month`` [AE pp. 219-223].
    """
    step_month = inflation_month or analysis_begin.month
    if not 1 <= step_month <= 12:
        raise ValueError("inflation_month must be 1-12")

    begin = pd.Period(analysis_begin.replace(day=1), freq="M")
    factors = []
    factor = 1.0
    anniversaries = 0
    for period in months:
        if period.month == step_month and period > begin:
            anniversaries += 1
            if timing_basis == TimingBasis.calendar_year:
                lookup_year = period.year
            else:  # analysis_year: i-th anniversary starts analysis year i+1
                lookup_year = anniversaries + 1
            factor *= 1.0 + rate_for_year(rates, lookup_year) / 100.0
        factors.append(factor)
    return pd.Series(factors, index=months, name="factor")


def factor_table(
    inflation: Inflation,
    months: pd.PeriodIndex,
    analysis_begin: dt.date,
) -> pd.DataFrame:
    """Precomputed monthly factor series for every index (spec §4.1 step 2):
    columns ``general``, ``market_rent``, ``expense``, ``cpi`` plus one per
    custom index. Named indices default to ``general`` when not given
    (spec §3.3)."""
    def series(rates: Optional[list[YearRate]]) -> pd.Series:
        return inflation_factors(
            rates if rates is not None else inflation.general_rate,
            months,
            analysis_begin,
            inflation.inflation_month,
            inflation.timing_basis,
        )

    table = pd.DataFrame(
        {
            "general": series(inflation.general_rate),
            "market_rent": series(inflation.market_rent_rate),
            "expense": series(inflation.expense_rate),
            "cpi": series(inflation.cpi_rate),
        }
    )
    for index in inflation.custom_indices:
        table[index.name] = series(index.rates)
    return table
