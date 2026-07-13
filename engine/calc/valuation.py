"""Present value, IRR, and direct capitalization (Phase 3 Step 5;
spec §3.18 / §4.1 pass 14) [AE pp. 450-476, 453-454, 472-473].

**EXTERNALLY UNVALIDATED:** no golden populates ``valuation`` and none
ever will — no OM publishes a valuation result (verified 2026-07-11).
Proven by worked-example tests (Iron Rule 3), engineered tests, the §9.3
self-consistency invariant, and an owner hand-check against Excel's
NPV()/IRR() (DEVIATIONS.md §20). Valuation never recomputes the ledger
(spec §4.1) — it consumes the assembled ``RunResult``.

Cash-flow basis (spec §4.1 pass 14):

- **Unleveraged** stream = the ledger's Cash Flow Before Debt Service
  over the holding period (pv_start through the resale month; the resale
  look-forward is the buyer's, not owned cash flow) + the unleveraged net
  resale proceeds in the resale month; t0 outflow = the purchase price.
  Independent of debt and — apart from the ``pct_increase_over_price``
  resale method — of the price itself.
- **Leveraged** stream = Cash Flow After Debt Service over the hold +
  the leveraged net resale (net proceeds − loan payoffs) in the resale
  month; t0 outflow = equity = purchase price − loan funding proceeds.
- The resale amount is taken from the ``ResaleResult`` directly (not the
  posted ledger column), so it values correctly even when
  ``apply_resale_to_cash_flow`` is False (:func:`holding_stream`).
- Below-the-line items (closing costs, deposits) are NOT in the stream —
  the spec basis is CFBDS/CFADS + resale only, and folding closing costs
  into t0 would break the §9.3 identity.

Discounting (spec §4.1): the rate is an APR [AE p. 472 "Discount Rate
(APR)"]. For periods-per-year p ∈ {annual 1, quarterly 4, monthly 12},
the monthly stream is aggregated into p-per-year buckets from
``pv_start`` and each bucket discounted at ``(1 + (d/100)/p)^(−e)``,
where ``e`` is the 1-based period index (``end_of_period``) or index −
0.5 (``mid_period``, the [AE p. 472] half-period convention). The t0
price sits at exponent 0. "Monthly in Advance" (0/12 for period one) is
not a schema convention.

IRR: solve the periodic rate that zeroes the stream's NPV (one sign
change → a unique root, bisection), then **annualize nominally
(periodic × p)** — NOT the effective ``(1+irr_m)^12−1`` the spec text
also states. The spec is internally inconsistent (nominal APR/p
discounting vs an effective IRR formula); nominal annualization is the
only convention under which "price = PV ⟹ IRR = discount rate" holds
(the §9.3 invariant and ARGUS's core value identity). DEVIATIONS.md §20.

Direct cap [AE pp. 453-454]: value = NOI basis / (cap_rate/100), the NOI
basis anchored at ``pv_start`` — ``year_1`` = analysis year 1 (the first
12 ledger months), ``forward_12`` = the 12 months forward from
``pv_start``. These coincide when ``pv_start`` = analysis begin and are a
distinct window from resale's ``cap_noi_forward_12`` (anchored at the
resale date, Step 4).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from engine.models import PropertyModel
from engine.models.valuation import (
    DiscountMethod,
    NOIBasis,
    PeriodConvention,
    ValuationInputs,
)

from .ledger import (
    CFADS,
    CFBDS,
    CLOSING_COSTS,
    LOAN_COSTS,
    NOI,
    MonthlyLedger,
)
from .resale import ResaleResult
from .timeline import snap_to_month_start

#: Periods per year for each discount method.
_PERIODS_PER_YEAR = {
    DiscountMethod.annual: 1,
    DiscountMethod.quarterly: 4,
    DiscountMethod.monthly: 12,
}
#: IRR bisection bracket. The floor is a PERIODIC percent kept safely
#: above −100% (so the discount factor 1 + periodic stays positive); the
#: annual-nominal floor is this × periods-per-year, convention-aware —
#: for monthly it is −1188%, not a fixed −99%, so valid deeply-negative
#: (large-loss) IRRs are reachable (#8, DEVIATIONS.md §24). The ceiling
#: is an annual nominal percent.
_IRR_PERIODIC_FLOOR_PCT = -99.0
_IRR_HIGH_PCT = 1_000.0
_IRR_TOL = 1e-10


@dataclass
class ValuationResult:
    """PV / IRR / direct-cap outputs (spec §7 reports 8-9 detail)."""

    discount_rate: float                     # APR percent, as input
    discount_method: DiscountMethod
    period_convention: PeriodConvention
    pv_start: pd.Period
    unleveraged_pv: float
    unleveraged_irr: Optional[float]         # annual percent; None if no price
    unleveraged_t0: Optional[float]          # price + t0 closing/financing costs
    leveraged_pv: Optional[float]            # None if no loans
    leveraged_irr: Optional[float]           # None if no loans or no price
    leveraged_equity: Optional[float]        # t0 equity; None if no loans/price
    direct_cap_value: Optional[float]        # None if no direct_cap input


def _period_buckets(stream: pd.Series, pv_start: pd.Period,
                    method: DiscountMethod, convention: PeriodConvention,
                    ) -> list[tuple[float, float]]:
    """Aggregate a monthly cash-flow series into (exponent, amount)
    buckets for one discount convention (module docstring). Months before
    ``pv_start`` are excluded; the exponent is the 1-based period index,
    less 0.5 for mid-period."""
    p = _PERIODS_PER_YEAR[method]
    months_per_period = 12 // p
    sums: dict[int, float] = {}
    for month, amount in stream.items():
        if month < pv_start:
            continue
        months_elapsed = ((month.year - pv_start.year) * 12
                          + (month.month - pv_start.month))
        period = months_elapsed // months_per_period + 1  # 1-based
        sums[period] = sums.get(period, 0.0) + float(amount)
    shift = 0.5 if convention == PeriodConvention.mid_period else 0.0
    return [(period - shift, amount) for period, amount in sorted(sums.items())]


def _present_value(buckets: list[tuple[float, float]], annual_rate_pct: float,
                   method: DiscountMethod) -> float:
    """Σ amount / (1 + periodic)^exponent, periodic = APR/p (nominal)."""
    periodic = (annual_rate_pct / 100.0) / _PERIODS_PER_YEAR[method]
    return sum(amount / (1.0 + periodic) ** exponent
               for exponent, amount in buckets)


def holding_stream(operating: pd.Series, resale_amount: float,
                   resale_month: pd.Period) -> pd.Series:
    """The investor's cash-flow stream over the holding period: the
    operating series (CFBDS or CFADS) truncated at the resale month, with
    the net resale proceeds added there. Months AFTER the resale belong
    to the buyer — the 12-month resale look-forward exists only to value
    the terminal cap-NOI (spec §2.3), it is not owned cash flow — so they
    are dropped. Taking the resale amount directly (not the ledger's
    posted column) also values it correctly when
    ``apply_resale_to_cash_flow`` is False."""
    stream = operating[operating.index <= resale_month].copy()
    stream.loc[resale_month] += resale_amount
    return stream


def _sign_changes(amounts: list[float]) -> int:
    """Number of sign changes in a cash-flow sequence, ignoring zeros."""
    signs = [1 if a > 0.0 else -1 for a in amounts if a != 0.0]
    return sum(1 for a, b in zip(signs, signs[1:]) if a != b)


def _solve_irr(buckets: list[tuple[float, float]], t0: float,
               method: DiscountMethod) -> Optional[float]:
    """Annual nominal IRR (percent) for the stream ``t0`` (at exponent 0)
    plus ``buckets``: bisect the periodic rate that zeroes NPV, then
    annualize × p. Returns ``None`` when the endpoints don't bracket a
    root (no sign change → no real IRR). **Raises ``ValueError`` when the
    stream has more than one sign change** — multiple internal rates of
    return may exist, and returning one arbitrary root would be a silent
    number (#7, DEVIATIONS.md §24). The bracket floor is convention-aware
    (#8), so valid deeply-negative IRRs are reachable."""
    p = _PERIODS_PER_YEAR[method]

    flow = [t0] + [amount for _, amount in buckets]
    changes = _sign_changes(flow)
    if changes > 1:
        raise ValueError(
            f"IRR is ambiguous: the cash-flow stream has {changes} sign "
            "changes, so more than one internal rate of return may exist. "
            "Refusing to return a single arbitrary root (no silent "
            "numbers — Iron Rule / spec §1.3). Inspect the stream (e.g. a "
            "large mid-hold capital event or staged loan draw)."
        )

    def npv(annual_pct: float) -> float:
        return t0 + _present_value(buckets, annual_pct, method)

    lo, hi = _IRR_PERIODIC_FLOOR_PCT * p, _IRR_HIGH_PCT
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo == 0.0:
        return lo
    if f_hi == 0.0:
        return hi
    if (f_lo > 0.0) == (f_hi > 0.0):
        return None  # no bracketed root
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if abs(f_mid) < _IRR_TOL or (hi - lo) < _IRR_TOL:
            return mid
        if (f_mid > 0.0) == (f_lo > 0.0):
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
    return (lo + hi) / 2.0


def _pv_start_month(valuation: ValuationInputs, analysis_begin: dt.date,
                    months: pd.PeriodIndex) -> pd.Period:
    if valuation.pv_start is None:
        return months[0]
    start = pd.Period(snap_to_month_start(valuation.pv_start), freq="M")
    if start < months[0] or start > months[-1]:
        raise ValueError(
            f"pv_start {start} is outside the analysis timeline "
            f"({months[0]}..{months[-1]})"
        )
    return start


def _direct_cap_value(valuation: ValuationInputs, frame: pd.DataFrame,
                      pv_start: pd.Period, months: pd.PeriodIndex,
                      analysis_begin: dt.date) -> Optional[float]:
    direct = valuation.direct_cap
    if direct is None:
        return None
    if direct.noi_basis == NOIBasis.year_1:
        window = months[:12]                       # analysis year 1
    else:  # forward_12: 12 months forward from pv_start [AE pp. 453-454]
        window = pd.period_range(pv_start, pv_start + 11, freq="M")
    noi = float(frame[NOI][window].sum())
    return noi / (direct.cap_rate / 100.0)


def compute_valuation(valuation: ValuationInputs, ledger: MonthlyLedger,
                      months: pd.PeriodIndex, analysis_begin: dt.date,
                      model: PropertyModel,
                      resale: Optional[ResaleResult],
                      loan_schedules: list) -> ValuationResult:
    """Unleveraged/leveraged PV and IRR + direct cap from the assembled
    ledger (spec §4.1 pass 14; module docstring). ``resale`` supplies the
    terminal value; the holding stream truncates the operating cash flows
    at the resale month and adds the net proceeds there (the resale
    look-forward is not owned cash flow — :func:`holding_stream`)."""
    frame = ledger.frame
    pv_start = _pv_start_month(valuation, analysis_begin, months)
    method = valuation.discount_method
    convention = valuation.period_convention
    rate = valuation.discount_rate
    resale_month = resale.resale_month
    # No silent numbers: a valuation date after disposition leaves no
    # holding period — the truncated stream would be empty and PV/IRR
    # meaningless. Refuse rather than return a zero (Codex finding #9).
    if pv_start > resale_month:
        raise ValueError(
            f"pv_start {pv_start} is after the resale month "
            f"{resale_month}; there is no holding period to value. The "
            "valuation date must be at or before disposition."
        )

    price = (model.purchase.price
             if model.purchase is not None and model.purchase.price is not None
             else None)

    # t0 acquisition/financing costs the investor pays at the valuation
    # date — closing costs and loan costs posted at or before pv_start.
    # These are below-the-line (not in CFBDS/CFADS), and the owner-approved
    # reframe (#2, DEVIATIONS.md §24) counts returns net of them: the t0
    # outflow is price + these costs, not price alone ("the numbers LP
    # cares about is the actual return including closing costs"). Costs
    # dated AFTER pv_start are a known residual gap (still below the line).
    # Ledger columns are negative (report sign); flip to positive outflows.
    closing_at_t0 = -float(frame[CLOSING_COSTS][frame.index <= pv_start].sum())
    financing_at_t0 = -float(frame[LOAN_COSTS][frame.index <= pv_start].sum())
    t0_costs = closing_at_t0 + financing_at_t0

    # Unleveraged: CFBDS over the hold + the unleveraged net resale;
    # t0 = price + t0 closing/financing costs.
    unlev_stream = holding_stream(frame[CFBDS], resale.net_unleveraged,
                                  resale_month)
    unlev_buckets = _period_buckets(unlev_stream, pv_start, method, convention)
    unleveraged_pv = _present_value(unlev_buckets, rate, method)
    unleveraged_t0 = (price + t0_costs) if price is not None else None
    unleveraged_irr = (
        _solve_irr(unlev_buckets, -unleveraged_t0, method)
        if unleveraged_t0 is not None else None
    )

    # Leveraged: CFADS over the hold + the leveraged net resale, plus each
    # loan's proceeds posted at its ACTUAL funding month (#1). t0 equity =
    # price + t0 costs − only the proceeds available at t0 (loans funding
    # at pv_start, plus the assumed outstanding balance of any loan funded
    # before pv_start); later-funding draws post as stream inflows, not
    # netted at t0. Computable only with loans.
    leveraged_pv = None
    leveraged_irr = None
    leveraged_equity = None
    if model.loans:
        lev_stream = holding_stream(frame[CFADS], resale.net_leveraged,
                                    resale_month)
        day_one_proceeds = 0.0
        for s in loan_schedules:
            if s.funding_month == pv_start:
                day_one_proceeds += s.principal0
            elif s.funding_month < pv_start:
                # assumed existing loan: the buyer takes on its balance
                day_one_proceeds += float(s.balance[pv_start])
            elif s.funding_month <= resale_month:
                # staged/construction draw: a positive inflow at its month
                lev_stream.loc[s.funding_month] += s.principal0
        lev_buckets = _period_buckets(lev_stream, pv_start, method, convention)
        leveraged_pv = _present_value(lev_buckets, rate, method)
        if price is not None:
            leveraged_equity = price + t0_costs - day_one_proceeds
            leveraged_irr = _solve_irr(lev_buckets, -leveraged_equity, method)

    direct_cap_value = _direct_cap_value(valuation, frame, pv_start, months,
                                         analysis_begin)

    return ValuationResult(
        discount_rate=rate, discount_method=method,
        period_convention=convention, pv_start=pv_start,
        unleveraged_pv=unleveraged_pv, unleveraged_irr=unleveraged_irr,
        unleveraged_t0=unleveraged_t0,
        leveraged_pv=leveraged_pv, leveraged_irr=leveraged_irr,
        leveraged_equity=leveraged_equity,
        direct_cap_value=direct_cap_value,
    )


def assert_pv_irr_self_consistency(result: ValuationResult,
                                   model: PropertyModel) -> None:
    """§9.3 self-consistency, standing whenever the **total t0 outlay**
    (price + t0 closing/financing costs) equals the computed unleveraged
    PV: the unleveraged IRR then equals the discount rate within 1bp
    (0.01 percentage points). This is ARGUS's "value net of costs = PV ⟹
    IRR = discount rate" identity — a tautology of the bisection solver.
    The reframe (#2, DEVIATIONS.md §24) only changed *what value is
    tested* (price → price + t0 costs), not the identity's logic; it holds
    for every discount convention under nominal annualization."""
    if result.unleveraged_t0 is None or result.unleveraged_irr is None:
        return
    total_outlay = result.unleveraged_t0  # price + t0 closing/financing
    if abs(total_outlay - result.unleveraged_pv) > 0.01:
        return  # outlay isn't set to the computed PV — identity not claimed
    if abs(result.unleveraged_irr - result.discount_rate) > 0.01:
        raise ValueError(
            f"PV/IRR self-consistency violated: the total t0 outlay "
            f"(price + closing/financing = {total_outlay:,.2f}) equals the "
            f"unleveraged PV but the unleveraged IRR "
            f"({result.unleveraged_irr:.4f}%) is not the discount rate "
            f"({result.discount_rate:.4f}%) within 1bp"
        )
