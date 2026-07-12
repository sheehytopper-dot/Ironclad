"""Space absorption: lease-up of vacant space (Phase 2 Step 3; spec §3.15)
[AE pp. 395-403].

Each absorption spec "rapidly sub-divides and leases large areas of vacant
space ... using a simple set of assumptions and a market leasing profile"
[AE p. 395]: synthetic leases are generated on the schedule (start date +
interval months between lease starts [AE p. 397]), each taking every term
from the referenced MLP — "base rent, fixed steps, ... free rent, ...
recoveries, tenant improvements, leasing commissions, and term length"
[AE p. 396] — at **new-tenant economics** (100% new rent inflated to the
lease's own start on the market index, new free rent, new TI/LC; no
renewal blending on first generation: there is no incumbent to renew).
Thereafter each generated lease behaves exactly like a rent roll lease:
run.py resolves its rollover chain per the profile's ``upon_expiration``
through ``resolve_lease_chain``.

Lease count [AE p. 397]: with ``number_of_leases`` the area splits evenly;
with ``area_per_lease`` the count is ceil(total / average) with the final
lease taking the remainder, so the generated areas always sum exactly to
``total_area`` (keeping derived rentable area whole, spec §3.2). Names
follow the manual's series pattern, e.g. "Vacant Office 2 of 8"
[AE p. 403].

Pre-absorption vacant months follow the manual's Cash Flow convention
[AE p. 538]: Potential Base Rent includes "the market value of the
currently vacant spaces," offset one-for-one by Absorption & Turnover
Vacancy — ``pre_absorption_vacancy`` provides that market-value series per
generated lease, month-by-month at the then-current market rent. Scheduled
Base, EGR, and NOI are untouched by the gross-up (it nets to zero inside
Scheduled); what it changes is the Potential Base Rent presentation and,
critically, the A&T ledger line that general vacancy's
``reduce_by_absorption_turnover`` offset consumes (spec §3.4;
DEVIATIONS.md §8 records the 2026-07-06 correction).

**Reabsorbed space (contract leases, v1 — DEVIATIONS.md §8):** a contract
lease with ``upon_expiration = 'reabsorb'`` retires at expiration and hands
its square footage to the absorption pool. From the month after expiration
the space is carried at market value with the offsetting A&T entry —
netting to $0 in Scheduled/EGR/NOI — until absorption re-leases it or the
timeline ends. The accounting splits in two, and the ARGUS step-down is
emergent from their sum: ``reabsorption_vacancy`` posts the **uncovered
remainder** (the lease's area minus all linked specs' total_area — the full
area when nothing is linked, zero when fully covered) on the reabsorbed
lease itself, while each linked spec's generated leases post their own
pre-start phantom via ``pre_absorption_vacancy`` with ``available_from`` =
the reabsorbed lease's expiration + 1 (not timeline start — before that,
the contract tenant's real rent occupies those months). Together: the full
area at market from expiration, stepping down suite by suite as staggered
absorption leases start. Speculative/MLP-chain reabsorb stays refused (a
chain segment has no fixed expiration for the linkage to anchor on).

The manual's separate Available-vs-Start dates and Absorption Months input
are UI conveniences the §3.15 schema deliberately omits (start_date +
interval_months express the same schedule; an ARGUS-style "absorb 5,000 SF
per month" maps to area_per_lease=5000 + interval_months=1 — discrete
monthly leases, not a continuous ramp).
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Mapping

import pandas as pd

from engine.calc.leases import _market_factor, _market_monthly, lease_term_periods
from engine.calc.timeline import snap_to_month_start
from engine.models import (
    AbsorptionSpec,
    FreeRent,
    Inflation,
    LCSpec,
    Lease,
    LeaseStatus,
    LeasingCosts,
    MarketLeasingProfile,
    MoneyRate,
    MoneyUnit,
    UponExpiration,
)


def _lease_areas(spec: AbsorptionSpec) -> list[float]:
    """Per-lease areas summing exactly to ``total_area`` [AE p. 397]."""
    if spec.number_of_leases is not None:
        n = spec.number_of_leases
        return [spec.total_area / n] * n
    average = spec.area_per_lease
    n = max(1, math.ceil(spec.total_area / average - 1e-9))
    areas = [average] * (n - 1)
    areas.append(spec.total_area - average * (n - 1))
    return areas


def generate_absorption_leases(
    spec: AbsorptionSpec,
    profiles: Mapping[str, MarketLeasingProfile],
    analysis_begin: dt.date,
    inflation: Inflation,
) -> list[Lease]:
    """Generate the spec's synthetic leases (spec §3.15 [AE pp. 395-397]).

    Each lease starts ``interval_months`` after the previous one, runs the
    MLP's term at the MLP's new-tenant economics (rent inflated to its own
    start when ``term_growth`` — "changes to market assumptions ... are
    dynamically incorporated" [AE p. 395]), and carries the MLP's steps,
    free rent, recoveries, and TI/LC (inflated likewise; posted at each
    lease's start by ``engine/calc/capital.py``).
    """
    try:
        profile = profiles[spec.market_leasing_profile]
    except KeyError:
        raise ValueError(
            f"absorption {spec.name!r}: unknown market leasing profile "
            f"{spec.market_leasing_profile!r}"
        ) from None
    where = f"absorption {spec.name!r} / profile {profile.name!r}"

    if profile.market_base_rent_new.unit == MoneyUnit.pct_of_last_rent:
        raise ValueError(
            f"{where}: pct_of_last_rent market rent is meaningless for "
            "absorption of vacant space (there is no prior rent)"
        )

    areas = _lease_areas(spec)
    n = len(areas)
    start0 = pd.Period(snap_to_month_start(spec.start_date), freq="M")

    leases = []
    for i, area in enumerate(areas):
        start = start0 + i * spec.interval_months
        factor = (
            _market_factor(inflation, start, analysis_begin)
            if profile.term_growth else 1.0
        )
        rent_monthly = _market_monthly(
            profile.market_base_rent_new, area, factor, None, where
        )
        # TI and $-form LC inflate to the lease's own start exactly like
        # the rent above (a % LC needs no factor — its rent base already
        # carries it). The generated lease's contract segment then posts
        # them as literal dollars (engine/calc/capital.py).
        leasing_costs = None
        if profile.ti_new is not None or profile.lc_new is not None:
            ti = profile.ti_new
            if ti is not None:
                ti = MoneyRate(amount=ti.amount * factor, unit=ti.unit)
            lc = profile.lc_new
            if lc is not None and lc.rate is not None:
                lc = LCSpec(rate=MoneyRate(amount=lc.rate.amount * factor,
                                           unit=lc.rate.unit))
            leasing_costs = LeasingCosts(ti=ti, lc=lc)
        free_rent = None
        if profile.free_rent_months_new > 0:
            free_rent = FreeRent(months=profile.free_rent_months_new,
                                 profile=profile.free_rent_profile)
        upon = profile.upon_expiration
        leases.append(Lease(
            tenant_name=f"{spec.name} {i + 1} of {n}",  # [AE p. 403]
            area=area,
            lease_type=spec.lease_type,
            start_date=start.to_timestamp().date(),
            term_months=profile.term_months,
            status=LeaseStatus.speculative,
            base_rent=MoneyRate(amount=rent_monthly,
                                unit=MoneyUnit.dollars_per_month),
            rent_steps=list(profile.rent_increases or []),
            free_rent=free_rent,
            recoveries=profile.recoveries,
            leasing_costs=leasing_costs,
            market_leasing_profile=(
                profile.name
                if upon in (UponExpiration.market, UponExpiration.renew)
                else None
            ),
            option_profile=(
                profile.chained_profile
                if upon == UponExpiration.option else None
            ),
            upon_expiration=upon,
        ))
    return leases


def _market_value_series(
    profile: MarketLeasingProfile,
    area: float,
    first: pd.Period,
    last: pd.Period,
    months: pd.PeriodIndex,
    analysis_begin: dt.date,
    inflation: Inflation,
    where: str,
) -> pd.Series:
    """Market value of ``area`` for the months ``first``..``last``
    (inclusive), valued month-by-month at the then-current market rent —
    the profile's new-tenant rate inflated to each vacant month under
    ``term_growth`` ("changes to market assumptions ... are dynamically
    incorporated" [AE p. 395]; DEVIATIONS.md §8's month-level convention).
    Shared by the pre-absorption and reabsorption phantom paths."""
    series = pd.Series(0.0, index=months, name="vacant_market_value")
    for period in months:
        if period < first:
            continue
        if period > last:
            break
        factor = (
            _market_factor(inflation, period, analysis_begin)
            if profile.term_growth else 1.0
        )
        series[period] = _market_monthly(
            profile.market_base_rent_new, area, factor, None, where
        )
    return series


def pre_absorption_vacancy(
    leases: list[Lease],
    profile: MarketLeasingProfile,
    months: pd.PeriodIndex,
    analysis_begin: dt.date,
    inflation: Inflation,
    available_from: pd.Period | None = None,
) -> dict[str, pd.Series]:
    """Market value of each generated lease's space for the months before
    its lease starts — the "market value of the currently vacant spaces"
    that ARGUS carries in Potential Base Rent with the offsetting
    Absorption & Turnover Vacancy entry [AE p. 538].

    Valued month-by-month at the then-current market rent (module
    docstring; DEVIATIONS.md §8). ``available_from`` is the first month
    the space is vacant: ``None`` (day-one vacant space) means the start
    of the timeline; a spec linked to a reabsorbed lease passes that
    lease's expiration + 1, so no phantom posts while the contract tenant
    still occupies the space. run.py posts each series positively to Base
    Rental Revenue and negatively to Absorption & Turnover Vacancy,
    exactly like rollover downtime (spec §4.2). Returns
    ``{tenant_name: series}``.
    """
    where = f"absorption profile {profile.name!r}"
    first_vacant = months[0] if available_from is None else available_from
    vacancy: dict[str, pd.Series] = {}
    for lease in leases:
        start = pd.Period(snap_to_month_start(lease.start_date), freq="M")
        vacancy[lease.tenant_name] = _market_value_series(
            profile, lease.area, first_vacant, start - 1, months,
            analysis_begin, inflation, where,
        )
    return vacancy


def reabsorption_vacancy(
    lease: Lease,
    profile: MarketLeasingProfile,
    linked_specs: list[AbsorptionSpec],
    months: pd.PeriodIndex,
    analysis_begin: dt.date,
    inflation: Inflation,
) -> pd.Series:
    """Post-expiration phantom for a reabsorbed contract lease: the market
    value of its **uncovered remainder** — ``lease.area`` minus the linked
    specs' combined ``total_area`` — from the month after expiration
    through the end of the timeline (DEVIATIONS.md §8; the owner's ARGUS
    mechanics: potential revenue and the vacancy deduction "offset each
    other, netting to $0 ... until it is dealt with elsewhere").

    The covered portion's phantom is NOT posted here: each linked spec's
    generated leases carry it via ``pre_absorption_vacancy`` with
    ``available_from`` = expiration + 1, so the total across both paths is
    the full area at market from expiration, stepping down as staggered
    absorption leases start. With no linked specs the remainder is the
    full area (space stays vacant to timeline end); fully covered, this
    series is zero. Priced from the reabsorbed lease's own
    ``market_leasing_profile`` (required by the schema for reabsorb).
    """
    where = (f"lease {lease.tenant_name!r} (reabsorb) / "
             f"profile {profile.name!r}")
    remainder = lease.area - sum(s.total_area for s in linked_specs)
    if remainder <= 1e-9:
        return pd.Series(0.0, index=months, name="vacant_market_value")
    _, end = lease_term_periods(lease)
    return _market_value_series(
        profile, remainder, end + 1, months[-1], months,
        analysis_begin, inflation, where,
    )
