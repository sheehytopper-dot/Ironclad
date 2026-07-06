"""Property calculation run: spec §4.1 passes 1-6 (Phase 1 core;
Phase 2 Step 2 adds rollover projection).

Orchestrates timeline → inflation → lease chain resolution (contract term
+ speculative segments per MLP, spec §4.1 pass 3 / §4.2) → base rent,
absorption & turnover vacancy, free rent → expenses → %-of-revenue
expense resolution → recoveries → ledger assembly, and asserts the §9.3
pre-valuation invariants on every run (CLAUDE.md Conventions). Inputs
whose passes don't exist yet raise ``NotImplementedError`` rather than
silently posting nothing (Design principle "no silent numbers"):
non-net recovery structures (Step 5), percentage rent (Step 8),
``reabsorb`` expirations (DEVIATIONS.md §8), TI/LC posting, security
deposits, and debt (Phase 3). Space absorption (Step 3) generates
synthetic leases per spec §3.15 that join the rent roll for every
downstream pass; pre-absorption vacant space grosses Base Rental Revenue
up to market with the offsetting A&T entry [AE p. 538]. General vacancy
and credit loss (Step 4) compute inside the fixed point — their bases
include recoveries, and the A&T offset consumes the vacancy already in
the ledger (spec §3.4).

Rollover projection (spec §4.2/§2.3): downtime months post the blended
market rent to Base Rental Revenue and its negative to Absorption &
Turnover Vacancy — PGR stays a full-occupancy figure; occupied area drops
by (1 − renewal weight) × area over downtime; speculative segments recover
per their MLP's assignment over occupied months only; TI/LC stay recorded
on segments, unposted (Phase 3).

The %-of-EGR fixed point (spec §4.1 step 9; DEVIATIONS.md §6). A
recoverable %-of-EGR expense — the Clorox-shape management fee — feeds
back into EGR through the net recovery pool, so this module iterates
fee → recoveries → EGR → fee to convergence (a contraction whose factor
is share × pct). Golden #1 confirms: Management Fee = 3% of *final* EGR.

Per-area expense units are denominated on Property Size (gross building
area, spec §3.2/§3.11); occupied/available-area units and ``pct_fixed``
scaling use the occupancy series computed from the resolved chains.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from engine.calc.absorption import (
    generate_absorption_leases,
    pre_absorption_vacancy,
)
from engine.calc.expenses import PCT_UNITS, project_expense
from engine.calc.leases import (
    LeaseRentCashflows,
    LeaseSegment,
    project_contract_rent,
    project_segment_rent,
    resolve_lease_chain,
)
from engine.calc.ledger import (
    MonthlyLedger,
    assemble_ledger,
    assert_invariants,
    occupancy_series,
    occupied_area_from_chains,
    rentable_area_series,
)
from engine.calc.recoveries import project_segment_recoveries
from engine.calc.timeline import build_month_index
from engine.calc.vacancy import (
    TenantRevenue,
    credit_loss_series,
    general_vacancy_series,
)
from engine.models import (
    ExpenseItem,
    ExpenseUnit,
    FreeRentProfile,
    PropertyModel,
    UponExpiration,
)

#: Fixed-point controls for %-of-revenue expenses. The iteration is a
#: contraction with factor Σ(share × pct); 100 rounds is far beyond any
#: plausible convergence need and exists only to turn a divergent input
#: (fees summing past 100% of revenue) into a loud error.
_MAX_FIXED_POINT_ROUNDS = 100
_FIXED_POINT_TOL = 1e-9


@dataclass
class RunResult:
    """One property calculation (passes 1-6) with full audit detail retained
    (spec §1.3 "no silent numbers")."""

    ledger: MonthlyLedger
    months: pd.PeriodIndex
    occupied_area: pd.Series
    rentable_area: pd.Series
    occupancy: pd.Series
    segments: dict[str, list[LeaseSegment]]         # by tenant_name
    lease_rents: dict[str, LeaseRentCashflows]      # by tenant_name (chain totals)
    absorption_vacancy: dict[str, pd.Series]        # by tenant_name (negative)
    recoveries: dict[str, pd.Series]                # by tenant_name
    general_vacancy: pd.Series                      # negative
    credit_loss: pd.Series                          # negative
    expense_series: list[tuple[ExpenseItem, pd.Series]]


def _phase_guards(model: PropertyModel) -> None:
    """Refuse inputs whose calculation passes don't exist yet (Iron Rule 2 /
    no silent numbers) with the phase that will add them."""

    def refuse(condition: bool, what: str, phase: str) -> None:
        if condition:
            raise NotImplementedError(
                f"{what} is not implemented until {phase}; "
                "remove the input or wait for that phase"
            )

    refuse(bool(model.miscellaneous_revenues or model.parking_revenues
                or model.storage_revenues), "property revenues", "Phase 2")
    refuse(bool(model.loans), "debt", "Phase 3")
    for lease in model.rent_roll:
        where = f"lease {lease.tenant_name!r}: "
        refuse(lease.percentage_rent is not None,
               where + "percentage rent", "Phase 2 Step 8")
        refuse(bool(lease.miscellaneous_items),
               where + "miscellaneous tenant items", "Phase 2")
        refuse(lease.leasing_costs is not None,
               where + "contract TIs/LCs", "Phase 3")
        refuse(lease.security_deposit is not None,
               where + "security deposits", "Phase 3")
        refuse(lease.upon_expiration == UponExpiration.reabsorb,
               where + "upon_expiration 'reabsorb'",
               "re-pooling semantics are defined (DEVIATIONS.md §8)")
    for profile in model.market_leasing_profiles:
        where = f"market leasing profile {profile.name!r}: "
        refuse(profile.percentage_rent is not None,
               where + "speculative percentage rent", "Phase 2 Step 8")
        refuse(bool(profile.miscellaneous_items),
               where + "rollover miscellaneous items", "Phase 2")
        refuse(profile.security_deposit is not None,
               where + "security deposits", "Phase 3")
        refuse(profile.upon_expiration == UponExpiration.reabsorb,
               where + "upon_expiration 'reabsorb'",
               "re-pooling semantics are defined (DEVIATIONS.md §8)")
    for item in model.expenses:
        refuse(item.unit == ExpenseUnit.pct_of_account,
               f"expense {item.name!r}: unit 'pct_of_account'", "Phase 2")


def _free_rent_profile(ref: Optional[str],
                       model: PropertyModel) -> Optional[FreeRentProfile]:
    if ref is None:
        return None
    return {p.name: p for p in model.free_rent_profiles}[ref]


def run_property(model: PropertyModel) -> RunResult:
    """Execute spec §4.1 passes 1-6 and return the assembled monthly ledger
    with the §9.3 pre-valuation invariants asserted."""
    _phase_guards(model)
    begin = model.property.analysis_begin

    # Pass 1: timeline. Pass 2 (inflation factors) happens inside each
    # projection call via the shared inflation module.
    months = build_month_index(begin, model.property.analysis_term_years)

    # Pass 3: lease chain resolution — contract terms + absorption-generated
    # leases (spec §3.15: each behaves like a rent roll lease thereafter),
    # each resolved into speculative segments per MLP through timeline end
    # (spec §4.2). Pre-absorption vacant months post nothing to revenue;
    # the space counts in rentable/available area (DEVIATIONS.md §8).
    profiles = {p.name: p for p in model.market_leasing_profiles}
    synthetic: list = []
    pre_vacancy: dict[str, pd.Series] = {}
    for spec in model.absorption:
        generated = generate_absorption_leases(
            spec, profiles, begin, model.inflation
        )
        synthetic.extend(generated)
        pre_vacancy.update(pre_absorption_vacancy(
            generated, profiles[spec.market_leasing_profile],
            months, begin, model.inflation,
        ))
    all_leases = list(model.rent_roll) + synthetic
    names = [lease.tenant_name for lease in all_leases]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ValueError(
            f"tenant names collide across rent roll and absorption: "
            f"{sorted(duplicates)}"
        )
    chains = {
        lease.tenant_name: resolve_lease_chain(
            lease, months, begin, model.inflation, profiles
        )
        for lease in all_leases
    }
    occupied = occupied_area_from_chains(chains.values(), months)
    rentable = rentable_area_series(model.area_measures, all_leases, months)
    occupancy = occupancy_series(occupied, rentable)
    available = (rentable - occupied).rename("available_area")

    # Pass 4: base rent, steps, CPI, free rent, absorption & turnover
    # vacancy per lease (contract portion + speculative segments).
    lease_rents: dict[str, LeaseRentCashflows] = {}
    absorption: dict[str, pd.Series] = {}
    for lease in all_leases:
        contract_free = (
            _free_rent_profile(lease.free_rent.profile, model)
            if lease.free_rent is not None else None
        )
        rents = project_contract_rent(
            lease, months, begin, model.inflation,
            free_rent_profile=contract_free,
        )
        vacancy = pd.Series(0.0, index=months)
        for segment in chains[lease.tenant_name]:
            if not segment.speculative:
                continue
            spec = project_segment_rent(
                segment, months,
                free_rent_profile=_free_rent_profile(
                    segment.free_rent_profile, model
                ),
            )
            rents.base_rent += spec.base_rent
            rents.free_rent += spec.free_rent
            vacancy += spec.absorption_vacancy
        # pre-absorption vacant space: market value to Base Rental Revenue,
        # offset in A&T Vacancy [AE p. 538] (DEVIATIONS.md §8)
        pre = pre_vacancy.get(lease.tenant_name)
        if pre is not None:
            rents.base_rent += pre
            vacancy -= pre
        lease_rents[lease.tenant_name] = rents
        absorption[lease.tenant_name] = vacancy

    base_total = sum((r.base_rent for r in lease_rents.values()),
                     pd.Series(0.0, index=months))
    cpi_total = sum((r.cpi_adjustment for r in lease_rents.values()),
                    pd.Series(0.0, index=months))
    free_total = sum((r.free_rent for r in lease_rents.values()),
                     pd.Series(0.0, index=months))
    absorption_total = sum(absorption.values(), pd.Series(0.0, index=months))

    # Pass 5: expenses that don't reference revenue.
    area = model.area_measures.property_size

    def project(item: ExpenseItem,
                reference: Optional[pd.Series] = None) -> pd.Series:
        return project_expense(
            item, months, begin, model.inflation, area=area,
            occupancy=occupancy, occupied_area=occupied,
            available_area=available, reference=reference,
        )

    fixed_items = [i for i in model.expenses if i.unit not in PCT_UNITS]
    pct_items = [i for i in model.expenses if i.unit in PCT_UNITS]
    fixed_series = [(item, project(item)) for item in fixed_items]

    # Pass 6 + passes 9-10 inside one fixed point (spec §4.1;
    # DEVIATIONS.md §6): recoveries feed EGR; general vacancy and credit
    # loss deduct from it (their bases include recoveries); a %-of-EGR fee
    # feeds recoveries — so all of it iterates together to convergence.
    # Recoveries run per segment: each segment's own assignment, occupied
    # months only.
    pct_series = {item.name: pd.Series(0.0, index=months)
                  for item in pct_items}
    timing_basis = model.inflation.timing_basis

    def recoveries_from(expense_series) -> dict[str, pd.Series]:
        return {
            tenant: sum(
                (project_segment_recoveries(
                    s, months, expense_series, rentable,
                    analysis_begin=begin, inflation=model.inflation,
                ) for s in segments),
                pd.Series(0.0, index=months),
            )
            for tenant, segments in chains.items()
        }

    def property_flows(expense_series):
        """Recoveries → vacancy/credit loss → Total PGR / EGR, exactly as
        the ledger defines them (spec §4.1 steps 6, 10)."""
        recoveries = recoveries_from(expense_series)
        tenants = {
            tenant: TenantRevenue(
                scheduled=(lease_rents[tenant].base_rent
                           + absorption[tenant]
                           + lease_rents[tenant].free_rent),
                cpi=lease_rents[tenant].cpi_adjustment,
                recoveries=recoveries[tenant],
                absorption_vacancy=absorption[tenant],
            )
            for tenant in chains
        }
        gv = general_vacancy_series(model.general_vacancy, tenants, months,
                                    begin, timing_basis)
        cl = credit_loss_series(model.credit_loss, tenants, gv, months,
                                begin, timing_basis)
        recovery_total = sum(recoveries.values(),
                             pd.Series(0.0, index=months))
        pgr = (base_total + absorption_total + free_total + cpi_total
               + recovery_total)
        egr = pgr + gv + cl
        return recoveries, gv, cl, pgr, egr

    for _ in range(_MAX_FIXED_POINT_ROUNDS):
        expense_series = fixed_series + [
            (item, pct_series[item.name]) for item in pct_items
        ]
        recoveries, gv, cl, pgr, egr = property_flows(expense_series)
        if not pct_items:
            break
        delta = 0.0
        for item in pct_items:
            reference = egr if item.unit == ExpenseUnit.pct_of_egr else pgr
            updated = project(item, reference=reference)
            delta = max(delta, float((updated - pct_series[item.name]).abs().max()))
            pct_series[item.name] = updated
        if delta < _FIXED_POINT_TOL:
            expense_series = fixed_series + [
                (item, pct_series[item.name]) for item in pct_items
            ]
            recoveries, gv, cl, pgr, egr = property_flows(expense_series)
            break
    else:
        raise ValueError(
            "%-of-revenue expenses did not converge — their combined "
            "percentages likely meet or exceed 100% of revenue"
        )

    ledger = assemble_ledger(
        months,
        lease_rents=lease_rents.values(),
        recoveries=recoveries.values(),
        expenses=expense_series,
        absorption_vacancy=absorption_total,
        general_vacancy=gv,
        credit_loss=cl,
    )
    assert_invariants(
        ledger, analysis_begin=begin,
        fiscal_year_end_month=model.property.fiscal_year_end_month,
        occupied_area=occupied, rentable_area=rentable,
    )
    return RunResult(
        ledger=ledger, months=months, occupied_area=occupied,
        rentable_area=rentable, occupancy=occupancy, segments=chains,
        lease_rents=lease_rents, absorption_vacancy=absorption,
        recoveries=recoveries, general_vacancy=gv, credit_loss=cl,
        expense_series=expense_series,
    )
