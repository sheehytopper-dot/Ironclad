"""Sensitivity matrices (Phase 3 Step 6; spec §3.18 ``sensitivity_intervals``
/ §7 reports 5-6) [AE pp. 451-452].

**EXTERNALLY UNVALIDATED:** no golden populates ``valuation`` and none
ever will (no OM publishes a valuation result, verified 2026-07-11).
Proven by engineered tests and the plan's own cross-check
(tests/unit/test_sensitivity.py): every matrix cell equals a direct
single-point call to the Step 4/5 functions with those substituted
inputs (DEVIATIONS.md §21).

This is a pure re-computation over the assembled ``RunResult`` — the
ledger is NEVER recomputed (spec §4.1). Each column reuses Step 4's
``compute_resale`` with a ``model_copy`` substituting the exit cap
(reads the existing NOI window only); each cell reuses Step 5's
``_period_buckets``/``_present_value``/``_solve_irr`` on
``CFBDS``/``CFADS`` + the substituted resale proceeds.

Two matrices (spec §7 reports 5-6), as DataFrames — rendering is Phase 4:

- **Value matrix** — unleveraged PV over **discount rate (rows) × exit
  cap (columns)**.
- **IRR matrix** — unleveraged IRR over **price (rows) × exit cap
  (columns)**, plus a parallel **leveraged IRR matrix** on the same axes
  (all-NaN when there are no loans — never a silent zero, Step 5's
  convention). The price rows are unleveraged PV at the discount-rate
  grid, valued at the BASE exit cap ("prices at PV of rate grid", spec
  §7 report 5) — a pure sensitivity axis, not live price derivation
  (Step 5 / DEVIATIONS.md §20 #6 is untouched).

Grid: ``count`` ∈ {5, 7} points **centered on the base case**, spaced
``±k × step`` (the odd count guarantees a center cell = the exact base
case; the manual gives the step, the centering is the standard
convention — DEVIATIONS.md §21). The exit-cap axis applies only to
cap-NOI resale methods [AE p. 451]; for fixed/pct-increase resales there
is no cap axis and sensitivity is ``None``.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from engine.models import PropertyModel
from engine.models.valuation import Resale, ResaleMethod

from .ledger import CFADS, CFBDS
from .resale import ResaleResult, compute_resale
from .valuation import (
    _period_buckets,
    _pv_start_month,
    _present_value,
    _solve_irr,
    holding_stream,
)

#: Resale methods whose value depends on an exit cap rate (spec §3.18;
#: [AE p. 451] "one of the NOI options").
_CAP_METHODS = (
    ResaleMethod.cap_noi_forward_12,
    ResaleMethod.cap_noi_current_year,
    ResaleMethod.gross_value_less_costs,
)


@dataclass
class SensitivityMatrices:
    """Sensitivity grids (spec §7 reports 5-6 data; rendering is Phase 4).

    Row/column labels are the axis values (percent or dollars); every
    cell equals a direct single-point Step 4/5 computation."""

    value_matrix: pd.DataFrame              # unleveraged PV; discount × cap
    unleveraged_irr_matrix: pd.DataFrame    # price × cap
    leveraged_irr_matrix: pd.DataFrame      # price × cap (NaN without loans)
    discount_rate_axis: list[float]         # percent
    cap_rate_axis: list[float]              # percent
    price_axis: list[float]                 # dollars (PV at each discount rate)


def _centered_axis(base: float, step: float, count: int) -> list[float]:
    """``count`` points centered on ``base``, spaced ``±k × step`` (odd
    count → a center point equal to the base case)."""
    half = count // 2
    return [base + (i - half) * step for i in range(count)]


def _resale_at_cap(base_resale: Resale, exit_cap: float, result,
                   model: PropertyModel) -> ResaleResult:
    """Step 4's resale recomputed at a substituted exit cap against the
    existing ledger (no ledger recompute)."""
    substituted = base_resale.model_copy(update={"exit_cap_rate": exit_cap})
    return compute_resale(substituted, result.ledger, result.months,
                          result.occupancy, model, result.loan_schedules)


def _unlev_stream(result, resale: ResaleResult) -> pd.Series:
    return holding_stream(result.ledger.frame[CFBDS], resale.net_unleveraged,
                          resale.resale_month)


def _lev_stream(result, resale: ResaleResult) -> pd.Series:
    return holding_stream(result.ledger.frame[CFADS], resale.net_leveraged,
                          resale.resale_month)


def compute_sensitivity(model: PropertyModel, result,
                        ) -> Optional[SensitivityMatrices]:
    """Build the value and IRR matrices from the assembled ``RunResult``
    (module docstring). Returns ``None`` when the resale method has no
    exit cap (fixed/pct-increase — no cap axis)."""
    valuation = model.valuation
    if valuation is None:
        return None
    base_resale = valuation.resale
    if base_resale.method not in _CAP_METHODS:
        return None

    intervals = valuation.sensitivity_intervals
    method = valuation.discount_method
    convention = valuation.period_convention
    pv_start = _pv_start_month(valuation, model.property.analysis_begin,
                               result.months)

    discount_axis = _centered_axis(valuation.discount_rate,
                                   intervals.discount_rate_step,
                                   intervals.count)
    cap_axis = _centered_axis(base_resale.exit_cap_rate,
                              intervals.cap_rate_step, intervals.count)
    loan_proceeds = sum(float(s.funding.sum()) for s in result.loan_schedules)
    has_loans = bool(result.loan_schedules)

    # One resale per exit cap (columns share it) — read the NOI window once.
    resale_by_cap = {cap: _resale_at_cap(base_resale, cap, result, model)
                     for cap in cap_axis}
    unlev_buckets = {
        cap: _period_buckets(_unlev_stream(result, resale_by_cap[cap]),
                             pv_start, method, convention)
        for cap in cap_axis
    }
    lev_buckets = {
        cap: _period_buckets(_lev_stream(result, resale_by_cap[cap]),
                             pv_start, method, convention)
        for cap in cap_axis
    }

    # Value matrix: unleveraged PV over discount × cap.
    value = pd.DataFrame(
        {cap: {rate: _present_value(unlev_buckets[cap], rate, method)
               for rate in discount_axis}
         for cap in cap_axis},
        index=discount_axis, columns=cap_axis,
    )

    # Price axis: unleveraged PV at each discount rate, at the BASE exit
    # cap (spec §7 report 5 "prices at PV of rate grid") = the base-cap
    # column of the value matrix.
    base_cap = base_resale.exit_cap_rate
    price_axis = [float(value.loc[rate, base_cap]) for rate in discount_axis]

    def irr_grid(buckets_by_cap, equity_offset):
        return pd.DataFrame(
            {cap: {price: _solve_irr(buckets_by_cap[cap],
                                     -(price - equity_offset), method)
                   for price in price_axis}
             for cap in cap_axis},
            index=price_axis, columns=cap_axis,
        )

    unleveraged_irr = irr_grid(unlev_buckets, 0.0)
    if has_loans:
        leveraged_irr = irr_grid(lev_buckets, loan_proceeds)
    else:
        leveraged_irr = pd.DataFrame(float("nan"), index=price_axis,
                                     columns=cap_axis)

    return SensitivityMatrices(
        value_matrix=value, unleveraged_irr_matrix=unleveraged_irr,
        leveraged_irr_matrix=leveraged_irr, discount_rate_axis=discount_axis,
        cap_rate_axis=cap_axis, price_axis=price_axis,
    )
