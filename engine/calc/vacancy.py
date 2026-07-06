"""General vacancy and credit loss (Phase 2 Step 4; spec §3.4-§3.5,
§4.1 step 10) [AE pp. 224-232].

Method bases [AE pp. 224, 229]:

- ``percent_of_scheduled_base_plus`` — "% of Total Rental Revenue:
  Scheduled Base Rent + CPI Increases"
- ``percent_of_total_tenant_revenue`` — rental revenue plus percentage
  rent and expense recoveries
- ``percent_of_pgr`` — total tenant revenue plus property-level other
  income

``include_in_pgr_accounts`` (spec §3.4) overrides the method's base with
an explicit list of revenue lines. Rates vary by year (``YearRate``; the
inflation timing basis governs whether years are calendar or analysis
years, spec §3.3).

**The A&T interaction (spec §3.4, critical):** with
``reduce_by_absorption_turnover`` on (the ARGUS default), the percentage
applies to revenue at 100% occupancy — the base adds back the A&T vacancy
already in the ledger ("calculations based on potential revenue with 100%
Occupancy" [AE p. 226]; "Gross-Up Revenue by Absorption & Turnover
Vacancy" [AE p. 225]) — and the resulting allowance is then reduced by
that A&T: monthly General Vacancy = max(0, target − |A&T|), showing zero
when downtime already exceeds the allowance [AE p. 226]. Total vacancy
therefore equals the stated rate of full-occupancy revenue instead of
stacking downtime on top (Gate 2 criterion 5). With the toggle off, the
ledger shows separate, un-netted Vacancy Allowance and A&T lines
[AE p. 226] computed on as-scheduled revenue.

Credit loss applies **after** general vacancy on the reduced base, with
no A&T interaction of its own (spec §3.5 [AE p. 229]).

Tenant overrides are exclusion-only in the §3.4 schema (the credit-tenant
case: an excluded tenant's revenue — and its A&T — leaves the base and
the offset). The manual's adjust/increment/replace override methods,
annual-amount method, and after-expiration reversion are not modeled —
DEVIATIONS.md §9.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Mapping, Optional

import pandas as pd

from engine.calc.inflation import rate_for_year
from engine.calc.ledger import (
    CPI_ADJUSTMENT_REVENUE,
    EXPENSE_RECOVERY_REVENUE,
    PERCENTAGE_RENT,
    SCHEDULED_BASE_RENTAL_REVENUE,
)
from engine.calc.timeline import analysis_year_of
from engine.models import (
    CreditLoss,
    GeneralVacancy,
    TimingBasis,
    VacancyMethod,
)


@dataclass
class TenantRevenue:
    """One tenant's monthly revenue components at ledger conventions
    (scheduled net of A&T and free rent; ``absorption_vacancy`` negative)."""

    scheduled: pd.Series
    cpi: pd.Series
    recoveries: pd.Series
    absorption_vacancy: pd.Series
    percentage_rent: Optional[pd.Series] = None  # Phase 2 Step 8


def _zeros(months: pd.PeriodIndex) -> pd.Series:
    return pd.Series(0.0, index=months)


def _rate_series(rates, months: pd.PeriodIndex, analysis_begin: dt.date,
                 timing_basis: TimingBasis) -> pd.Series:
    """Year-varying percentage as a monthly series (spec §3.4 rate
    schedules; calendar vs analysis years per the timing basis)."""
    values = []
    for period in months:
        year = (period.year if timing_basis == TimingBasis.calendar_year
                else analysis_year_of(analysis_begin, period))
        values.append(rate_for_year(rates, year) / 100.0)
    return pd.Series(values, index=months)


def _tenant_base(revenue: TenantRevenue, method: VacancyMethod,
                 include_accounts, months: pd.PeriodIndex,
                 gross_up: bool) -> pd.Series:
    """One tenant's contribution to the percentage base. ``gross_up`` adds
    back the tenant's A&T vacancy — revenue at 100% occupancy
    [AE pp. 225-226]."""
    scheduled = revenue.scheduled.copy()
    if gross_up:
        scheduled = scheduled - revenue.absorption_vacancy  # A&T is negative
    pct_rent = (revenue.percentage_rent
                if revenue.percentage_rent is not None else _zeros(months))
    lines = {
        SCHEDULED_BASE_RENTAL_REVENUE: scheduled,
        CPI_ADJUSTMENT_REVENUE: revenue.cpi,
        PERCENTAGE_RENT: pct_rent,
        EXPENSE_RECOVERY_REVENUE: revenue.recoveries,
    }
    if include_accounts:
        base = _zeros(months)
        for name in include_accounts:
            if name not in lines:
                raise ValueError(
                    f"include_in_pgr_accounts: unknown or non-tenant revenue "
                    f"line {name!r} (supported: {sorted(lines)})"
                )
            base = base + lines[name]
        return base
    base = lines[SCHEDULED_BASE_RENTAL_REVENUE] + lines[CPI_ADJUSTMENT_REVENUE]
    if method == VacancyMethod.percent_of_scheduled_base_plus:
        return base
    # total tenant revenue adds percentage rent and recoveries; PGR adds
    # property-level income on top (run.py supplies it separately)
    return base + lines[PERCENTAGE_RENT] + lines[EXPENSE_RECOVERY_REVENUE]


def _excluded(spec) -> set:
    return {o.tenant_ref for o in spec.tenant_overrides if o.exclude}


def _base_and_at(spec, tenants: Mapping[str, TenantRevenue],
                 months: pd.PeriodIndex, gross_up: bool,
                 property_revenue: Optional[pd.Series],
                 ) -> tuple[pd.Series, pd.Series]:
    """The percentage base over non-excluded tenants, and those tenants'
    A&T vacancy total (negative) for the allowance reduction."""
    excluded = _excluded(spec)
    base = _zeros(months)
    at_total = _zeros(months)
    for name, revenue in tenants.items():
        if name in excluded:
            continue
        base = base + _tenant_base(revenue, spec.method,
                                   spec.include_in_pgr_accounts, months,
                                   gross_up)
        at_total = at_total + revenue.absorption_vacancy
    if (spec.method == VacancyMethod.percent_of_pgr
            and not spec.include_in_pgr_accounts
            and property_revenue is not None):
        base = base + property_revenue
    return base, at_total


def general_vacancy_series(spec: GeneralVacancy,
                           tenants: Mapping[str, TenantRevenue],
                           months: pd.PeriodIndex, analysis_begin: dt.date,
                           timing_basis: TimingBasis,
                           property_revenue: Optional[pd.Series] = None,
                           ) -> pd.Series:
    """Monthly General Vacancy (negative; spec §3.4 [AE pp. 224-228]).

    With ``reduce_by_absorption_turnover``: target = rate × base at 100%
    occupancy; posted allowance = −max(0, target − |A&T|) [AE pp. 225-226].
    Without: −(rate × as-scheduled base), independent of A&T [AE p. 226].
    Excluded tenants leave both the base and the A&T offset.
    """
    series = pd.Series(0.0, index=months, name="general_vacancy")
    if spec.method == VacancyMethod.none:
        return series
    reduce = spec.reduce_by_absorption_turnover
    base, at_total = _base_and_at(spec, tenants, months, gross_up=reduce,
                                  property_revenue=property_revenue)
    rate = _rate_series(spec.rate, months, analysis_begin, timing_basis)
    target = rate * base
    if reduce:
        allowance = (target - at_total.abs()).clip(lower=0.0)
    else:
        allowance = target
    return (-allowance).rename("general_vacancy")


def credit_loss_series(spec: CreditLoss,
                       tenants: Mapping[str, TenantRevenue],
                       general_vacancy: pd.Series,
                       months: pd.PeriodIndex, analysis_begin: dt.date,
                       timing_basis: TimingBasis,
                       property_revenue: Optional[pd.Series] = None,
                       ) -> pd.Series:
    """Monthly Credit Loss (negative; spec §3.5 [AE pp. 229-232]): applied
    after General Vacancy on the reduced base — rate × max(0, base −
    |general vacancy|) — with no A&T gross-up or offset of its own."""
    series = pd.Series(0.0, index=months, name="credit_loss")
    if spec.method == VacancyMethod.none:
        return series
    base, _ = _base_and_at(spec, tenants, months, gross_up=False,
                           property_revenue=property_revenue)
    reduced = (base + general_vacancy).clip(lower=0.0)  # GV is negative
    rate = _rate_series(spec.rate, months, analysis_begin, timing_basis)
    return (-(rate * reduced)).rename("credit_loss")
