"""Debt engine: per-loan amortization schedules and the ledger's
financing section (Phase 3 Step 3; spec §3.17 / §4.1 pass 12)
[AE pp. 438-449].

**Validation path (say it plainly):** no golden fixture populates
``loans`` and none will — this module is proven by the manual's stated
conventions, closed-form worked-example tests (Iron Rule 3), and the
**owner's bank-amortization-calculator hand-check**, which for debt IS
the designed validation path (NEXT_STEPS_TO_GATE3.md Step 0), not a
placeholder pending future data. Standard mortgage math is universal and
externally checkable in a way OM cash flows are not.

Conventions (Part A adjudications — DEVIATIONS.md §18):

- **Monthly rate = annual / 12** — the manual's default Calc Method
  ("12 Months: The monthly interest rate is the annual interest rate
  divided by twelve" [AE p. 443]); the closed form
  ``payment = P × r / (1 − (1+r)^−n)`` is spec §3.17's normative
  statement (the manual never prints it). The 360-day and semi-annual
  Calc Methods are schema-absent.
- **Funding** defaults to the purchase date if a purchase exists, else
  the analysis begin ([AE p. 442] Loan Date default; Step 2's
  ``Purchase.date`` default is also analysis begin). Existing loans may
  fund before the analysis window ("modeled back to their original
  start date" [AE p. 442]) — the schedule computes from funding and
  only in-window months post to the ledger. Payments run from the month
  after funding through maturity; the funding month itself posts the
  proceeds.
- **Interest-only** [AE p. 438 "Interest Only" loan type;
  ``interest_only_months``]: interest-only payments, principal
  untouched; when amortization begins, the payment levels to amortize
  the then-current balance over the remaining amortization horizon.
- **Balloon** ("amortized over N years, due in M months"): the payment
  is sized to the full N-year amortization; the balance remaining at
  maturity posts as a balloon principal repayment in the maturity month
  ([AE p. 438] "Quick Start — Balloon Payments"). ``interest_only``
  amortization = the whole principal balloons.
- **Floating** = index YearRate schedule + spread (spec §3.17). The
  manual's mechanism is a varying-rate Interest Rate Editor
  [AE pp. 441-442] and it is silent on payment recomputation; chosen
  convention: **on each effective-rate change the payment re-levels to
  amortize the current balance over the remaining amortization horizon
  at the new rate** — the [AE p. 444] "recalculate ... over the same
  term" behavior applied to rate changes, and the only convention under
  which a floating fully-amortizing loan reaches zero at maturity.
  ``YearRate.year`` is read per the model's ``inflation.timing_basis``,
  like every other YearRate schedule in the engine.
- **Additional principal** [AE p. 444]: the manual offers Recalc Pmt
  Yes/No; the schema has no toggle, so the **"No" behavior** is modeled
  — originally scheduled payments continue, payoff shortens. Paydowns
  clamp to the outstanding balance; a paid-off loan posts nothing
  further (its remaining term, and any balloon, vanish).
- **Loan costs** [AE pp. 445-446]: ``points_pct`` × loan amount +
  ``fees``, posting to the Loan Costs line **in the financing section**
  ("These costs will appear on the Cash Flow report in the Financing
  section" [AE p. 446]) — not with Step 2's acquisition lines.
  ``expense`` = lump sum at funding (or ``timing``); ``amortize`` =
  straight-line over the loan term (manual silent on the schedule;
  spec §3.17's amortize-or-expense toggle).
- **Debt Funding is a display line outside the CFADS rollup:** ARGUS's
  "Show Loan Proceeds" defaults to No [AE p. 447], and spec §4.1 pass
  14 builds leveraged IRR from "CFADS + equity at t0" — proceeds inside
  CFADS would double-count against that equity. CFADS = CFBDS + Total
  Debt Service (interest + principal + loan costs).

Invariants (§9.3, asserted on every run with loans): opening balance
rolls from the prior ending balance; balances never go negative;
interest-only months amortize nothing; a fully-amortizing loan's balloon
is ~0 at maturity.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from engine.models import Inflation, Loan, Purchase, TimingBasis
from engine.models.investment import (
    FloatingRate,
    LoanAmountBasis,
    LoanCostHandling,
)

from .inflation import rate_for_year
from .timeline import snap_to_month_start

#: Fully-amortizing loans must land within a cent of zero at maturity.
_ZERO_BALANCE_TOLERANCE = 0.01


@dataclass
class LoanSchedule:
    """One loan's full monthly schedule (spec §7 report 20 detail;
    "no silent numbers"). ``frame`` covers every loan month — funding
    through maturity, in- or out-of-window — with columns
    opening / rate / payment / interest / principal /
    additional_principal / ending. The ledger-aligned series carry
    report signs and only in-window months."""

    loan: Loan
    principal0: float
    funding_month: pd.Period
    maturity_month: pd.Period
    frame: pd.DataFrame
    balloon: float               # balance repaid at maturity (0 if none)
    funding: pd.Series           # + proceeds at funding month
    interest: pd.Series          # − interest paid
    principal: pd.Series         # − scheduled + additional + balloon
    loan_costs: pd.Series        # − points/fees per handling
    balance: pd.Series           # outstanding at each ledger month end


def level_payment(principal: float, monthly_rate: float, months: int) -> float:
    """``P × r / (1 − (1+r)^−n)`` (spec §3.17; r = annual/12 per the
    [AE p. 443] default Calc Method). Zero-rate loans divide evenly."""
    if months <= 0:
        raise ValueError("level payment needs a positive month count")
    if monthly_rate == 0.0:
        return principal / months
    return principal * monthly_rate / (1.0 - (1.0 + monthly_rate) ** -months)


def _month(date: dt.date) -> pd.Period:
    return pd.Period(snap_to_month_start(date), freq="M")


def _principal0(loan: Loan, purchase: Optional[Purchase]) -> float:
    basis = loan.amount.basis
    if basis == LoanAmountBasis.amount:
        return loan.amount.value
    if basis == LoanAmountBasis.pct_of_price:
        if purchase is None or purchase.price is None:
            raise ValueError(
                f"loan {loan.name!r}: pct_of_price needs a purchase price"
            )
        return purchase.price * loan.amount.value / 100.0
    raise NotImplementedError(
        f"loan {loan.name!r}: amount basis 'pct_of_value' (\"% of Adopted "
        "Valuation\" [AE p. 438]) is not implemented. Step 5 (PV/IRR) built "
        "the valuation this would size off, but a loan sized off the derived "
        "property value is an OPEN OWNER SCOPE DECISION (DEVIATIONS.md §20): "
        "debt is computed at pass 12 and valuation at pass 14, so a "
        "value-sized loan needs the (unleveraged) valuation reordered before "
        "debt — added architecture no golden or current deal needs. Use an "
        "amount or pct_of_price."
    )


def _annual_rate(loan: Loan, period: pd.Period, analysis_begin: dt.date,
                 timing_basis: TimingBasis) -> float:
    """Effective annual rate (percent) in force during ``period``:
    fixed loans are constant; floating = index (carry-forward YearRate
    schedule [AE pp. 441-442]) + spread, year keyed per the model's
    timing basis."""
    if not isinstance(loan.rate, FloatingRate):
        return float(loan.rate)
    if timing_basis == TimingBasis.calendar_year:
        year = period.year
    else:
        offset = ((period.year - analysis_begin.year) * 12
                  + (period.month - analysis_begin.month))
        year = max(offset, 0) // 12 + 1
    return rate_for_year(loan.rate.index, year) + loan.rate.spread


def build_loan_schedule(loan: Loan, months: pd.PeriodIndex,
                        analysis_begin: dt.date,
                        purchase: Optional[Purchase],
                        inflation: Optional[Inflation]) -> LoanSchedule:
    """One loan's amortization schedule from funding through maturity
    (spec §4.1 pass 12) [AE pp. 438-446], plus its ledger-aligned
    posting series."""
    principal0 = _principal0(loan, purchase)
    if loan.funding_date is not None:
        funding = _month(loan.funding_date)
    elif purchase is not None and purchase.date is not None:
        funding = _month(purchase.date)
    else:
        funding = _month(analysis_begin)
    if funding > months[-1]:
        raise ValueError(
            f"loan {loan.name!r}: funding month {funding} is after the "
            f"analysis timeline ends ({months[-1]})"
        )

    if loan.term_months is not None:
        term = loan.term_months
    else:
        maturity = _month(loan.maturity_date)
        term = ((maturity.year - funding.year) * 12
                + (maturity.month - funding.month))
        if term < 1:
            raise ValueError(
                f"loan {loan.name!r}: maturity {maturity} is not after "
                f"funding {funding}"
            )
    maturity = funding + term

    if loan.amortization == "interest_only":
        io_months = term
        horizon = 0
    else:
        io_months = min(loan.interest_only_months, term)
        if loan.amortization == "fully_amortizing":
            horizon = term - io_months
        else:  # int years: "amortized over N years, due in M months"
            horizon = int(loan.amortization) * 12
    amort_start = funding + io_months + 1  # first amortizing payment month
    amort_end = funding + io_months + horizon  # last month of the horizon

    timing_basis = (inflation.timing_basis if inflation is not None
                    else TimingBasis.analysis_year)
    # Additional principal only applies during the loan's payment window
    # (funding+1 .. maturity). A payment dated outside it would be
    # silently dropped by the schedule loop, so refuse loudly instead
    # (no silent numbers — Codex finding #11).
    additional = {}
    for extra in loan.additional_principal:
        month = _month(extra.date)
        if month < funding + 1 or month > maturity:
            raise ValueError(
                f"loan {loan.name!r}: additional principal dated {month} "
                f"is outside the loan's active window "
                f"({funding + 1}..{maturity}); it would never be applied"
            )
        additional[month] = additional.get(month, 0.0) + extra.amount

    loan_months = pd.period_range(funding + 1, maturity, freq="M")
    rows = []
    balance = principal0
    payment = 0.0
    prior_rate = None
    balloon = 0.0
    for m in loan_months:
        annual = _annual_rate(loan, m, analysis_begin, timing_basis)
        r = annual / 100.0 / 12.0  # [AE p. 443] "12 Months" Calc Method
        opening = balance
        if opening <= _ZERO_BALANCE_TOLERANCE:
            # paid off early (additional principal) — nothing further
            rows.append((m, opening, annual, 0.0, 0.0, 0.0, 0.0, opening))
            prior_rate = annual
            continue
        interest = opening * r
        if m <= funding + io_months:
            scheduled_principal = 0.0
            pay = interest
        else:
            if m == amort_start or (prior_rate is not None
                                    and annual != prior_rate):
                remaining = (amort_end - m).n + 1  # re-level [AE p. 444]
                payment = level_payment(opening, r, remaining)
            scheduled_principal = min(payment - interest, opening)
            pay = interest + scheduled_principal
        extra = min(additional.get(m, 0.0), opening - scheduled_principal)
        ending = opening - scheduled_principal - extra
        if m == maturity and ending > _ZERO_BALANCE_TOLERANCE:
            balloon = ending  # balloon repayment [AE p. 438]
            ending = 0.0
        rows.append((m, opening, annual, pay, interest,
                     scheduled_principal, extra, ending))
        balance = ending
        prior_rate = annual

    frame = pd.DataFrame(
        rows, columns=["month", "opening", "rate", "payment", "interest",
                       "principal", "additional_principal", "ending"],
    ).set_index("month")

    # --- ledger-aligned series (in-window months only, report signs) ---
    def zeros(name):
        return pd.Series(0.0, index=months, name=name)

    funding_series = zeros("debt_funding")
    if funding >= months[0]:
        funding_series[funding] += principal0
    interest_series = zeros("interest_expense")
    principal_series = zeros("principal_payments")
    in_window = frame.index[(frame.index >= months[0])
                            & (frame.index <= months[-1])]
    for m in in_window:
        interest_series[m] -= float(frame.loc[m, "interest"])
        principal_series[m] -= float(frame.loc[m, "principal"]
                                     + frame.loc[m, "additional_principal"])
    if months[0] <= maturity <= months[-1]:
        principal_series[maturity] -= balloon

    # Outstanding balance at each ledger month end: the funding month
    # carries the full draw; schedule months carry their ending balance;
    # pre-funding and post-maturity months are zero; a pre-window funding
    # carries its balance into the window.
    balance_series = zeros("loan_balance")
    if funding >= months[0]:
        balance_series[funding] = principal0
    balance_series[in_window] = frame.loc[in_window, "ending"].astype(float)
    if funding < months[0] and len(in_window):
        first = in_window[0]
        balance_series[balance_series.index < first] = float(
            frame.loc[first, "opening"])

    costs_series = zeros("loan_costs")
    if loan.loan_costs is not None:
        cost = (loan.loan_costs.points_pct / 100.0 * principal0
                + loan.loan_costs.fees)
        if cost:
            start = (_month(loan.loan_costs.timing)
                     if loan.loan_costs.timing is not None else funding)
            if loan.loan_costs.handling == LoanCostHandling.expense:
                if months[0] <= start <= months[-1]:
                    costs_series[start] -= cost
            else:  # amortize: straight-line over the loan term
                monthly = cost / term
                for m in pd.period_range(start + 1, start + term, freq="M"):
                    if months[0] <= m <= months[-1]:
                        costs_series[m] -= monthly

    return LoanSchedule(
        loan=loan, principal0=principal0, funding_month=funding,
        maturity_month=maturity, frame=frame, balloon=balloon,
        funding=funding_series, interest=interest_series,
        principal=principal_series, loan_costs=costs_series,
        balance=balance_series,
    )


def assert_debt_invariants(schedule: LoanSchedule) -> None:
    """§9.3 debt invariants, asserted on every run with loans present:
    the ending balance rolls month to month; balances never go negative;
    interest-only months amortize nothing; a fully-amortizing loan ends
    within a cent of zero at maturity. Raises ``ValueError`` naming the
    first violated identity."""
    frame = schedule.frame
    name = schedule.loan.name
    prior_ending = frame["ending"].shift(1)
    prior_ending.iloc[0] = schedule.principal0
    drift = (frame["opening"] - prior_ending).abs().max()
    if drift > 1e-6:
        raise ValueError(
            f"loan {name!r}: opening balance does not roll from the prior "
            f"ending balance (max drift {drift})"
        )
    if (frame["ending"] < -1e-6).any():
        raise ValueError(f"loan {name!r}: negative balance in the schedule")
    if schedule.loan.amortization == "interest_only":
        io_end = schedule.maturity_month - 1  # balloon month may amortize
    else:
        io_end = schedule.funding_month + schedule.loan.interest_only_months
    io_rows = frame[frame.index <= io_end]
    if (io_rows["principal"].abs() > 1e-9).any():
        raise ValueError(
            f"loan {name!r}: interest-only months amortized principal"
        )
    if (schedule.loan.amortization == "fully_amortizing"
            and schedule.balloon > _ZERO_BALANCE_TOLERANCE):
        raise ValueError(
            f"loan {name!r}: fully-amortizing loan left a "
            f"{schedule.balloon:,.2f} balloon at maturity"
        )
