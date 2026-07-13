"""Property calculation run: spec §4.1 passes 1-6 (Phase 1 core;
Phase 2 Step 2 adds rollover projection).

Orchestrates timeline → inflation → lease chain resolution (contract term
+ speculative segments per MLP, spec §4.1 pass 3 / §4.2) → base rent,
absorption & turnover vacancy, free rent → expenses → %-of-revenue
expense resolution → recoveries → ledger assembly, and asserts the §9.3
pre-valuation invariants on every run (CLAUDE.md Conventions). Inputs
whose passes don't exist yet raise ``NotImplementedError`` rather than
silently posting nothing (Design principle "no silent numbers"):
``reabsorb`` on MLP profiles (speculative chains — DEVIATIONS.md §8; the
contract-lease variant is built), TI/LC categories (DEVIATIONS.md §16),
and the valuation-derived inputs (derived purchase prices, pct_of_value
loan amounts — Step 5). Space absorption
(Step 3 of Phase 2) generates
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
per their MLP's assignment over occupied months only; TI/LC post as lump
sums in each segment's start month (Phase 3 Step 1, spec §4.1 pass 11;
engine/calc/capital.py). Percentage rent (Step 8, spec §4.1
step 7) projects per segment over occupied months — the lease's spec on
the contract term, the MLP's on speculative terms [AE p. 376] — and is
**externally unvalidated pending golden #3** (CLAUDE.md standing gap).

Property revenues (misc / parking / storage, spec §4.1 step 9): absolute-
amount lines project once and join PGR; %-of-EGR / %-of-PGR lines re-enter
EGR through PGR, so they resolve inside the same %-of-revenue fixed point
as the management fee (self-consistent, DEVIATIONS.md §13). ``pct_of_account``
property revenue is deferred (refused loudly).

The %-of-EGR fixed point (spec §4.1 step 9; DEVIATIONS.md §6). A
recoverable %-of-EGR expense — the Clorox-shape management fee — feeds
back into EGR through the net recovery pool, so this module iterates
fee → recoveries → EGR → fee to convergence (a contraction whose factor
is share × pct). Golden #1 confirms: Management Fee = 3% of *final* EGR.
The %-of-EGR/PGR property-revenue lines join this same loop.

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
    reabsorption_vacancy,
)
from engine.calc.capital import project_lease_capital
from engine.calc.debt import (
    LoanSchedule,
    assert_debt_invariants,
    build_loan_schedule,
)
from engine.calc.expenses import PCT_UNITS, project_expense
from engine.calc.investment import acquisition_flows, segment_security_deposits
from engine.calc.leases import (
    LeaseRentCashflows,
    LeaseSegment,
    contract_free_fraction,
    lease_term_periods,
    project_contract_rent,
    project_segment_rent,
    resolve_lease_chain,
    segment_free_fraction,
)
from engine.calc.ledger import (
    MonthlyLedger,
    assemble_ledger,
    assert_invariants,
    occupancy_series,
    occupied_area_from_chains,
    rentable_area_series,
)
from engine.calc.misc_items import project_segment_misc_items
from engine.calc.percentage_rent import project_segment_percentage_rent
from engine.calc.resale import (
    ResaleResult,
    assert_resale_invariants,
    compute_resale,
)
from engine.calc.sensitivity import SensitivityMatrices, compute_sensitivity
from engine.calc.valuation import (
    ValuationResult,
    assert_pv_irr_self_consistency,
    compute_valuation,
)
from engine.calc.recoveries import (
    PoolAudit,
    RecoveryContext,
    project_segment_recoveries,
)
from engine.calc.revenues import (
    PCT_UNITS as REVENUE_PCT_UNITS,
    project_property_revenue,
)
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
    PropertyRevenue,
    RevenueUnit,
    UponExpiration,
)

#: Fixed-point controls for %-of-revenue expenses. The iteration is a
#: contraction with factor Σ(share × pct); per-month min/max limits on a
#: fee are 1-Lipschitz clamps that only tighten it (recoveries.py module
#: docstring). 100 rounds is far beyond any plausible convergence need
#: and exists only to turn a divergent input (fees summing past 100% of
#: revenue) into a loud error.
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
    percentage_rent: dict[str, pd.Series]           # by tenant_name
    misc_tenant_revenue: dict[str, pd.Series]       # by tenant_name
    recoveries: dict[str, pd.Series]                # by tenant_name
    recovery_audit: list[PoolAudit]                 # per tenant per pool
    tenant_improvements: dict[str, pd.Series]       # by tenant_name (positive $)
    leasing_commissions: dict[str, pd.Series]       # by tenant_name (positive $)
    security_deposits: dict[str, pd.Series]         # by tenant_name (signed)
    purchase_price: pd.Series                       # negative at purchase month
    closing_costs: pd.Series                        # negative
    loan_schedules: list[LoanSchedule]              # per loan (§7 report 20)
    resale: Optional[ResaleResult]                  # §7 report 21 detail
    valuation: Optional[ValuationResult]            # §7 reports 8-9 detail
    sensitivity: Optional[SensitivityMatrices]      # §7 reports 5-6 detail
    general_vacancy: pd.Series                      # negative
    credit_loss: pd.Series                          # negative
    expense_series: list[tuple[ExpenseItem, pd.Series]]
    property_revenue: pd.Series                     # parking/storage/misc total


def _phase_guards(model: PropertyModel) -> None:
    """Refuse inputs whose calculation passes don't exist yet (Iron Rule 2 /
    no silent numbers) with the phase that will add them."""

    def refuse(condition: bool, what: str, phase: str) -> None:
        if condition:
            raise NotImplementedError(
                f"{what} is not implemented until {phase}; "
                "remove the input or wait for that phase"
            )

    for rev in (list(model.miscellaneous_revenues) + list(model.parking_revenues)
                + list(model.storage_revenues)):
        refuse(rev.unit == RevenueUnit.pct_of_account,
               f"property revenue {rev.name!r}: unit 'pct_of_account'",
               "a later phase (DEVIATIONS.md §13)")
    for lease in model.rent_roll:
        where = f"lease {lease.tenant_name!r}: "
        if lease.leasing_costs is not None:
            refuse(lease.leasing_costs.ti_category is not None
                   or lease.leasing_costs.lc_category is not None,
                   where + "TI/LC categories",
                   "a later phase (DEVIATIONS.md §16)")
    for profile in model.market_leasing_profiles:
        where = f"market leasing profile {profile.name!r}: "
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
    # (spec §4.2). Vacant space — pre-absorption and reabsorbed alike —
    # carries market value in Potential Base Rent with the offsetting A&T
    # entry [AE p. 538] and counts in rentable/available area
    # (DEVIATIONS.md §8).
    profiles = {p.name: p for p in model.market_leasing_profiles}
    synthetic: list = []
    linked_generated_names: set[str] = set()
    pre_vacancy: dict[str, pd.Series] = {}
    reabsorb_end = {
        lease.tenant_name: lease_term_periods(lease)[1]
        for lease in model.rent_roll
        if lease.upon_expiration == UponExpiration.reabsorb
    }
    for spec in model.absorption:
        generated = generate_absorption_leases(
            spec, profiles, begin, model.inflation
        )
        synthetic.extend(generated)
        # A spec linked to a reabsorbed lease re-leases that lease's space:
        # its phantom starts when the space becomes vacant (expiration + 1),
        # not at timeline start (DEVIATIONS.md §8).
        available_from = (
            reabsorb_end[spec.reabsorbed_from] + 1
            if spec.reabsorbed_from is not None else None
        )
        pre_vacancy.update(pre_absorption_vacancy(
            generated, profiles[spec.market_leasing_profile],
            months, begin, model.inflation, available_from=available_from,
        ))
        if spec.reabsorbed_from is not None:
            linked_generated_names.update(l.tenant_name for l in generated)
    # Reabsorbed contract leases: the uncovered remainder carries the
    # market-in / A&T-out phantom from expiration to timeline end
    # (DEVIATIONS.md §8; covered portions ride the linked specs above).
    for lease in model.rent_roll:
        if lease.upon_expiration != UponExpiration.reabsorb:
            continue
        linked = [s for s in model.absorption
                  if s.reabsorbed_from == lease.tenant_name]
        pre_vacancy[lease.tenant_name] = reabsorption_vacancy(
            lease, profiles[lease.market_leasing_profile], linked,
            months, begin, model.inflation,
        )
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
    # Derived rentable area counts a reabsorbed lease's stated area as the
    # permanent SF anchor for its space — leases generated by linked specs
    # re-lease that same square footage and are excluded from the sum
    # (fixed/schedule modes are unaffected).
    rentable_leases = [l for l in all_leases
                       if l.tenant_name not in linked_generated_names]
    rentable = rentable_area_series(model.area_measures, rentable_leases,
                                    months)
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

    # Pass 4b: percentage rent per lease (spec §4.1 step 7; [AE pp. 249-251,
    # 590]). It depends on sales volume and base + steps + CPI only — never
    # on EGR — so it computes once here and enters the fixed point below as
    # a constant (the contraction bound is untouched). Chain series carry
    # exactly the segment's potential rent within its occupied months, and
    # a speculative segment's CPI series is zero there (DEVIATIONS.md §7).
    percentage_rent = {
        tenant: sum(
            (project_segment_percentage_rent(
                segment, months,
                base_rent=lease_rents[tenant].base_rent,
                cpi_adjustment=lease_rents[tenant].cpi_adjustment,
                analysis_begin=begin, inflation=model.inflation,
            ) for segment in segments),
            pd.Series(0.0, index=months),
        )
        for tenant, segments in chains.items()
    }
    pct_rent_total = sum(percentage_rent.values(),
                         pd.Series(0.0, index=months))

    # Pass 11 (computed here — it depends on the chains only): TI/LC lump
    # sums in each segment's start month [AE pp. 245-248], contract and
    # speculative segments alike (Phase 3 Step 1; engine/calc/capital.py).
    # Positive dollars per tenant; the ledger posts them negated.
    fr_profiles = {p.name: p for p in model.free_rent_profiles}
    tenant_improvements: dict[str, pd.Series] = {}
    leasing_commissions: dict[str, pd.Series] = {}
    for tenant, segments in chains.items():
        ti_series, lc_series = project_lease_capital(
            segments, months, begin, model.inflation, fr_profiles
        )
        tenant_improvements[tenant] = ti_series
        leasing_commissions[tenant] = lc_series
    ti_total = sum(tenant_improvements.values(),
                   pd.Series(0.0, index=months))
    lc_total = sum(leasing_commissions.values(),
                   pd.Series(0.0, index=months))

    # Step 2 below-the-line flows (spec §3.16/§3.12; [AE pp. 435-437,
    # 384, 431-433]): acquisition (fixed price only — derived derivations
    # refuse inside acquisition_flows until Step 5) and per-segment
    # security deposits. EXTERNALLY UNVALIDATED — no golden populates
    # either input (DEVIATIONS.md §17).
    if model.purchase is not None:
        purchase_price, closing_costs = acquisition_flows(
            model.purchase, months, begin
        )
    else:
        purchase_price = pd.Series(0.0, index=months, name="purchase_price")
        closing_costs = pd.Series(0.0, index=months, name="closing_costs")
    security_deposits = {
        tenant: segment_security_deposits(segments, months)
        for tenant, segments in chains.items()
    }
    deposits_total = sum(security_deposits.values(),
                         pd.Series(0.0, index=months))

    # Pass 12: debt (spec §3.17; [AE pp. 438-449]) — per-loan schedules
    # with the §9.3 debt invariants asserted per loan; the ledger gets
    # the aggregated financing section. Validation = worked-example
    # tests + the owner's bank-calculator hand-check (DEVIATIONS.md
    # §18) — no golden has loans.
    loan_schedules = [
        build_loan_schedule(loan, months, begin, model.purchase,
                            model.inflation)
        for loan in model.loans
    ]
    for schedule in loan_schedules:
        assert_debt_invariants(schedule)
    zeros = pd.Series(0.0, index=months)
    debt_funding = sum((s.funding for s in loan_schedules), zeros.copy())
    interest_expense = sum((s.interest for s in loan_schedules),
                           zeros.copy())
    principal_payments = sum((s.principal for s in loan_schedules),
                             zeros.copy())
    loan_costs_total = sum((s.loan_costs for s in loan_schedules),
                           zeros.copy())

    # Pass 5: expenses that don't reference revenue.
    area = model.area_measures.property_size

    def project(item: ExpenseItem,
                reference: Optional[pd.Series] = None) -> pd.Series:
        return project_expense(
            item, months, begin, model.inflation, area=area,
            occupancy=occupancy, occupied_area=occupied,
            available_area=available, reference=reference,
            fiscal_year_end_month=model.property.fiscal_year_end_month,
        )

    fixed_items = [i for i in model.expenses if i.unit not in PCT_UNITS]
    pct_items = [i for i in model.expenses if i.unit in PCT_UNITS]
    fixed_series = [(item, project(item)) for item in fixed_items]

    # Pass 9: property revenues (misc / parking / storage, spec §4.1 step 9).
    # Absolute-amount lines are EGR-independent and project once; %-of-EGR/PGR
    # lines re-enter EGR through PGR, so they join the fixed point below (the
    # same shape as the recoverable management fee — DEVIATIONS.md §6, §13).
    def project_revenue(item: PropertyRevenue,
                        reference: Optional[pd.Series] = None) -> pd.Series:
        return project_property_revenue(
            item, months, begin, model.inflation, area=area,
            occupancy=occupancy, occupied_area=occupied,
            available_area=available, reference=reference,
        )

    all_revenues = (list(model.miscellaneous_revenues)
                    + list(model.parking_revenues)
                    + list(model.storage_revenues))
    rev_pct_items = [r for r in all_revenues if r.unit in REVENUE_PCT_UNITS]
    rev_abs_items = [r for r in all_revenues if r.unit not in REVENUE_PCT_UNITS]
    property_revenue_fixed = sum(
        (project_revenue(r) for r in rev_abs_items),
        pd.Series(0.0, index=months),
    )
    rev_pct_series = {r.name: pd.Series(0.0, index=months)
                      for r in rev_pct_items}

    # Pass 6 + passes 9-10 inside one fixed point (spec §4.1;
    # DEVIATIONS.md §6): recoveries feed EGR; general vacancy and credit
    # loss deduct from it (their bases include recoveries); a %-of-EGR fee
    # feeds recoveries — so all of it iterates together to convergence.
    # Recoveries run per segment: each segment's own assignment, occupied
    # months only.
    pct_series = {item.name: pd.Series(0.0, index=months)
                  for item in pct_items}
    timing_basis = model.inflation.timing_basis

    # Vacancy/credit-loss tenant overrides may reference a tenant by name
    # OR external_id (intake accepts both); the tenants dict is keyed by
    # tenant_name, so resolve every accepted ref to its tenant_name once
    # here rather than in the fixed-point loop (Codex-review correction —
    # DEVIATIONS.md §23).
    tenant_name_by_ref: dict[str, str] = {}
    for lease in model.rent_roll:
        tenant_name_by_ref[lease.tenant_name] = lease.tenant_name
        if lease.external_id:
            tenant_name_by_ref[lease.external_id] = lease.tenant_name

    # Context for user structures / gross-up, and per-segment free-rent
    # abatement fractions (applied when the segment's profile abates
    # recoveries [AE p. 254]) — all fee-independent, computed once.
    recovery_context = RecoveryContext(
        occupancy=occupancy, occupied_area=occupied, property_size=area,
        structures={s.name: s for s in model.recovery_structures},
        expense_groups={g.name: list(g.members) for g in model.expense_groups},
    )

    def _segment_abatement(lease, segment,
                           flag: str = "abate_recoveries",
                           ) -> Optional[pd.Series]:
        """Fractional free-month series when the segment's free-rent
        profile abates the given charge family [AE p. 254] — recoveries
        (``abate_recoveries``) or miscellaneous items
        (``abate_miscellaneous``)."""
        if segment.speculative:
            profile = _free_rent_profile(segment.free_rent_profile, model)
            if profile is not None and getattr(profile, flag):
                return segment_free_fraction(segment, months)
            return None
        if lease.free_rent is None:
            return None
        profile = _free_rent_profile(lease.free_rent.profile, model)
        if profile is not None and getattr(profile, flag):
            return contract_free_fraction(lease, months)
        return None

    abatements = {
        lease.tenant_name: [
            _segment_abatement(lease, segment)
            for segment in chains[lease.tenant_name]
        ]
        for lease in all_leases
    }

    # Pass 8: tenant miscellaneous items (spec §3.12; [AE pp. 378-381,
    # 240-244]) — fee-independent like percentage rent, so a constant in
    # the fixed point below. Contract terms carry the lease's items, each
    # speculative segment its MLP's; occupied months only. Free rent
    # abates an item only when the item opts in (free_rent_abates) AND the
    # profile abates miscellaneous items (abate_miscellaneous).
    misc_tenant = {
        lease.tenant_name: sum(
            (project_segment_misc_items(
                segment, months, analysis_begin=begin,
                inflation=model.inflation,
                abatement=_segment_abatement(lease, segment,
                                             "abate_miscellaneous"),
            ) for segment in chains[lease.tenant_name]),
            pd.Series(0.0, index=months),
        )
        for lease in all_leases
    }
    misc_total = sum(misc_tenant.values(), pd.Series(0.0, index=months))

    def recoveries_from(expense_series,
                        audit: Optional[list] = None) -> dict[str, pd.Series]:
        return {
            tenant: sum(
                (project_segment_recoveries(
                    s, months, expense_series, rentable,
                    analysis_begin=begin, inflation=model.inflation,
                    context=recovery_context, abatement=fraction,
                    audit=audit,
                ) for s, fraction in zip(segments, abatements[tenant])),
                pd.Series(0.0, index=months),
            )
            for tenant, segments in chains.items()
        }

    def property_flows(expense_series, property_revenue_total,
                       audit: Optional[list] = None):
        """Recoveries → property revenue → vacancy/credit loss → Total PGR /
        EGR, exactly as the ledger defines them (spec §4.1 steps 6, 9, 10).
        Property revenue joins PGR and the percent-of-PGR vacancy base."""
        recoveries = recoveries_from(expense_series, audit=audit)
        tenants = {
            tenant: TenantRevenue(
                scheduled=(lease_rents[tenant].base_rent
                           + absorption[tenant]
                           + lease_rents[tenant].free_rent),
                cpi=lease_rents[tenant].cpi_adjustment,
                recoveries=recoveries[tenant],
                absorption_vacancy=absorption[tenant],
                percentage_rent=percentage_rent[tenant],
                misc=misc_tenant[tenant],
            )
            for tenant in chains
        }
        gv = general_vacancy_series(model.general_vacancy, tenants, months,
                                    begin, timing_basis,
                                    property_revenue=property_revenue_total,
                                    tenant_name_by_ref=tenant_name_by_ref)
        cl = credit_loss_series(model.credit_loss, tenants, gv, months,
                                begin, timing_basis,
                                property_revenue=property_revenue_total,
                                tenant_name_by_ref=tenant_name_by_ref)
        recovery_total = sum(recoveries.values(),
                             pd.Series(0.0, index=months))
        pgr = (base_total + absorption_total + free_total + cpi_total
               + pct_rent_total + misc_total + recovery_total
               + property_revenue_total)
        egr = pgr + gv + cl
        return recoveries, gv, cl, pgr, egr

    def property_revenue_from_state() -> pd.Series:
        return property_revenue_fixed + sum(
            rev_pct_series.values(), pd.Series(0.0, index=months)
        )

    for _ in range(_MAX_FIXED_POINT_ROUNDS):
        expense_series = fixed_series + [
            (item, pct_series[item.name]) for item in pct_items
        ]
        property_revenue_total = property_revenue_from_state()
        recoveries, gv, cl, pgr, egr = property_flows(expense_series,
                                                      property_revenue_total)
        if not pct_items and not rev_pct_items:
            break
        delta = 0.0
        for item in pct_items:
            reference = egr if item.unit == ExpenseUnit.pct_of_egr else pgr
            updated = project(item, reference=reference)
            delta = max(delta, float((updated - pct_series[item.name]).abs().max()))
            pct_series[item.name] = updated
        for rev in rev_pct_items:
            reference = egr if rev.unit == RevenueUnit.pct_of_egr else pgr
            updated = project_revenue(rev, reference=reference)
            delta = max(delta,
                        float((updated - rev_pct_series[rev.name]).abs().max()))
            rev_pct_series[rev.name] = updated
        if delta < _FIXED_POINT_TOL:
            expense_series = fixed_series + [
                (item, pct_series[item.name]) for item in pct_items
            ]
            break
    else:
        raise ValueError(
            "%-of-revenue lines did not converge — their combined "
            "percentages likely meet or exceed 100% of revenue"
        )

    # Final pass with the converged fee, collecting the per-tenant per-pool
    # audit detail the Recovery Audit report consumes (spec §7 report 18).
    property_revenue_total = property_revenue_from_state()
    recovery_audit: list[PoolAudit] = []
    recoveries, gv, cl, pgr, egr = property_flows(expense_series,
                                                  property_revenue_total,
                                                  audit=recovery_audit)

    def _assemble(**resale_columns):
        return assemble_ledger(
            months,
            lease_rents=lease_rents.values(),
            recoveries=recoveries.values(),
            expenses=expense_series,
            absorption_vacancy=absorption_total,
            percentage_rent=pct_rent_total,
            misc_tenant_revenue=misc_total,
            property_revenue=property_revenue_total,
            general_vacancy=gv,
            credit_loss=cl,
            tenant_improvements=-ti_total,
            leasing_commissions=-lc_total,
            debt_funding=debt_funding,
            interest_expense=interest_expense,
            principal_payments=principal_payments,
            loan_costs=loan_costs_total,
            purchase_price=purchase_price,
            closing_costs=closing_costs,
            security_deposits=deposits_total,
            **resale_columns,
        )

    ledger = _assemble()

    # Pass 13: resale (spec §3.18; [AE pp. 464-471]) — computed FROM the
    # assembled ledger (valuation never recomputes it, spec §4.1), then
    # the two below-the-line resale columns post via reassembly. Only
    # ``valuation.resale`` is consumed this step — the discount/direct-
    # cap machinery is Step 5 (direct_cap is guarded above). §9.3
    # payoff-at-resale asserts on every run with resale + loans.
    resale_result = None
    valuation_result = None
    if model.valuation is not None:
        resale_result = compute_resale(
            model.valuation.resale, ledger, months, occupancy, model,
            loan_schedules,
        )
        assert_resale_invariants(resale_result, loan_schedules)
        ledger = _assemble(
            net_resale_proceeds=resale_result.proceeds_series,
            loan_payoff_at_resale=resale_result.payoff_series,
        )
        # Pass 14: PV / IRR / direct cap from the assembled ledger
        # (valuation never recomputes it, spec §4.1); §9.3
        # self-consistency asserts when the total t0 outlay == unleveraged
        # PV. Valuation reads per-loan funding timing off the schedules.
        valuation_result = compute_valuation(
            model.valuation, ledger, months, begin, model, resale_result,
            loan_schedules,
        )
        assert_pv_irr_self_consistency(valuation_result, model)

    assert_invariants(
        ledger, analysis_begin=begin,
        fiscal_year_end_month=model.property.fiscal_year_end_month,
        occupied_area=occupied, rentable_area=rentable,
    )
    result = RunResult(
        ledger=ledger, months=months, occupied_area=occupied,
        rentable_area=rentable, occupancy=occupancy, segments=chains,
        lease_rents=lease_rents, absorption_vacancy=absorption,
        percentage_rent=percentage_rent,
        misc_tenant_revenue=misc_tenant,
        recoveries=recoveries, recovery_audit=recovery_audit,
        tenant_improvements=tenant_improvements,
        leasing_commissions=leasing_commissions,
        security_deposits=security_deposits,
        purchase_price=purchase_price,
        closing_costs=closing_costs,
        loan_schedules=loan_schedules,
        resale=resale_result,
        valuation=valuation_result,
        sensitivity=None,
        general_vacancy=gv, credit_loss=cl,
        expense_series=expense_series,
        property_revenue=property_revenue_total,
    )
    # Pass 15: sensitivity matrices — a pure re-computation over the
    # assembled result (never the ledger, spec §4.1). None when there is
    # no valuation or the resale method has no exit cap.
    result.sensitivity = compute_sensitivity(model, result)
    return result
