"""Property resale (Phase 3 Step 4; spec §3.18 resale block / §4.1
pass 13) [AE pp. 464-471].

**EXTERNALLY UNVALIDATED:** no golden populates ``valuation`` and none
ever will — no OM publishes a valuation result (verified 2026-07-11).
This module is proven by the manual's stated definitions and formulas
(Iron Rule 3 worked-example tests) and engineered tests only, the same
standing as debt (DEVIATIONS.md §19).

Method definitions (Part A adjudications):

- ``cap_noi_forward_12`` — "CAP NOI (12 Months After Sale): Capitalize
  net operating income for twelve months after the sale date"
  [AE p. 465]. The window is resale month +1..+12, always available:
  the ledger timeline extends 12 months past analysis end (spec §2.3)
  and the resale date is capped at analysis end.
- ``cap_noi_current_year`` — "CAP NOI (Year of Sale)" [AE p. 465]; the
  "year of sale" is a reporting-year bucket ("the resale year"
  [AE p. 469]), implemented as the analysis year (12-month block from
  analysis begin) containing the resale month.
- ``gross_value_less_costs`` — the schema's name for "CAP Effective
  Gross Rents (12 Months After Sale): Capitalize net effective gross
  rents (effective gross revenue − recoveries) for twelve months after
  the sale date" [AE p. 465] — the only other cap-rate-required method
  in the manual's list [AE p. 467 note]. It differs from the CAP NOI
  methods in the income basis, not the inputs. Inferred mapping —
  DEVIATIONS.md §19.
- ``fixed_amount`` — "Enter Sale Price ... which will be used as the
  gross sale price AND net sale price" [AE p. 465]: uniquely, no
  selling costs or adjustments apply; populating them with this method
  is refused loudly rather than silently ignored.
- ``pct_increase_over_price`` — "Inflate Purchase Price" [AE p. 465],
  narrowed to the schema's TOTAL percent increase over the purchase
  price (not ARGUS's annual inflation field); requires a purchase.

Adjustment cascade (the order the manual states for Capitalization
Valuation [AE p. 465] — value "before adjustments", adjustments produce
"the gross sale price", selling costs subtract from that): capitalized
value → NOI adjustments (below) → ± ``adjustment_amounts`` [AE p. 471]
→ gross sale price → − selling costs (pct × gross) → net unleveraged →
− loan payoffs (each loan's ending balance in the resale month, Step
3's series) → net leveraged.

NOI adjustments: ``exclude_capital=True`` uses the ledger's NOI as-is
(the ledger NOI already excludes TI/LC/capex — CFBDS subtracts them
after NOI); ``False`` adds the window's Total Capital Costs into the
basis, the all-or-nothing form of the manual's Deductions grid
[AE pp. 470-471]. ``stabilize_occupancy`` applies the printed formula
"NOI × Gross Up % / Average Occupancy %" [AE p. 469] over the method's
own window, using the run's occupancy series — the ledger is never
recomputed (spec §4.1 note).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from engine.models import PropertyModel
from engine.models.valuation import Resale, ResaleMethod

from .debt import LoanSchedule
from .ledger import (
    EGR,
    EXPENSE_RECOVERY_REVENUE,
    NOI,
    TOTAL_CAPITAL_COSTS,
    MonthlyLedger,
)
from .timeline import snap_to_month_start


@dataclass
class ResaleResult:
    """The full resale calculation cascade (spec §7 report 21 detail;
    "no silent numbers")."""

    method: ResaleMethod
    resale_month: pd.Period
    noi_window: Optional[pd.PeriodIndex]      # None for the no-income methods
    income_basis: Optional[float]             # window NOI / net effective rents
    capital_adjustment: float                 # 0 unless exclude_capital=False
    occupancy_factor: float                   # 1.0 unless stabilized
    adjusted_basis: Optional[float]           # basis × factor + capital
    base_value: float                         # capitalized / fixed / inflated
    adjustments: list[tuple[str, float]]      # [AE p. 471], before selling costs
    gross_sale_price: float
    selling_costs: float
    net_unleveraged: float
    loan_payoffs: dict[str, float]            # by loan name, resale-month balance
    net_leveraged: float
    applied_to_cash_flow: bool
    proceeds_series: pd.Series = field(repr=False, default=None)  # + net unleveraged
    payoff_series: pd.Series = field(repr=False, default=None)    # − payoffs


def analysis_end_month(months: pd.PeriodIndex) -> pd.Period:
    """The true final analysis month — the timeline's last 12 months are
    the resale look-forward (spec §2.3), never part of the analysis."""
    return months[len(months) - 13]


def _resale_month(resale: Resale, months: pd.PeriodIndex) -> pd.Period:
    end = analysis_end_month(months)
    if resale.resale_date is None:
        return end
    month = pd.Period(snap_to_month_start(resale.resale_date), freq="M")
    if month < months[0] or month > end:
        raise ValueError(
            f"resale date {month} is outside the analysis window "
            f"({months[0]}..{end}; the final 12 timeline months are the "
            "resale look-forward, not saleable months)"
        )
    return month


def _noi_window(resale: Resale, resale_month: pd.Period,
                months: pd.PeriodIndex) -> Optional[pd.PeriodIndex]:
    if resale.method in (ResaleMethod.cap_noi_forward_12,
                         ResaleMethod.gross_value_less_costs):
        return pd.period_range(resale_month + 1, resale_month + 12, freq="M")
    if resale.method == ResaleMethod.cap_noi_current_year:
        offset = ((resale_month.year - months[0].year) * 12
                  + (resale_month.month - months[0].month))
        start = months[0] + (offset // 12) * 12
        return pd.period_range(start, start + 11, freq="M")
    return None


def compute_resale(resale: Resale, ledger: MonthlyLedger,
                   months: pd.PeriodIndex, occupancy: pd.Series,
                   model: PropertyModel,
                   loan_schedules: list[LoanSchedule]) -> ResaleResult:
    """Execute the resale cascade (module docstring) against the
    already-assembled ledger — valuation never recomputes it (spec §4.1)."""
    frame = ledger.frame
    resale_month = _resale_month(resale, months)
    window = _noi_window(resale, resale_month, months)

    income_basis = None
    capital_adjustment = 0.0
    occupancy_factor = 1.0
    adjusted_basis = None

    if resale.method == ResaleMethod.fixed_amount:
        if resale.selling_costs_pct or resale.adjustment_amounts:
            raise ValueError(
                "resale method 'fixed_amount' is the manual's Enter Sale "
                "Price: the amount is both the gross AND the net sale "
                "price [AE p. 465] — selling_costs_pct and "
                "adjustment_amounts cannot apply; remove them or use a "
                "cap method"
            )
        base_value = float(resale.fixed_amount)
    elif resale.method == ResaleMethod.pct_increase_over_price:
        if model.purchase is None or model.purchase.price is None:
            raise ValueError(
                "resale method 'pct_increase_over_price' inflates the "
                "purchase price [AE p. 465]; the model has no purchase "
                "price"
            )
        base_value = model.purchase.price * (1.0 + resale.pct_increase / 100.0)
    else:
        if resale.method == ResaleMethod.gross_value_less_costs:
            # net effective gross rents = EGR − recoveries [AE p. 465]
            income_basis = float(
                (frame[EGR] - frame[EXPENSE_RECOVERY_REVENUE])[window].sum()
            )
        else:
            income_basis = float(frame[NOI][window].sum())
        if not resale.noi_adjustments.exclude_capital:
            # include the window's capital costs in the basis — the
            # all-or-nothing Deductions grid [AE pp. 470-471]
            capital_adjustment = float(frame[TOTAL_CAPITAL_COSTS][window].sum())
        stabilize = resale.noi_adjustments.stabilize_occupancy
        if stabilize is not None:
            average = float(occupancy[window].mean())
            if average <= 0.0:
                raise ValueError(
                    "stabilize_occupancy: the average occupancy over the "
                    "resale window is zero — the [AE p. 469] ratio is "
                    "undefined"
                )
            occupancy_factor = (stabilize.occupancy_pct / 100.0) / average
        adjusted_basis = income_basis * occupancy_factor + capital_adjustment
        base_value = adjusted_basis / (resale.exit_cap_rate / 100.0)

    if resale.method == ResaleMethod.fixed_amount:
        adjustments: list[tuple[str, float]] = []
        gross = base_value
        selling = 0.0
    else:
        adjustments = [(a.name, a.amount) for a in resale.adjustment_amounts]
        gross = base_value + sum(amount for _, amount in adjustments)
        selling = resale.selling_costs_pct / 100.0 * gross
    net_unleveraged = gross - selling

    payoffs = {
        s.loan.name: float(s.balance[resale_month])
        for s in loan_schedules
    }
    net_leveraged = net_unleveraged - sum(payoffs.values())

    proceeds = pd.Series(0.0, index=months, name="net_resale_proceeds")
    payoff_series = pd.Series(0.0, index=months, name="loan_payoff_at_resale")
    if resale.apply_resale_to_cash_flow:
        proceeds[resale_month] = net_unleveraged
        payoff_series[resale_month] = -sum(payoffs.values())

    return ResaleResult(
        method=resale.method, resale_month=resale_month, noi_window=window,
        income_basis=income_basis, capital_adjustment=capital_adjustment,
        occupancy_factor=occupancy_factor, adjusted_basis=adjusted_basis,
        base_value=base_value, adjustments=adjustments,
        gross_sale_price=gross, selling_costs=selling,
        net_unleveraged=net_unleveraged, loan_payoffs=payoffs,
        net_leveraged=net_leveraged,
        applied_to_cash_flow=resale.apply_resale_to_cash_flow,
        proceeds_series=proceeds, payoff_series=payoff_series,
    )


def assert_resale_invariants(result: ResaleResult,
                             loan_schedules: list[LoanSchedule]) -> None:
    """§9.3 payoff-at-resale, standing on every run with both a resale
    and loans: each payoff equals that loan's outstanding (month-end)
    balance in the resale month per Step 3's schedule, and leveraged net
    proceeds = unleveraged net − the sum of those balances."""
    for schedule in loan_schedules:
        balance = float(schedule.balance[result.resale_month])
        payoff = result.loan_payoffs[schedule.loan.name]
        if abs(payoff - balance) > 1e-6:
            raise ValueError(
                f"resale payoff for loan {schedule.loan.name!r} "
                f"({payoff:,.2f}) is not the outstanding balance at "
                f"{result.resale_month} ({balance:,.2f})"
            )
    identity = result.net_unleveraged - sum(result.loan_payoffs.values())
    if abs(result.net_leveraged - identity) > 1e-6:
        raise ValueError(
            "leveraged net resale proceeds do not equal unleveraged net "
            "proceeds minus the outstanding loan balances"
        )
