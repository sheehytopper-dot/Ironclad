"""Acquisition flows and tenant security deposits (Phase 3 Step 2;
spec §3.16 / §3.12) [AE pp. 435-437, 384, 431-433].

**EXTERNALLY UNVALIDATED:** no golden fixture populates ``purchase`` or
``security_deposit`` — like reabsorb and tenant miscellaneous items, this
module is proven by the manual's definitions and engineered tests only
(DEVIATIONS.md §17), with no OM-published reference available.

All three lines post **below the line** — after Cash Flow Before Debt
Service, outside every NOI/EGR/CFBDS rollup. The ARGUS Cash Flow report
carries no acquisition rows (all three golden CSVs end at CFBDS), and the
manual frames purchase inputs as feeding "cash-on-cash metrics and
returns, such as the internal rate of return" [AE p. 435] — spec §4.1
pass 14 consumes the price at t0 on the valuation side.

- **Purchase price** (``fixed`` derivation only): posts as a negative
  lump sum in the purchase month. ARGUS fixes the purchase date at the
  Analysis Begin Date ("You cannot change this date" [AE p. 435]); the
  schema's optional ``date`` is honored when given (DEVIATIONS.md §17).
  The derived derivations (PV / direct cap [AE pp. 435-436]) refuse
  loudly — live derivation is an open owner scope decision after Step 5
  (DEVIATIONS.md §20).
- **Closing costs** [AE pp. 436-437]: each posts negative, $ amount or
  % of the purchase price, in the purchase month or at its own
  ``custom_date``. The manual's "% Total Price" method (a percentage of
  purchase + closing, self-referential) is schema-absent; Vendors Fees %
  and Stamp Duty % are ``pct_of_price`` with a label (DEVIATIONS.md §17).
- **Security deposits** [AE pp. 431-433; p. 384]: per segment — the
  contract term uses the lease's spec, speculative terms the MLP's
  ("once the lease expires, the input under the leasing profile will be
  used" [AE p. 384]). Collection posts as a **positive inflow at segment
  start**; if ``refunded_at_expiration``, the refund posts negative in
  the segment's final month. Sizing per [AE pp. 432-433]:
  ``months_of_rent`` × the base rental revenue level in the segment's
  first month (the manual's stated basis — free rent does not reduce
  it, since Base Rental Revenue posts gross of abatements);
  ``dollars_per_area`` × the lease area; ``dollars`` flat. A segment
  starting before the analysis window collects nothing in-window, but an
  in-window refund still posts (the refund is a real cash event even
  when the collection predated the analysis — DEVIATIONS.md §17).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd

from engine.models import Inflation, Purchase
from engine.models.investment import ClosingCostTiming, PriceDerivation
from engine.models.profiles import SecurityDepositSpec, SecurityDepositUnit

from .leases import LeaseSegment, segment_rent_level
from .timeline import snap_to_month_start


def _in_window(period: pd.Period, months: pd.PeriodIndex, what: str) -> pd.Period:
    if period < months[0] or period > months[-1]:
        raise ValueError(
            f"{what} month {period} is outside the analysis timeline "
            f"({months[0]}..{months[-1]})"
        )
    return period


def acquisition_flows(purchase: Purchase, months: pd.PeriodIndex,
                      analysis_begin: dt.date,
                      ) -> tuple[pd.Series, pd.Series]:
    """Purchase price and closing costs as negative monthly series
    (spec §3.16) [AE pp. 435-437]. A purchase or custom-date closing cost
    outside the timeline is a modeling error and raises — never a silent
    drop."""
    if purchase.derivation != PriceDerivation.fixed:
        raise NotImplementedError(
            f"purchase price derivation '{purchase.derivation.value}' "
            "(price backed out from computed valuation) is not implemented. "
            "Step 5 (PV/IRR) built the unleveraged PV this would derive from, "
            "but live derivation is an OPEN OWNER SCOPE DECISION "
            "(DEVIATIONS.md §20): deriving the price from the unleveraged PV "
            "is non-circular ONLY with no price-dependent loans and a resale "
            "method other than pct_increase_over_price, and even then needs "
            "the acquisition-flow posting deferred past valuation; a "
            "pct_of_price/pct_of_value loan sized off the derived price needs "
            "debt reordered after valuation. Use derivation 'fixed'."
        )
    price = pd.Series(0.0, index=months, name="purchase_price")
    closing = pd.Series(0.0, index=months, name="closing_costs")

    when = purchase.date if purchase.date is not None else analysis_begin
    purchase_month = _in_window(
        pd.Period(snap_to_month_start(when), freq="M"), months,
        "purchase date",
    )
    price[purchase_month] -= purchase.price

    for cost in purchase.closing_costs:
        amount = (cost.amount if cost.amount is not None
                  else purchase.price * cost.pct_of_price / 100.0)
        if cost.timing == ClosingCostTiming.custom_date:
            month = _in_window(
                pd.Period(snap_to_month_start(cost.date), freq="M"), months,
                f"closing cost {cost.name!r} date",
            )
        else:
            month = purchase_month
        closing[month] -= amount
    return price, closing


def _deposit_amount(spec: SecurityDepositSpec, segment: LeaseSegment) -> float:
    """Deposit dollars per [AE pp. 432-433]: months × month-one base
    rental revenue, $/area × lease size, or a flat amount."""
    if spec.unit == SecurityDepositUnit.months_of_rent:
        return spec.amount * segment_rent_level(segment, segment.start)
    if spec.unit == SecurityDepositUnit.dollars_per_area:
        return spec.amount * segment.area
    return spec.amount


def segment_security_deposits(segments: list[LeaseSegment],
                              months: pd.PeriodIndex) -> pd.Series:
    """One lease chain's deposit flows: per segment, collection (+) at
    segment start, refund (−) in the segment's final month when the spec
    refunds [AE pp. 431-433]. The contract segment carries the lease's
    spec, speculative segments their MLP's [AE p. 384]; a rollover
    therefore refunds the expiring segment's deposit and collects the
    next segment's — adjacent cash events, not netted (DEVIATIONS.md
    §17)."""
    series = pd.Series(0.0, index=months, name="security_deposits")
    for segment in segments:
        if segment.speculative:
            spec = (segment.profile.security_deposit
                    if segment.profile is not None else None)
        else:
            spec = segment.lease.security_deposit
        if spec is None:
            continue
        amount = _deposit_amount(spec, segment)
        if months[0] <= segment.start <= months[-1]:
            series[segment.start] += amount
        if spec.refunded_at_expiration and months[0] <= segment.end <= months[-1]:
            series[segment.end] -= amount
    return series
