"""Chart of Accounts tree and monthly ledger assembly (Phase 1; spec §2.3)
[AE pp. 197-210, 535-539].

The canonical ledger is one pandas DataFrame — Period[M] index from analysis
begin through analysis end + 12 months, one column per Cash Flow line — and
every annual/quarterly/fiscal view is an aggregation of it, never separately
computed (spec §2.3, Design principle "everything monthly").

Line names and order follow the ARGUS Cash Flow report [AE pp. 535-539] so
exports diff cleanly. Rollups are the report's own definitions [AE p. 538]:
Scheduled Base Rent is "the potential rent minus vacancy and free rent";
Effective Gross Revenue is potential gross revenue minus vacancy and credit
loss; Net Operating Income is EGR minus operating expenses; Cash Flow Before
Debt Service subtracts total leasing and capital costs from NOI. (Where the
spec §2.3 sketch orders lines differently, the manual governs —
DEVIATIONS.md §5.)

Sign convention: the ledger stores report signs — deductions (expenses,
free rent, vacancy, TI/LC) are negative, so every subtotal is a plain sum.
Expense series arrive positive from ``engine.calc.expenses`` and are negated
on posting; a negative capital ExpenseItem therefore posts as a capital
credit (DEVIATIONS.md §3, the Clorox Amortized CAM Revenue shape).

%-of-EGR expenses and the recovery fixed point are resolved by run.py's
ordered passes (spec §4.1 step 9) before assembly — this module posts
whatever series it is handed. Debt, resale, and the below-CFADS section are
Phase 3; non-operating expense detail — joined by the Phase 3 Step 2
acquisition and security-deposit lines — is carried below Cash Flow Before
Debt Service without further rollup until then. The engine never imports
UI code (Iron Rule 1).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from engine.calc.leases import LeaseRentCashflows, lease_term_periods
from engine.calc.timeline import analysis_year_of, fiscal_year_of
from engine.models import (
    AreaMeasures,
    ExpenseCategory,
    ExpenseItem,
    Lease,
    RentableAreaMode,
)

# ------------------------------------------------------------------ #
# Account names — the ARGUS Cash Flow lines (spec §2.3; [AE p. 538])  #
# ------------------------------------------------------------------ #

BASE_RENTAL_REVENUE = "Base Rental Revenue"
ABSORPTION_TURNOVER_VACANCY = "Absorption & Turnover Vacancy"
FREE_RENT = "Free Rent"
SCHEDULED_BASE_RENTAL_REVENUE = "Scheduled Base Rental Revenue"
CPI_ADJUSTMENT_REVENUE = "CPI & Other Adjustment Revenue"
PERCENTAGE_RENT = "Percentage Rent"
EXPENSE_RECOVERY_REVENUE = "Expense Recovery Revenue"
MISC_TENANT_REVENUE = "Miscellaneous Tenant Revenue"
PROPERTY_REVENUE = "Parking / Storage / Miscellaneous Property Revenue"
TOTAL_PGR = "Total Potential Gross Revenue"
GENERAL_VACANCY = "General Vacancy"
CREDIT_LOSS = "Credit Loss"
EGR = "Effective Gross Revenue"
TOTAL_OPERATING_EXPENSES = "Total Operating Expenses"
NOI = "Net Operating Income"
TENANT_IMPROVEMENTS = "Tenant Improvements"
LEASING_COMMISSIONS = "Leasing Commissions"
TOTAL_CAPITAL_COSTS = "Total Capital Costs"
CFBDS = "Cash Flow Before Debt Service"
#: Financing section (Phase 3 Step 3; spec §2.3 tree / §4.1 pass 12).
#: Debt Funding is a display line OUTSIDE the CFADS rollup — ARGUS's
#: "Show Loan Proceeds" defaults to No [AE p. 447] and spec §4.1 pass 14
#: builds leveraged IRR from "CFADS + equity at t0"; proceeds inside
#: CFADS would double-count against that equity.
DEBT_FUNDING = "Debt Funding"
INTEREST_EXPENSE = "Interest Expense"
PRINCIPAL_PAYMENTS = "Principal Payments"
LOAN_COSTS = "Loan Costs"
TOTAL_DEBT_SERVICE = "Total Debt Service"
CFADS = "Cash Flow After Debt Service"
#: Below-the-line lines (Phase 3 Step 2): posted after the financing
#: section, outside every rollup. The ARGUS Cash Flow report carries no
#: acquisition rows — the golden CSVs end at CFBDS; purchase feeds the
#: return metrics [AE p. 435] (spec §4.1 pass 14 consumes the price at
#: t0).
PURCHASE_PRICE = "Purchase Price"
CLOSING_COSTS = "Closing Costs"
SECURITY_DEPOSITS = "Security Deposits"
#: Resale (Phase 3 Step 4): net unleveraged proceeds post positive in
#: the resale month; the loan payoffs post negative beside them so the
#: leveraged net is the visible sum, not a silent netting. Below the
#: line, in no rollup (the ARGUS Cash Flow carries no resale row; the
#: PV analysis consumes it — spec §4.1 pass 14).
NET_RESALE_PROCEEDS = "Net Resale Proceeds"
LOAN_PAYOFF_AT_RESALE = "Loan Payoff at Resale"

#: Revenue detail lines summed into Total Potential Gross Revenue
#: (Scheduled Base already contains Base + A&T Vacancy + Free Rent).
_PGR_COMPONENTS = [
    SCHEDULED_BASE_RENTAL_REVENUE,
    CPI_ADJUSTMENT_REVENUE,
    PERCENTAGE_RENT,
    EXPENSE_RECOVERY_REVENUE,
    MISC_TENANT_REVENUE,
    PROPERTY_REVENUE,
]


@dataclass
class MonthlyLedger:
    """The canonical monthly ledger (spec §2.3): ``frame`` holds one column
    per Cash Flow line in report order; the column lists record which detail
    columns belong to each expense section (needed to re-derive the section
    totals when asserting invariants)."""

    frame: pd.DataFrame
    operating_columns: list[str] = field(default_factory=list)
    capital_columns: list[str] = field(default_factory=list)
    non_operating_columns: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ #
# Occupancy / area series (spec §3.2; §4.1 step 5)                    #
# ------------------------------------------------------------------ #

def occupied_area_series(leases: Iterable[Lease],
                         months: pd.PeriodIndex) -> pd.Series:
    """Occupied SF per month from contract terms only: the sum of each
    lease's area over its term. Always computed, never input (spec §3.2).
    For resolved chains (rollover) use :func:`occupied_area_from_chains`."""
    occupied = pd.Series(0.0, index=months, name="occupied_area")
    for lease in leases:
        start, end = lease_term_periods(lease)
        mask = (months >= start) & (months <= end)
        occupied[mask] += lease.area
    return occupied


def occupied_area_from_chains(chains: Iterable[list],
                              months: pd.PeriodIndex) -> pd.Series:
    """Occupied SF per month from resolved lease chains (Phase 2 Step 2).

    Each segment's occupied months carry its full area; downtime months
    preceding a speculative segment carry ``renewal_weight × area`` — the
    §4.2 partial-occupancy weighting (occupied drops by (1 − p) × area,
    the ARGUS default treating downtime area as fully vacant weighted by
    (1 − p)). Months after a chain ends (vacate/reabsorb) are vacant."""
    occupied = pd.Series(0.0, index=months, name="occupied_area")
    for segments in chains:
        for segment in segments:
            mask = (months >= segment.start) & (months <= segment.end)
            occupied[mask] += segment.area
            if segment.downtime_months:
                down = (months >= segment.downtime_start) & (months < segment.start)
                occupied[down] += segment.renewal_weight * segment.area
    return occupied


def rentable_area_series(area_measures: AreaMeasures, leases: Iterable[Lease],
                         months: pd.PeriodIndex) -> pd.Series:
    """Rentable SF per month per the §3.2 mode: ``derived`` = sum of rent
    roll areas ("Derive from tenants" [AE pp. 188-196]; absorption areas join
    in Phase 2), ``fixed`` = the override, ``schedule`` = a step function of
    the dated entries (months before the first entry use the first entry's
    area)."""
    mode = area_measures.rentable_area_mode
    if mode == RentableAreaMode.fixed:
        return pd.Series(float(area_measures.rentable_area_fixed),
                         index=months, name="rentable_area")
    if mode == RentableAreaMode.schedule:
        entries = sorted(area_measures.rentable_area_schedule,
                         key=lambda e: e.date)
        series = pd.Series(float(entries[0].area), index=months,
                           name="rentable_area")
        for entry in entries:
            start = pd.Period(entry.date, freq="M")
            series[months >= start] = float(entry.area)
        return series
    total = float(sum(lease.area for lease in leases))
    return pd.Series(total, index=months, name="rentable_area")


def occupancy_series(occupied: pd.Series, rentable: pd.Series) -> pd.Series:
    """Occupancy % per month = occupied area / rentable area (spec §3.2)."""
    return (occupied / rentable).rename("occupancy")


# ------------------------------------------------------------------ #
# Assembly (spec §4.1 steps 4-6 outputs → §2.3 accounts)              #
# ------------------------------------------------------------------ #

def _zeros(months: pd.PeriodIndex) -> pd.Series:
    return pd.Series(0.0, index=months)


def _optional(series: Optional[pd.Series], months: pd.PeriodIndex) -> pd.Series:
    if series is None:
        return _zeros(months)
    return series.reindex(months, fill_value=0.0).astype(float)


def assemble_ledger(months: pd.PeriodIndex, *,
                    lease_rents: Iterable[LeaseRentCashflows] = (),
                    recoveries: Iterable[pd.Series] = (),
                    expenses: Iterable[tuple[ExpenseItem, pd.Series]] = (),
                    absorption_vacancy: Optional[pd.Series] = None,
                    percentage_rent: Optional[pd.Series] = None,
                    misc_tenant_revenue: Optional[pd.Series] = None,
                    property_revenue: Optional[pd.Series] = None,
                    general_vacancy: Optional[pd.Series] = None,
                    credit_loss: Optional[pd.Series] = None,
                    tenant_improvements: Optional[pd.Series] = None,
                    leasing_commissions: Optional[pd.Series] = None,
                    debt_funding: Optional[pd.Series] = None,
                    interest_expense: Optional[pd.Series] = None,
                    principal_payments: Optional[pd.Series] = None,
                    loan_costs: Optional[pd.Series] = None,
                    purchase_price: Optional[pd.Series] = None,
                    closing_costs: Optional[pd.Series] = None,
                    security_deposits: Optional[pd.Series] = None,
                    net_resale_proceeds: Optional[pd.Series] = None,
                    loan_payoff_at_resale: Optional[pd.Series] = None,
                    ) -> MonthlyLedger:
    """Assemble per-lease and per-expense series into the canonical monthly
    ledger (spec §2.3).

    ``lease_rents``/``recoveries`` come from ``engine.calc.leases`` /
    ``engine.calc.recoveries`` per lease and are summed property-wide;
    ``expenses`` are (item, positive series) pairs from
    ``engine.calc.expenses`` — each posts negated to its own detail column
    (``item.account`` if set, else ``item.name``; same account accumulates)
    in its category's section. The optional series carry report sign already
    (deductions negative) and default to zero — Phase 1 callers omit them
    (absorption, vacancy/credit loss, TI/LC are Phase 2/3).

    Rollups per the Cash Flow report [AE p. 538]: Scheduled Base = Base +
    A&T Vacancy + Free Rent; Total PGR sums the revenue lines; EGR = PGR +
    vacancy + credit loss; NOI = EGR + operating expenses; CFBDS = NOI +
    TI + LC + capital lines. All plain sums under the report-sign
    convention.
    """
    base = _zeros(months)
    cpi = _zeros(months)
    free = _zeros(months)
    for rents in lease_rents:
        base += rents.base_rent.reindex(months, fill_value=0.0)
        cpi += rents.cpi_adjustment.reindex(months, fill_value=0.0)
        free += rents.free_rent.reindex(months, fill_value=0.0)

    recovery = _zeros(months)
    for series in recoveries:
        recovery += series.reindex(months, fill_value=0.0)

    sections: dict[ExpenseCategory, dict[str, pd.Series]] = {
        ExpenseCategory.operating: {},
        ExpenseCategory.capital: {},
        ExpenseCategory.non_operating: {},
    }
    owner: dict[str, ExpenseCategory] = {}
    for item, series in expenses:
        name = item.account or item.name
        if owner.setdefault(name, item.category) != item.category:
            raise ValueError(
                f"expense account {name!r} appears in more than one category "
                f"({owner[name].value} and {item.category.value})"
            )
        section = sections[item.category]
        posted = -series.reindex(months, fill_value=0.0)
        section[name] = section.get(name, _zeros(months)) + posted

    operating = sections[ExpenseCategory.operating]
    capital = sections[ExpenseCategory.capital]
    non_operating = sections[ExpenseCategory.non_operating]

    columns: dict[str, pd.Series] = {}
    columns[BASE_RENTAL_REVENUE] = base
    columns[ABSORPTION_TURNOVER_VACANCY] = _optional(absorption_vacancy, months)
    columns[FREE_RENT] = free
    columns[SCHEDULED_BASE_RENTAL_REVENUE] = (
        columns[BASE_RENTAL_REVENUE]
        + columns[ABSORPTION_TURNOVER_VACANCY]
        + columns[FREE_RENT]
    )
    columns[CPI_ADJUSTMENT_REVENUE] = cpi
    columns[PERCENTAGE_RENT] = _optional(percentage_rent, months)
    columns[EXPENSE_RECOVERY_REVENUE] = recovery
    columns[MISC_TENANT_REVENUE] = _optional(misc_tenant_revenue, months)
    columns[PROPERTY_REVENUE] = _optional(property_revenue, months)
    columns[TOTAL_PGR] = sum(columns[name] for name in _PGR_COMPONENTS)
    columns[GENERAL_VACANCY] = _optional(general_vacancy, months)
    columns[CREDIT_LOSS] = _optional(credit_loss, months)
    columns[EGR] = (
        columns[TOTAL_PGR] + columns[GENERAL_VACANCY] + columns[CREDIT_LOSS]
    )
    for name, series in operating.items():
        columns[name] = series
    columns[TOTAL_OPERATING_EXPENSES] = (
        sum(operating.values()) if operating else _zeros(months)
    )
    columns[NOI] = columns[EGR] + columns[TOTAL_OPERATING_EXPENSES]
    columns[TENANT_IMPROVEMENTS] = _optional(tenant_improvements, months)
    columns[LEASING_COMMISSIONS] = _optional(leasing_commissions, months)
    for name, series in capital.items():
        columns[name] = series
    columns[TOTAL_CAPITAL_COSTS] = (
        columns[TENANT_IMPROVEMENTS] + columns[LEASING_COMMISSIONS]
        + (sum(capital.values()) if capital else _zeros(months))
    )
    columns[CFBDS] = columns[NOI] + columns[TOTAL_CAPITAL_COSTS]
    # Financing section (Phase 3 Step 3; spec §2.3 tree). Debt Funding
    # is display-only — outside Total Debt Service and CFADS (see the
    # constants note above). CFADS = CFBDS + Total Debt Service.
    columns[DEBT_FUNDING] = _optional(debt_funding, months)
    columns[INTEREST_EXPENSE] = _optional(interest_expense, months)
    columns[PRINCIPAL_PAYMENTS] = _optional(principal_payments, months)
    columns[LOAN_COSTS] = _optional(loan_costs, months)
    columns[TOTAL_DEBT_SERVICE] = (
        columns[INTEREST_EXPENSE] + columns[PRINCIPAL_PAYMENTS]
        + columns[LOAN_COSTS]
    )
    columns[CFADS] = columns[CFBDS] + columns[TOTAL_DEBT_SERVICE]
    # Below the line (Phase 3 Step 2): acquisition flows and security
    # deposits post after the financing section, in no rollup — the Cash
    # Flow report has no acquisition rows and purchase feeds the return
    # metrics [AE p. 435]. Signs arrive report-ready (outflows negative,
    # deposit collections positive / refunds negative).
    columns[PURCHASE_PRICE] = _optional(purchase_price, months)
    columns[CLOSING_COSTS] = _optional(closing_costs, months)
    columns[SECURITY_DEPOSITS] = _optional(security_deposits, months)
    columns[NET_RESALE_PROCEEDS] = _optional(net_resale_proceeds, months)
    columns[LOAN_PAYOFF_AT_RESALE] = _optional(loan_payoff_at_resale, months)
    for name, series in non_operating.items():
        columns[name] = series

    frame = pd.DataFrame(columns, index=months)
    return MonthlyLedger(
        frame=frame,
        operating_columns=list(operating),
        capital_columns=list(capital),
        non_operating_columns=list(non_operating),
    )


# ------------------------------------------------------------------ #
# Aggregation views (spec §2.3: aggregations of the monthly ledger,   #
# never separately computed)                                          #
# ------------------------------------------------------------------ #

def to_annual(frame: pd.DataFrame, analysis_begin: dt.date) -> pd.DataFrame:
    """Analysis-year view: 12-month blocks from the analysis begin month,
    rows labeled 1..N (spec §3.1). The resale look-forward months form the
    final year."""
    labels = [analysis_year_of(analysis_begin, p) for p in frame.index]
    return frame.groupby(labels).sum()


def to_quarterly(frame: pd.DataFrame) -> pd.DataFrame:
    """Calendar-quarter view (Period[Q] rows)."""
    return frame.groupby(frame.index.asfreq("Q")).sum()


def to_fiscal_annual(frame: pd.DataFrame,
                     fiscal_year_end_month: int = 12) -> pd.DataFrame:
    """Fiscal-year view, rows labeled by the calendar year the fiscal year
    ends in (spec §3.1 ``fiscal_year_end_month``) — the basis on which the
    OM goldens assert (spec §9.1). First/last groups may be partial years
    when the analysis begin month doesn't open a fiscal year."""
    labels = [fiscal_year_of(p, fiscal_year_end_month) for p in frame.index]
    return frame.groupby(labels).sum()


# ------------------------------------------------------------------ #
# Property-level invariants (spec §9.3, pre-valuation subset)         #
# ------------------------------------------------------------------ #

def assert_invariants(ledger: MonthlyLedger, *, analysis_begin: dt.date,
                      fiscal_year_end_month: int = 12,
                      occupied_area: Optional[pd.Series] = None,
                      rentable_area: Optional[pd.Series] = None) -> None:
    """Assert the §9.3 invariants that apply before valuation exists; raise
    ``ValueError`` naming the first violated identity. Called on every calc
    run (CLAUDE.md Conventions). Debt and PV/IRR self-consistency join in
    Phase 3.
    """
    frame = ledger.frame

    def close(a, b) -> bool:
        return bool(np.allclose(np.asarray(a, dtype=float),
                                np.asarray(b, dtype=float), atol=1e-6))

    identities = [
        (f"{SCHEDULED_BASE_RENTAL_REVENUE} = {BASE_RENTAL_REVENUE} + "
         f"{ABSORPTION_TURNOVER_VACANCY} + {FREE_RENT} [AE p. 538]",
         frame[SCHEDULED_BASE_RENTAL_REVENUE],
         frame[BASE_RENTAL_REVENUE] + frame[ABSORPTION_TURNOVER_VACANCY]
         + frame[FREE_RENT]),
        (f"{TOTAL_PGR} = sum of revenue lines",
         frame[TOTAL_PGR],
         sum(frame[name] for name in _PGR_COMPONENTS)),
        (f"{EGR} = {TOTAL_PGR} + {GENERAL_VACANCY} + {CREDIT_LOSS} [AE p. 538]",
         frame[EGR],
         frame[TOTAL_PGR] + frame[GENERAL_VACANCY] + frame[CREDIT_LOSS]),
        (f"{TOTAL_OPERATING_EXPENSES} = sum of operating expense lines",
         frame[TOTAL_OPERATING_EXPENSES],
         sum((frame[name] for name in ledger.operating_columns),
             pd.Series(0.0, index=frame.index))),
        (f"{NOI} = {EGR} + {TOTAL_OPERATING_EXPENSES} [AE p. 539]",
         frame[NOI], frame[EGR] + frame[TOTAL_OPERATING_EXPENSES]),
        (f"{TOTAL_CAPITAL_COSTS} = {TENANT_IMPROVEMENTS} + "
         f"{LEASING_COMMISSIONS} + capital expense lines",
         frame[TOTAL_CAPITAL_COSTS],
         frame[TENANT_IMPROVEMENTS] + frame[LEASING_COMMISSIONS]
         + sum((frame[name] for name in ledger.capital_columns),
               pd.Series(0.0, index=frame.index))),
        (f"{CFBDS} = {NOI} + {TOTAL_CAPITAL_COSTS} [AE p. 539]",
         frame[CFBDS], frame[NOI] + frame[TOTAL_CAPITAL_COSTS]),
    ]
    for label, actual, expected in identities:
        if not close(actual, expected):
            raise ValueError(f"ledger invariant violated: {label}")

    if occupied_area is not None and rentable_area is not None:
        excess = occupied_area - rentable_area.reindex(occupied_area.index)
        if (excess > 1e-6).any():
            month = excess[excess > 1e-6].index[0]
            raise ValueError(
                f"invariant violated: occupied area exceeds rentable area "
                f"in {month} (spec §9.3)"
            )

    monthly_totals = frame.sum()
    for view_name, view in [
        ("annual", to_annual(frame, analysis_begin)),
        ("quarterly", to_quarterly(frame)),
        ("fiscal", to_fiscal_annual(frame, fiscal_year_end_month)),
    ]:
        if not close(view.sum(), monthly_totals):
            raise ValueError(
                f"invariant violated: sum(monthly) != sum({view_name}) "
                f"aggregation (spec §9.3)"
            )
