"""Month index, date math, fiscal handling (spec §4.1 step 1) [AE pp. 182-187].

The canonical timeline is a pandas ``PeriodIndex`` (freq ``M``) running from
the Analysis Begin Date through analysis end **+ 12 months** — the extra year
is required for the resale NOI look-forward (spec §2.3). All dates snap to
the first of the month.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd


def snap_to_month_start(d: dt.date) -> dt.date:
    """All timing snaps to months (spec §3.1): return the first of d's month."""
    return d.replace(day=1)


def build_month_index(analysis_begin: dt.date, analysis_term_years: int) -> pd.PeriodIndex:
    """The canonical monthly timeline: analysis begin → analysis end + 12
    months (resale look-forward, spec §2.3/§4.1 step 1)."""
    if analysis_term_years < 1:
        raise ValueError("analysis_term_years must be >= 1")
    start = pd.Period(snap_to_month_start(analysis_begin), freq="M")
    return pd.period_range(start, periods=(analysis_term_years + 1) * 12, freq="M")


def month_offset(analysis_begin: dt.date, d: dt.date) -> int:
    """0-based month offset of date ``d`` from the analysis begin month."""
    begin = snap_to_month_start(analysis_begin)
    return (d.year - begin.year) * 12 + (d.month - begin.month)


def analysis_year_of(analysis_begin: dt.date, period: pd.Period) -> int:
    """1-based analysis year containing ``period`` (12-month blocks from the
    analysis begin month, regardless of calendar year)."""
    offset = (period.year - analysis_begin.year) * 12 + (period.month - analysis_begin.month)
    if offset < 0:
        raise ValueError(f"{period} precedes analysis begin {analysis_begin}")
    return offset // 12 + 1


def fiscal_year_of(period: pd.Period, fiscal_year_end_month: int = 12) -> int:
    """Fiscal year label for a month, named for the calendar year in which the
    fiscal year *ends* (spec §3.1 ``fiscal_year_end_month``). With the default
    December year-end, this is simply the calendar year."""
    if not 1 <= fiscal_year_end_month <= 12:
        raise ValueError("fiscal_year_end_month must be 1-12")
    return period.year + (1 if period.month > fiscal_year_end_month else 0)
