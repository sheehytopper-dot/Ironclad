"""Percentage rent — retail sales overage (Phase 2 Step 8, spec §3.13)
[AE pp. 249-251, 376-377, 590].

Percentage rent is the share of retail sales above a breakpoint that the
tenant pays the landlord: **% rent due = Σ per layer max(0, sales volume −
breakpoint) × sales %** [AE p. 590; spec §3.13], up to six layers of
tiered overage [AE p. 250]. Sales volume is annual ($/yr, or $/SF/yr ×
tenant area [AE pp. 249-250]) growing on its inflation index; breakpoints
per [AE pp. 251, 377]:

- **natural** — sales must first cover the rent: breakpoint = (base rent
  + step rent + CPI) / layer % ("the natural breakpoint is calculated on
  base rent + step rent + CPI" [AE pp. 250-251, 377]; "base rent divided
  by the overage percentage" [AE p. 590]). Free rent does not reduce it —
  the manual's definition names potential rent components only.
- **fixed_amount** — the annual dollar amount entered per layer
  ("calculates on sales volume over annual amount entered" [AE p. 250]).
- **zero** — the percentage applies to total sales [AE pp. 251, 377].

Everything posts monthly (spec §2.3): each month prices the annualized
run rate — that month's sales volume and rent × 12 — through the annual
formula and posts 1/12 of the result, the same straight monthly accrual
convention as recoveries (spec §3.14 v1 policy; DEVIATIONS.md §11).
Percentage rent posts over a segment's **occupied months only** — none
during rollover downtime, matching the Step 2 recovery convention
(DEVIATIONS.md §11). Speculative segments carry their MLP's spec
[AE p. 376 "Market" sales basis; spec §3.6]; their natural breakpoint
uses the blended market rent (no CPI — DEVIATIONS.md §7).

The [AE p. 413] recovery offset (Offset % per recovery method deducting
recoveries from percentage rent) lives on the recovery structure, which
the §3.14 schema does not carry — deferred, not silently dropped
(DEVIATIONS.md §11).

**EXTERNALLY UNVALIDATED PENDING GOLDEN #3** (CLAUDE.md standing gap):
no OM with a published Argus percentage-rent line has been staged, so
this module has only the manual's definitional examples as references —
any retail underwriting before the golden #3 back-test treats the
Percentage Rent line as unverified.

Everything returns monthly Period[M] Series posting to the Percentage
Rent ledger line. The engine never imports UI code (Iron Rule 1).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from engine.calc.inflation import index_schedule, inflation_factors
from engine.models import (
    Inflation,
    PercentRentBreakpoint,
    PercentRentSpec,
    SalesVolumeUnit,
)


def annual_percentage_rent(spec: PercentRentSpec, annual_sales: float,
                           annual_rent: float) -> float:
    """The [AE p. 590] annual formula: Σ per layer max(0, sales −
    breakpoint) × pct. ``annual_rent`` (base + steps + CPI) feeds the
    natural breakpoint = rent / layer pct [AE pp. 251, 377, 590]."""
    total = 0.0
    for layer in spec.breakpoint_layers:
        pct = layer.pct / 100.0
        if spec.breakpoint == PercentRentBreakpoint.natural:
            breakpoint_amount = annual_rent / pct
        elif spec.breakpoint == PercentRentBreakpoint.fixed_amount:
            breakpoint_amount = float(layer.breakpoint_amount)
        else:  # zero: percentage of total sales [AE pp. 251, 377]
            breakpoint_amount = 0.0
        total += max(0.0, annual_sales - breakpoint_amount) * pct
    return total


def sales_volume_series(spec: PercentRentSpec, area: float,
                        months: pd.PeriodIndex, analysis_begin: dt.date,
                        inflation: Inflation) -> pd.Series:
    """Annualized sales volume per month: the entered amount ($/yr, or
    $/SF/yr × tenant area [AE pp. 249-250]) on its growth index (a named
    index, an explicit schedule, or the general rate — spec §3.3/§3.13)."""
    growth = spec.sales_volume.growth
    if isinstance(growth, list):
        rates = growth
    else:
        rates = index_schedule(inflation, growth, default="general")
    factors = inflation_factors(
        rates, months, analysis_begin,
        inflation.inflation_month, inflation.timing_basis,
    )
    amount = spec.sales_volume.amount
    if spec.sales_volume.unit == SalesVolumeUnit.dollars_per_area_per_year:
        amount *= area
    return (factors * amount).rename("annual_sales")


def project_segment_percentage_rent(
        segment, months: pd.PeriodIndex, *,
        base_rent: pd.Series,
        cpi_adjustment: Optional[pd.Series],
        analysis_begin: dt.date,
        inflation: Inflation) -> pd.Series:
    """One segment's monthly Percentage Rent over its occupied months.

    ``base_rent`` / ``cpi_adjustment`` are the tenant's chain series from
    pass 4 — within a segment's occupied months they carry exactly that
    segment's potential rent including steps (downtime and pre-absorption
    postings fall outside those months), so the natural breakpoint's
    base + step + CPI [AE pp. 250-251] is read straight off them.
    """
    series = pd.Series(0.0, index=months, name="percentage_rent")
    spec = segment.percentage_rent
    if spec is None:
        return series
    sales = sales_volume_series(spec, segment.area, months,
                                analysis_begin, inflation)
    for period in months:
        if not (segment.start <= period <= segment.end):
            continue
        rent_month = float(base_rent[period])
        if cpi_adjustment is not None:
            rent_month += float(cpi_adjustment[period])
        series[period] = annual_percentage_rent(
            spec, float(sales[period]), rent_month * 12.0
        ) / 12.0
    return series
