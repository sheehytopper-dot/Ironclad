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

Pre-absorption vacant months post **nothing** to revenue; the space counts
in available (and rentable) area only — owner-directed v1 behavior,
recorded with its manual tension in DEVIATIONS.md §8. ``reabsorb``
expirations (space returning to the absorption pool) have undefined
re-pooling semantics in v1 and are refused loudly by run.py — also
DEVIATIONS.md §8. The manual's separate Available-vs-Start dates and
Absorption Months input are UI conveniences the §3.15 schema deliberately
omits (start_date + interval_months express the same schedule).
"""
from __future__ import annotations

import datetime as dt
import math
from typing import Mapping

import pandas as pd

from engine.calc.leases import _market_factor, _market_monthly
from engine.calc.timeline import snap_to_month_start
from engine.models import (
    AbsorptionSpec,
    FreeRent,
    Inflation,
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
    free rent, recoveries, and TI/LC (costs recorded; posting is Phase 3).
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

    leasing_costs = None
    if profile.ti_new is not None or profile.lc_new is not None:
        leasing_costs = LeasingCosts(ti=profile.ti_new, lc=profile.lc_new)

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
