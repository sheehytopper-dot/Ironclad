"""Occupancy report (Phase 4 Step 4; spec §7 report 15) [AE pp. 585-604].

Occupied area, rentable area, available area, and occupancy % per period,
straight from the occupancy series the run already computes
(``result.occupied_area`` / ``result.rentable_area`` / ``result.occupancy``,
spec §3.2). A count/area/percent report — **not** a monetary one — so the
$ unit toggle does not apply (``monetary=False``); it takes the period
toggle (monthly / quarterly / annual / fiscal).

Areas are **stock** quantities (SF in place at a point in time), so a
period figure is the **mean** area over the period's months (not a sum,
which would be meaningless), and occupancy % is mean-occupied ÷
mean-rentable — for the monthly view this is exactly the run's own series
(:func:`reconcile_to_result`). The §9.3 invariant occupied ≤ rentable is
re-checked here (:func:`assert_occupied_within_rentable`). The engine
never imports UI code (Iron Rule 1).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from engine.reports.base import Period, Report, ReportMeta, period_mean_area

COLUMNS = ["occupied_area", "rentable_area", "available_area", "occupancy"]


def _analysis_begin(result, analysis_begin: Optional[dt.date]) -> dt.date:
    if analysis_begin is not None:
        return analysis_begin
    return result.months[0].to_timestamp().date()


def occupancy(result, *, period: Period = Period.monthly,
              fiscal_year_end_month: int = 12,
              analysis_begin: Optional[dt.date] = None) -> Report:
    """Build the Occupancy report (#15) from a ``RunResult``: per period,
    the mean occupied / rentable / available SF and the occupancy fraction
    (occupied ÷ rentable). Monthly returns the run's series unchanged."""
    begin = _analysis_begin(result, analysis_begin)
    occupied = period_mean_area(result.occupied_area, period,
                                analysis_begin=begin,
                                fiscal_year_end_month=fiscal_year_end_month)
    rentable = period_mean_area(result.rentable_area, period,
                                analysis_begin=begin,
                                fiscal_year_end_month=fiscal_year_end_month)
    available = (rentable - occupied).rename("available_area")
    # occupancy = occupied / rentable; NaN where rentable is 0 (undefined,
    # not a silent zero — Step 1's convention).
    occ = (occupied / rentable.replace(0.0, float("nan"))).rename("occupancy")
    frame = pd.DataFrame({
        "occupied_area": occupied, "rentable_area": rentable,
        "available_area": available, "occupancy": occ,
    }, columns=COLUMNS)
    frame.index.name = ("month" if period == Period.monthly else period.value)
    meta = ReportMeta(name="Occupancy", number=15, period=period,
                      monetary=False, citation="[AE pp. 585-604]",
                      extra={"fiscal_year_end_month": fiscal_year_end_month})
    return Report(frame=frame, meta=meta)


def reconcile_to_result(report: Report, result) -> pd.DataFrame:
    """Monthly report minus the run's own occupancy series — exact zeros
    when the report faithfully echoes the source. Defined on the **monthly**
    view (period aggregations are means, which don't tie cell-for-cell to
    the raw series); raises for a non-monthly report."""
    if report.meta.period != Period.monthly:
        raise ValueError(
            "reconcile_to_result compares the monthly view; rebuild the "
            f"report with period=Period.monthly (got {report.meta.period})")
    frame = report.frame
    return pd.DataFrame({
        "occupied_area": frame["occupied_area"] - result.occupied_area,
        "rentable_area": frame["rentable_area"] - result.rentable_area,
        "occupancy": frame["occupancy"] - result.occupancy,
    })


def assert_occupied_within_rentable(report: Report, atol: float = 1e-6) -> None:
    """Assert occupied ≤ rentable in every row (the §9.3 invariant, surfaced
    on the report); raise naming the first period that violates it."""
    breach = report.frame[report.frame["available_area"] < -atol]
    if not breach.empty:
        period = breach.index[0]
        raise ValueError(
            f"occupancy invariant violated: occupied area exceeds rentable "
            f"in {period} (spec §9.3)")
