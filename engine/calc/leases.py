"""Contract-term lease rent: base rent unit conversion, fixed and percent
steps, CPI adjustments, and free rent (Phase 1; spec §4.1 step 4).

Base rent calculation examples are normative [AE pp. 391-394]; free rent
profiles [AE pp. 253-254]; CPI increases [AE pp. 255-257]. Rollover chains
and speculative segments are Phase 2 (spec §4.2); this module projects the
contract term only.

Conventions (spec §2.3): every output is a monthly pandas Series indexed by
the canonical Period[M] timeline, zero outside the lease term and analysis
window. Base rent + fixed/percent steps post to Base Rental Revenue; CPI
adjustments post separately (CPI & Other Adjustment Revenue); free rent
posts as negative amounts (Free Rent).

Free rent abates base rent and fixed steps at 100% and CPI at 0% — the
manual's element defaults [AE p. 254]. (The §3.8 schema cannot express
partial percentages per element; see DEVIATIONS.md.)

Out of scope here, with no §3 schema inputs: rent-review ratchets, %-of-sales
reviews, and average-prior-rent reviews [AE pp. 392-393] — v1 does not model
them (spec §3.12).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from engine.calc.inflation import index_schedule, rate_for_year
from engine.calc.timeline import snap_to_month_start
from engine.models import (
    CPIMethod,
    FreeRentProfile,
    FreeRentTiming,
    Inflation,
    Lease,
    MoneyRate,
    MoneyUnit,
    RentStep,
    TimingBasis,
)


def monthly_base_rent(rate: MoneyRate, area: float,
                      market_rent_annual: Optional[float] = None) -> float:
    """Convert a base-rent ``MoneyRate`` to dollars per month.

    Unit conversions per the normative calculation examples [AE p. 391]:
    $/SF/yr × area / 12; $/SF/mo × area; $/yr / 12; $/mo as entered;
    % of market × (annual market rent) / 12.
    """
    u = rate.unit
    if u == MoneyUnit.dollars_per_area_per_year:
        return rate.amount * area / 12.0
    if u == MoneyUnit.dollars_per_area_per_month:
        return rate.amount * area
    if u == MoneyUnit.dollars_per_year:
        return rate.amount / 12.0
    if u == MoneyUnit.dollars_per_month:
        return rate.amount
    if u == MoneyUnit.pct_of_market:
        if market_rent_annual is None:
            raise ValueError(
                "pct_of_market base rent requires market_rent_annual "
                "(the space's market rent in $/year)"
            )
        return market_rent_annual * rate.amount / 100.0 / 12.0
    raise ValueError(f"{u.value!r} is not a base rent unit")


def lease_term_periods(lease: Lease) -> tuple[pd.Period, pd.Period]:
    """First and last occupied month of the contract term. All timing snaps
    to months (spec §3.1): the start month is the month containing
    ``start_date``; the end month is the month containing ``end_date`` (or
    start + term_months − 1)."""
    start = pd.Period(snap_to_month_start(lease.start_date), freq="M")
    if lease.end_date is not None:
        end = pd.Period(snap_to_month_start(lease.end_date), freq="M")
    else:
        end = start + lease.term_months - 1
    return start, end


def _step_period(step: RentStep, lease_start: pd.Period) -> pd.Period:
    if step.date is not None:
        return pd.Period(snap_to_month_start(step.date), freq="M")
    return lease_start + step.month_offset


def rent_level(lease: Lease, period: pd.Period,
               market_rent_annual: Optional[float] = None) -> float:
    """Monthly base rent (including fixed and percent steps) in force during
    ``period``.

    Amount steps re-base the rent per their own unit [rent review examples,
    AE p. 392]; percent steps compound multiplicatively on the prior rent
    [% of market with step amounts, AE p. 391: 100,000 ×1.05 → 105,000,
    ×1.05 → 110,250].
    """
    start, _ = lease_term_periods(lease)
    level = monthly_base_rent(lease.base_rent, lease.area, market_rent_annual)
    for step in sorted(lease.rent_steps, key=lambda s: _step_period(s, start)):
        if _step_period(step, start) > period:
            break
        if step.amount is not None:
            level = monthly_base_rent(
                MoneyRate(amount=step.amount, unit=step.unit),
                lease.area, market_rent_annual,
            )
        else:
            level *= 1.0 + step.pct_increase / 100.0
    return level


def contract_base_rent(lease: Lease, months: pd.PeriodIndex,
                       market_rent_annual: Optional[float] = None) -> pd.Series:
    """Monthly contract base rent (incl. steps) over the analysis timeline;
    zero outside the lease term [AE pp. 391-392]."""
    start, end = lease_term_periods(lease)
    series = pd.Series(0.0, index=months, name="base_rent")
    for period in months:
        if start <= period <= end:
            series[period] = rent_level(lease, period, market_rent_annual)
    return series


# --------------------------------------------------------------------- #
# CPI increases [AE pp. 255-257; indexed review example AE p. 392]       #
# --------------------------------------------------------------------- #

def _cpi_schedule(inflation: Inflation, index_ref: Optional[str]):
    """Resolve a CPI spec's index ref to an annual rate schedule; a CPI spec
    with no index uses the cpi rate (spec §3.3/§3.7)."""
    return index_schedule(inflation, index_ref, default="cpi")


def _schedule_year(period: pd.Period, analysis_begin: dt.date,
                   timing_basis: TimingBasis) -> int:
    """Which schedule year applies to an increase falling in ``period``:
    the calendar year under calendar basis, else the 1-based analysis year
    (clamped to 1 for events preceding the analysis window — CPI on an
    in-place lease accrues from lease start)."""
    if timing_basis == TimingBasis.calendar_year:
        return period.year
    offset = (period.year - analysis_begin.year) * 12 + (period.month - analysis_begin.month)
    return max(1, offset // 12 + 1)


def cpi_adjustments(lease: Lease, months: pd.PeriodIndex,
                    analysis_begin: dt.date, inflation: Inflation,
                    market_rent_annual: Optional[float] = None) -> pd.Series:
    """Monthly CPI adjustment series for a contract lease [AE pp. 255-257].

    At each increase event (first on the lease anniversary or after
    ``first_increase_month`` months, then every ``frequency_months``), the
    increase is (rent + prior CPI) × effective rate — the manual defines
    minimum/maximum increases "over the prior rent (rent + prior CPI)"
    [AE p. 257], and the indexed-review example compounds a lease year's rent
    by (1 + CPI) at the start of the new lease year [AE p. 392]. Method
    scaling: ``pct_of_cpi`` takes pct% of the calculated CPI ("if calculated
    CPI is $1,000 … 57% … $570" [AE p. 257]); ``cpi_plus_pct`` adds pct
    points; ``cap_pct``/``floor_pct`` clamp the effective rate (the
    ``min_max_banded`` method is full CPI with both bounds set).
    Adjustments post to CPI & Other Adjustment Revenue, never into base rent
    (spec §2.3).
    """
    series = pd.Series(0.0, index=months, name="cpi_adjustment")
    spec = lease.cpi
    if spec is None:
        return series
    rates = _cpi_schedule(inflation, spec.index)
    start, end = lease_term_periods(lease)

    first_offset = 12 if spec.first_increase_month == "anniversary" else int(spec.first_increase_month)
    events = []
    event = start + first_offset
    while event <= end:
        events.append(event)
        event += spec.frequency_months

    level = 0.0
    levels: list[tuple[pd.Period, float]] = []
    for event in events:
        rate = rate_for_year(rates, _schedule_year(event, analysis_begin, inflation.timing_basis))
        if spec.method == CPIMethod.pct_of_cpi:
            rate *= (spec.pct or 0.0) / 100.0
        elif spec.method == CPIMethod.cpi_plus_pct:
            rate += spec.pct or 0.0
        if spec.cap_pct is not None:
            rate = min(rate, spec.cap_pct)
        if spec.floor_pct is not None:
            rate = max(rate, spec.floor_pct)
        base = rent_level(lease, event, market_rent_annual) + level
        level += base * rate / 100.0
        levels.append((event, level))

    for period in months:
        if start <= period <= end:
            applicable = [lvl for ev, lvl in levels if ev <= period]
            if applicable:
                series[period] = applicable[-1]
    return series


# --------------------------------------------------------------------- #
# Free rent [AE pp. 253-254]                                             #
# --------------------------------------------------------------------- #

def free_rent(lease: Lease, months: pd.PeriodIndex,
              market_rent_annual: Optional[float] = None,
              profile: Optional[FreeRentProfile] = None) -> pd.Series:
    """Monthly free-rent abatement (negative) for a contract lease.

    Elements to include follow the manual's defaults [AE p. 254]: base rent
    and fixed steps abate at 100%, CPI at 0% — so the abated amount is the
    stepped base rent level, never the CPI adjustment. ``front`` timing
    abates the first N lease months (a fractional N abates a fraction of the
    final month); ``custom`` timing abates the listed 1-based lease months in
    full (spec §3.12).
    """
    series = pd.Series(0.0, index=months, name="free_rent")
    fr = lease.free_rent
    if fr is None or (profile is not None and not profile.abate_base_rent):
        return series
    start, end = lease_term_periods(lease)
    custom = set(fr.custom_months or [])
    for period in months:
        if not start <= period <= end:
            continue
        lease_month = (period.year - start.year) * 12 + (period.month - start.month)
        if fr.timing == FreeRentTiming.front:
            fraction = min(1.0, max(0.0, fr.months - lease_month))
        else:
            fraction = 1.0 if (lease_month + 1) in custom else 0.0
        if fraction:
            series[period] = -fraction * rent_level(lease, period, market_rent_annual)
    return series


# --------------------------------------------------------------------- #
# Orchestration                                                          #
# --------------------------------------------------------------------- #

@dataclass
class LeaseRentCashflows:
    """Contract-term rent series for one lease (spec §2.3 accounts)."""

    base_rent: pd.Series       # Base Rental Revenue (incl. fixed/% steps)
    cpi_adjustment: pd.Series  # CPI & Other Adjustment Revenue
    free_rent: pd.Series       # Free Rent (negative)


def project_contract_rent(lease: Lease, months: pd.PeriodIndex,
                          analysis_begin: dt.date,
                          inflation: Optional[Inflation] = None,
                          market_rent_annual: Optional[float] = None,
                          free_rent_profile: Optional[FreeRentProfile] = None,
                          ) -> LeaseRentCashflows:
    """Project one lease's contract-term rent onto the monthly timeline
    (spec §4.1 step 4, contract portion)."""
    if lease.cpi is not None and inflation is None:
        raise ValueError("lease has a CPI spec; inflation assumptions are required")
    base = contract_base_rent(lease, months, market_rent_annual)
    cpi = (
        cpi_adjustments(lease, months, analysis_begin, inflation, market_rent_annual)
        if lease.cpi is not None
        else pd.Series(0.0, index=months, name="cpi_adjustment")
    )
    free = free_rent(lease, months, market_rent_annual, free_rent_profile)
    return LeaseRentCashflows(base_rent=base, cpi_adjustment=cpi, free_rent=free)
