"""Property calculation run: spec §4.1 passes 1-6 (Phase 1).

Orchestrates timeline → inflation → contract leases → expenses →
%-of-revenue expense resolution → net recoveries → ledger assembly, and
asserts the §9.3 pre-valuation invariants on every run (CLAUDE.md
Conventions). Phase 1 models the contract term only: no rollover blending,
absorption, vacancy/credit loss, percentage rent, TI/LC, debt, or
valuation — inputs that would need those passes raise ``NotImplementedError``
rather than silently posting nothing (Design principle "no silent numbers").

The %-of-EGR fixed point (spec §4.1 step 9). A recoverable %-of-EGR expense
— the Clorox-shape management fee — feeds back into EGR through the net
recovery pool: EGR includes recoveries, recoveries include the fee, the fee
is a percent of EGR. The spec's "single second pass" language covers
%-of-EGR *revenue* items, which reference EGR excluding themselves and need
no iteration; the recovery feedback loop is indirect, so this module
iterates fee → recoveries → EGR → fee to convergence (a contraction whose
factor is share × pct — ≈0.03 for the Clorox 3% fee — so a handful of
rounds reaches machine precision). The Clorox golden confirms the converged
relationship: Management Fee = 3% of *final* EGR (FY2027: 117,818 ≈ 3% ×
3,927,262), which equals pct/(1−pct) × EGR-excluding-the-fee at 100% share.

Per-area expense units are denominated on Property Size (gross building
area, spec §3.2/§3.11); occupied/available-area units and ``pct_fixed``
scaling use the occupancy series computed from the rent roll.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from engine.calc.expenses import PCT_UNITS, project_expense
from engine.calc.leases import LeaseRentCashflows, project_contract_rent
from engine.calc.ledger import (
    MonthlyLedger,
    assemble_ledger,
    assert_invariants,
    occupancy_series,
    occupied_area_series,
    rentable_area_series,
)
from engine.calc.recoveries import project_recoveries
from engine.calc.timeline import build_month_index
from engine.models import (
    ExpenseItem,
    ExpenseUnit,
    FreeRentProfile,
    Lease,
    PropertyModel,
    VacancyMethod,
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
    lease_rents: dict[str, LeaseRentCashflows]      # by tenant_name
    recoveries: dict[str, pd.Series]                # by tenant_name
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

    refuse(bool(model.absorption), "space absorption", "Phase 2")
    refuse(model.general_vacancy.method != VacancyMethod.none,
           "general vacancy", "Phase 2")
    refuse(model.credit_loss.method != VacancyMethod.none,
           "credit loss", "Phase 2")
    refuse(bool(model.miscellaneous_revenues or model.parking_revenues
                or model.storage_revenues), "property revenues", "Phase 2")
    refuse(bool(model.loans), "debt", "Phase 3")
    for lease in model.rent_roll:
        where = f"lease {lease.tenant_name!r}: "
        refuse(lease.percentage_rent is not None,
               where + "percentage rent", "Phase 2")
        refuse(bool(lease.miscellaneous_items),
               where + "miscellaneous tenant items", "Phase 2")
        refuse(lease.leasing_costs is not None,
               where + "contract TIs/LCs", "Phase 3")
    for item in model.expenses:
        refuse(item.unit == ExpenseUnit.pct_of_account,
               f"expense {item.name!r}: unit 'pct_of_account'", "Phase 2")


def _free_rent_profile(lease: Lease,
                       model: PropertyModel) -> Optional[FreeRentProfile]:
    if lease.free_rent is None or lease.free_rent.profile is None:
        return None
    by_name = {p.name: p for p in model.free_rent_profiles}
    return by_name[lease.free_rent.profile]  # ref validated by PropertyModel


def run_property(model: PropertyModel) -> RunResult:
    """Execute spec §4.1 passes 1-6 and return the assembled monthly ledger
    with the §9.3 pre-valuation invariants asserted."""
    _phase_guards(model)
    begin = model.property.analysis_begin

    # Pass 1: timeline. Pass 2 (inflation factors) happens inside each
    # projection call via the shared inflation module.
    months = build_month_index(begin, model.property.analysis_term_years)

    # Pass 3: lease resolution — Phase 1 is the contract term only.
    leases = model.rent_roll
    occupied = occupied_area_series(leases, months)
    rentable = rentable_area_series(model.area_measures, leases, months)
    occupancy = occupancy_series(occupied, rentable)
    available = (rentable - occupied).rename("available_area")

    # Pass 4: base rent, steps, CPI, free rent per lease.
    lease_rents = {
        lease.tenant_name: project_contract_rent(
            lease, months, begin, model.inflation,
            free_rent_profile=_free_rent_profile(lease, model),
        )
        for lease in leases
    }
    base_total = sum((r.base_rent for r in lease_rents.values()),
                     pd.Series(0.0, index=months))
    cpi_total = sum((r.cpi_adjustment for r in lease_rents.values()),
                    pd.Series(0.0, index=months))
    free_total = sum((r.free_rent for r in lease_rents.values()),
                     pd.Series(0.0, index=months))

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

    # Pass 6 + the %-of-EGR fixed point (spec §4.1 step 9, module
    # docstring): iterate fee → recoveries → EGR → fee to convergence,
    # then take the recoveries computed from the converged fee.
    pct_series = {item.name: pd.Series(0.0, index=months)
                  for item in pct_items}

    def recoveries_from(expense_series) -> dict[str, pd.Series]:
        return {
            lease.tenant_name: project_recoveries(
                lease, months, expense_series, rentable
            )
            for lease in leases
        }

    for _ in range(_MAX_FIXED_POINT_ROUNDS):
        expense_series = fixed_series + [
            (item, pct_series[item.name]) for item in pct_items
        ]
        recoveries = recoveries_from(expense_series)
        recovery_total = sum(recoveries.values(),
                             pd.Series(0.0, index=months))
        # Total PGR / EGR exactly as the ledger defines them; vacancy and
        # credit loss are zero in Phase 1, so EGR = Total PGR.
        pgr = base_total + free_total + cpi_total + recovery_total
        egr = pgr
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
            recoveries = recoveries_from(expense_series)
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
    )
    assert_invariants(
        ledger, analysis_begin=begin,
        fiscal_year_end_month=model.property.fiscal_year_end_month,
        occupied_area=occupied, rentable_area=rentable,
    )
    return RunResult(
        ledger=ledger, months=months, occupied_area=occupied,
        rentable_area=rentable, occupancy=occupancy,
        lease_rents=lease_rents, recoveries=recoveries,
        expense_series=expense_series,
    )
