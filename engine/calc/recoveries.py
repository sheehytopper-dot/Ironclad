"""Expense recoveries: system methods and user recovery structures
(Phase 2 Step 5) [AE pp. 404-413, 517-520].

System methods [AE pp. 405-406, 408-409]: ``net`` (pool × share),
``base_stop`` (building $/SF stop), ``base_year``/``base_year_plus_1``
(frozen base-year pool as the stop; lease-start-relative, pre-analysis
starts use analysis year 1), ``fixed`` (tenant amount, opt-in inflation).
All recoveries floor at 0 — a tenant never pays the landlord's stop — and
post as straight monthly accrual (spec §3.14 v1 policy).

**Base-year window resolution** (``_resolve_base_year_window``, shared by
the system methods and user pools). The pre-analysis fallback [AE pp. 377,
408] triggers off **either** an explicit stated base year whose whole
12-month window ends before the analysis start (the OM's true base year,
e.g. 2017, has no ledger data → analysis year 1, while the stated year is
kept as the documented input) **or** — when no year is stated — a lease
start before the analysis. A partially-in-window year is kept and
annualized from its available months; a future-dated window still raises.
**Known base-year override:** ``RecoveryAssignment.base_year_amount`` and
``BaseYearSpec.known_amount`` supply the frozen base-year pool as a TOTAL
annual dollar figure (matching what the computed path produces before
pro-rata division — *not* a $/SF quantity like ``base_stop``); when set the
window and fallback are bypassed and the year field is pure documentation.
Both are frozen historical constants w.r.t. the fee, so the %-of-EGR fixed
point's contraction bound is untouched (DEVIATIONS.md §10; §6).

User structures (spec §3.14 [AE pp. 407-413]): named pools over expense
refs and expense groups (group members resolved; an expense appearing
twice in one structure is an error — "take care to avoid double counting"
[AE p. 408]); per-pool methods net/stop/base_year/fixed; expense
adjustments (± pct of a named expense [AE p. 410]); denominators
rentable_area / property_size / occupied_area / fixed_area [AE p. 410];
``pro_rata_share_override``; admin fee as % of recoverable expenses
[AE pp. 519-520] added to the basis before or after the stop subtraction;
caps/floors per pool [AE pp. 411-412] — annual min/max inflating on the
general rate by default, YoY and cumulative growth caps applied to
calendar-year totals (v1 convention; ARGUS reconciles on recovery years).
Explicit pool membership is authoritative: a named expense joins its pool
regardless of ``is_recoverable`` (user intent governs).

**Gross-up** [AE p. 407; formula p. 520]: grossed expense = fixed portion
+ variable portion × (gross_up_pct / actual occupancy) when actual <
target, never gross down. Per item with fixed fraction f at occupancy
``occ`` this reduces to series × (f + (1−f)·max(occ, g)) / (f + (1−f)·occ)
— **bounded**, because the occupancy in the ratio's denominator cancels
against the occupancy already inside the projected series. The genuinely
pathological case is a fully variable item (f = 0) in a zero-occupancy
month: the observed series is 0 and the base amount is unrecoverable from
it — that raises a loud ``ValueError`` (remedy: pct_fixed > 0, or no
gross-up on that pool). ``per_occupied_area`` items gross as fully
variable; ``per_available_area`` and %-of-revenue items pass through
ungrossed — the manual's "Gross Up Percent of Line" policy [AE p. 519]
at its no-adjustment (100% Fixed) setting, a fixed v1 policy
(DEVIATIONS.md §10).

**Fixed-point convergence with gross-up (extending the Step 5 session 1
stop bound):** because %-of-revenue lines are never grossed under the
fixed policy above, every gross-up ratio is a constant with respect to
the fee series — the fee passes through pools un-amplified, and the
session-1 contraction bound (factor ≤ 2 × Σ share × pct, from max(0, ·)
being 1-Lipschitz with the fee reaching a recovery through the month's
pool and the frozen base-year stop) carries over unchanged. Implementing
the manual's 100%-Variable policy would multiply that bound by
max(g / occ) — unbounded at low occupancy — so any future policy toggle
must re-derive the bound before shipping; it is deliberately not
implemented (DEVIATIONS.md §10).

**Fixed-point convergence with expense limits (extending both bounds
above; Gate 2 audit-review request):** a recoverable %-of-revenue fee may
carry per-month min/max clamps (``ExpenseItem.limits`` [AE p. 279]) —
e.g. a management fee floored at a dollar minimum that must hold through
full vacancy. ``run_property`` re-projects the fee off EGR each round and
``project_expense`` clamps after applying the percentage, so the
iteration map becomes clamp ∘ (pct × EGR(·)). Min/max clamps are
1-Lipschitz — |clamp(a) − clamp(b)| ≤ |a − b| — and locally constant
(factor 0) wherever a bound binds, so composing them can only tighten
the session-1/session-2 contraction bound, never loosen it. Verified
against the iteration code: the fee series is stored, compared for
convergence, and fed to EGR post-clamp, so the composition above is
exactly what iterates (tests/unit/test_run.py::TestFeeFloorInFixedPoint,
including exact Recovery Audit reconciliation with a binding floor).

Not modeled (schema-absent, DEVIATIONS.md §10): anchor contributions /
"Reimburse After" common-expense factors [AE pp. 410-411], the
"% of Recovery" admin-fee flavor [AE p. 520], fiscal base-year windows
(``BaseYearSpec.fiscal`` raises), and amount/area cap units.

Full per-tenant per-pool audit detail is retained (``PoolAudit``) for the
Recovery Audit report (spec §7 report 18), which must reconcile exactly
to the ledger. Everything returns monthly Period[M] Series (spec §2.3);
recoveries post to Expense Recovery Revenue. The engine never imports UI
code (Iron Rule 1).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional, Union

import pandas as pd

from engine.calc.expenses import PCT_UNITS
from engine.calc.inflation import index_schedule, inflation_factors
from engine.calc.leases import lease_term_periods
from engine.calc.timeline import snap_to_month_start
from engine.models import (
    AdminFeeApplies,
    CapsFloors,
    Denominator,
    ExpenseItem,
    ExpenseUnit,
    Inflation,
    Lease,
    PoolMethod,
    RecoveryAssignment,
    RecoveryPool,
    RecoveryStructure,
    RecoverySystemMethod,
)

#: (item, projected monthly series) pairs, as produced by
#: engine.calc.expenses.project_expense over the same timeline.
ExpenseSeries = Iterable[tuple[ExpenseItem, pd.Series]]

#: Units whose projected series carries a pct_fixed occupancy split the
#: gross-up formula can invert (spec §3.11).
_FIXED_DOLLAR_UNITS = frozenset({
    ExpenseUnit.dollars_per_year,
    ExpenseUnit.dollars_per_month,
    ExpenseUnit.dollars_per_area_per_year,
    ExpenseUnit.dollars_per_area_per_month,
})


@dataclass
class RecoveryContext:
    """Property-level context user structures and gross-up need beyond the
    (item, series) pairs: the occupancy series, denominators, and the named
    structures/groups (run.py builds one per run)."""

    occupancy: pd.Series
    occupied_area: pd.Series
    property_size: float
    structures: Mapping[str, RecoveryStructure] = field(default_factory=dict)
    expense_groups: Mapping[str, list] = field(default_factory=dict)


@dataclass
class PoolAudit:
    """Per-tenant per-pool audit trail (spec §7 report 18; spec §1.3 "no
    silent numbers"): expenses (adjusted basis), gross-up, admin fee, stop,
    share, pre-cap result, and the final posted recovery."""

    tenant: str
    segment_start: pd.Period
    start: pd.Period
    end: pd.Period
    structure: Optional[str]
    pool: str
    basis: pd.Series
    grossed: pd.Series
    admin_fee: pd.Series
    stop: pd.Series
    share: pd.Series
    pre_cap: pd.Series
    recovery: pd.Series


def _area_at(rentable_area: Union[pd.Series, float], period: pd.Period) -> float:
    if isinstance(rentable_area, pd.Series):
        return float(rentable_area[period])
    return float(rentable_area)


def recoverable_pool(expenses: ExpenseSeries, months: pd.PeriodIndex) -> pd.Series:
    """Sum the recoverable expenses into one monthly pool series.

    Membership is ``ExpenseItem.is_recoverable`` — the explicit flag, else
    the category default (operating in; capital and non-operating out,
    spec §3.11). Series are taken as projected: a %-of-EGR fee contributes
    whatever fixed-point series the caller resolved (spec §4.1 step 9).
    """
    pool = pd.Series(0.0, index=months, name="recoverable_pool")
    for item, series in expenses:
        if item.is_recoverable:
            pool += series.reindex(months, fill_value=0.0)
    return pool


def net_recoveries(lease: Lease, months: pd.PeriodIndex, pool: pd.Series,
                   rentable_area: Union[pd.Series, float]) -> pd.Series:
    """Net system method [AE p. 405]: the tenant pays its proportionate
    share — lease area / rentable area — of the pool expense each occupied
    month of the contract term."""
    series = pd.Series(0.0, index=months, name="expense_recovery")
    start, end = lease_term_periods(lease)
    for period in months:
        if start <= period <= end:
            share = lease.area / _area_at(rentable_area, period)
            series[period] = float(pool[period]) * share
    return series


# ------------------------------------------------------------------ #
# Gross-up [AE p. 407; formula p. 520]                                #
# ------------------------------------------------------------------ #

def _grossed_series(item: ExpenseItem, series: pd.Series,
                    occupancy: pd.Series, gross_up_pct: float,
                    where: str) -> pd.Series:
    """One item's series grossed to ``gross_up_pct`` occupancy: series ×
    (f + (1−f)·max(occ, g)) / (f + (1−f)·occ) — never grossed down
    [AE p. 407]. %-of-revenue and per-available-area items pass through
    ungrossed (module docstring policy)."""
    unit = item.unit
    if unit in PCT_UNITS or unit == ExpenseUnit.per_available_area:
        return series
    f = 0.0 if unit == ExpenseUnit.per_occupied_area else item.pct_fixed / 100.0
    if f >= 1.0:
        return series  # 100% fixed: gross-up never applies [AE p. 519]
    g = gross_up_pct / 100.0
    out = series.copy()
    for period in series.index:
        occ = float(occupancy[period])
        if occ >= g:
            continue  # never gross down
        denominator = f + (1.0 - f) * occ
        if denominator <= 0.0:
            raise ValueError(
                f"{where}: cannot gross up the fully variable expense "
                f"{item.name!r} in zero-occupancy month {period} — its "
                "occupancy-scaled amount is 0 and the base amount cannot "
                "be recovered from it (set pct_fixed > 0 or remove the "
                "gross-up)"
            )
        out[period] = float(series[period]) * (f + (1.0 - f) * g) / denominator
    return out


# ------------------------------------------------------------------ #
# Shared helpers: base-year windows, frozen stops, fixed amounts,      #
# caps/floors                                                          #
# ------------------------------------------------------------------ #

def _resolve_base_year_window(year: Optional[int], plus: int,
                              analysis_begin: Optional[dt.date], where: str,
                              *, lease_start: Optional[pd.Period] = None,
                              ) -> tuple[pd.Period, pd.Period]:
    """The frozen base-year window [AE pp. 405-406, 408-409, 377], shared by
    the system methods and user pools.

    "Analysis year 1" is the 12 months from the analysis begin month. The
    pre-analysis fallback ("leases that begin before the analysis start ...
    pay their pro-rata share of any increases over the ... first year of the
    analysis" [AE pp. 377, 408]) triggers off **either** signal:

    - an explicit stated ``year`` whose whole 12-month window ends before the
      analysis start — the OM's true base year (e.g. 2017) has no ledger data,
      so it falls back to analysis year 1 while the stated year is preserved as
      the documented input; OR
    - no explicit ``year`` and a ``lease_start`` before the analysis start.

    Otherwise the window is the stated year (or the lease-start calendar year),
    shifted by ``plus`` months for the +1 method. A partially-in-window year
    (e.g. a 2026 base year on a mid-2026 analysis) is kept and annualized from
    its available months by :func:`_frozen_stop_annual` — only a window ending
    entirely before the analysis start falls back. A future-dated window is
    left to raise in ``_frozen_stop_annual`` (an input error, not missing
    history)."""
    begin = (pd.Period(snap_to_month_start(analysis_begin), freq="M")
             if analysis_begin is not None else None)
    if year is not None:
        first = pd.Period(f"{year}-01", freq="M") + plus
        if begin is not None and (first + 11) < begin:
            return begin, begin + 11  # analysis year 1 [AE pp. 377, 408]
        return first, first + 11
    if begin is None:
        raise ValueError(f"{where}: base-year recoveries need analysis_begin")
    if lease_start is None or lease_start < begin:
        return begin, begin + 11  # analysis year 1 [AE pp. 408-409]
    first = pd.Period(f"{lease_start.year}-01", freq="M") + plus
    return first, first + 11


def _frozen_stop_annual(basis: pd.Series,
                        window: tuple[pd.Period, pd.Period],
                        where: str) -> float:
    """The base-year basis total, frozen. A window truncated by the
    timeline annualizes from its available months (module docstring)."""
    lo, hi = window
    available = basis[(basis.index >= lo) & (basis.index <= hi)]
    if available.empty:
        raise ValueError(
            f"{where}: base year {lo}..{hi} lies entirely outside the "
            "analysis timeline"
        )
    total = float(available.sum())
    if len(available) < 12:
        total *= 12.0 / len(available)
    return total


def _factor_series(ref, months: pd.PeriodIndex,
                   analysis_begin: Optional[dt.date],
                   inflation: Optional[Inflation], default_flat: bool,
                   where: str) -> pd.Series:
    """Inflation factors for a recovery-side InflationRef. ``None`` means
    flat when ``default_flat`` (fixed recoveries are fixed unless opted
    in), else the general rate (caps/floors inflate on general by default
    [AE p. 412])."""
    if ref is None:
        if default_flat or inflation is None:
            return pd.Series(1.0, index=months)
        ref = "general"
    if analysis_begin is None:
        raise ValueError(f"{where}: inflated recovery amounts need "
                         "analysis_begin")
    if isinstance(ref, list):
        rates = ref
    else:
        if inflation is None:
            raise ValueError(f"{where}: inflation index {ref!r} needs the "
                             "property inflation assumptions")
        rates = index_schedule(inflation, ref)
    month = inflation.inflation_month if inflation is not None else None
    basis_kwargs = ({"timing_basis": inflation.timing_basis}
                    if inflation is not None else {})
    return inflation_factors(rates, months, analysis_begin, month,
                             **basis_kwargs)


def _apply_caps_floors(series: pd.Series, caps: Optional[CapsFloors],
                       start: pd.Period, end: pd.Period,
                       months: pd.PeriodIndex,
                       analysis_begin: Optional[dt.date],
                       inflation: Optional[Inflation],
                       where: str) -> pd.Series:
    """Per-pool caps and floors [AE pp. 411-412]: annual ``min``/``max``
    amounts (monthly twelfths, inflating on the general rate by default);
    YoY (``yearly_cap_pct``, vs the prior capped year) and cumulative
    (``cumulative_cap_pct``, vs the first year compounded) growth caps on
    calendar-year totals — the v1 stand-in for ARGUS recovery years."""
    if caps is None:
        return series
    out = series.copy()
    occupied = [p for p in months if start <= p <= end]
    if caps.min is not None or caps.max is not None:
        factors = _factor_series(None, months, analysis_begin, inflation,
                                 default_flat=False, where=where)
        for period in occupied:
            f = float(factors[period])
            value = float(out[period])
            if caps.max is not None:
                value = min(value, caps.max / 12.0 * f)
            if caps.min is not None:
                value = max(value, caps.min / 12.0 * f)
            out[period] = value
    if caps.yearly_cap_pct is not None or caps.cumulative_cap_pct is not None:
        years = sorted({p.year for p in occupied})
        first_total: Optional[float] = None
        prev_total: Optional[float] = None
        for i, year in enumerate(years):
            block = [p for p in occupied if p.year == year]
            raw = float(sum(out[p] for p in block))
            allowed = raw
            if i > 0 and raw > 0:
                if caps.yearly_cap_pct is not None:
                    allowed = min(allowed,
                                  prev_total * (1 + caps.yearly_cap_pct / 100.0))
                if caps.cumulative_cap_pct is not None:
                    allowed = min(
                        allowed,
                        first_total * (1 + caps.cumulative_cap_pct / 100.0) ** i,
                    )
                if allowed < raw:
                    scale = allowed / raw
                    for p in block:
                        out[p] *= scale
            final = min(raw, allowed)
            prev_total = final
            if i == 0:
                first_total = final
    return out


# ------------------------------------------------------------------ #
# User recovery structures (spec §3.14 [AE pp. 407-413])               #
# ------------------------------------------------------------------ #

def _pool_weights(pool: RecoveryPool, groups: Mapping[str, list],
                  where: str) -> dict[str, float]:
    """Resolve a pool's expense refs (names or group names) to per-expense
    weights, applying the pool's adjustments [AE p. 410]. Duplicate
    membership is an error [AE p. 408]."""
    names: list[str] = []
    for ref in pool.expenses:
        if ref in groups:
            names.extend(groups[ref])
        else:
            names.append(ref)
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ValueError(
            f"{where}: expense(s) {sorted(duplicates)} appear more than "
            "once in one pool (directly or via groups) — double counting "
            "[AE p. 408]"
        )
    weights = {name: 1.0 for name in names}
    for adjustment in pool.expense_adjustments:
        delta = adjustment.pct / 100.0
        if adjustment.action == "exclude":
            weights[adjustment.expense] = weights.get(adjustment.expense, 0.0) - delta
        elif adjustment.action == "add":
            weights[adjustment.expense] = weights.get(adjustment.expense, 0.0) + delta
        else:
            raise ValueError(
                f"{where}: unknown expense adjustment action "
                f"{adjustment.action!r} (use 'exclude' or 'add')"
            )
    return weights


def _pool_denominator(pool: RecoveryPool,
                      rentable_area: Union[pd.Series, float],
                      context: RecoveryContext, period: pd.Period,
                      where: str) -> float:
    if pool.denominator == Denominator.rentable_area:
        return _area_at(rentable_area, period)
    if pool.denominator == Denominator.property_size:
        return context.property_size
    if pool.denominator == Denominator.occupied_area:
        return float(context.occupied_area[period])
    return float(pool.denominator_fixed_area)  # fixed_area (validated)


def _weighted_basis(weights: Mapping[str, float],
                    by_name: Mapping[str, tuple[ExpenseItem, pd.Series]],
                    months: pd.PeriodIndex, gross_up_pct: Optional[float],
                    occupancy: pd.Series, where: str) -> pd.Series:
    basis = pd.Series(0.0, index=months)
    for name, weight in weights.items():
        if name not in by_name:
            raise ValueError(f"{where}: unknown expense {name!r}")
        item, series = by_name[name]
        if gross_up_pct is not None:
            series = _grossed_series(item, series, occupancy, gross_up_pct,
                                     where)
        basis = basis + weight * series.reindex(months, fill_value=0.0)
    return basis


def _pool_recovery(pool: RecoveryPool, label: str, tenant: str,
                   structure_name: str, segment_start: pd.Period,
                   area: float, start: pd.Period, end: pd.Period,
                   months: pd.PeriodIndex,
                   by_name: Mapping[str, tuple[ExpenseItem, pd.Series]],
                   rentable_area: Union[pd.Series, float],
                   context: RecoveryContext,
                   analysis_begin: Optional[dt.date],
                   inflation: Optional[Inflation],
                   where: str) -> tuple[pd.Series, PoolAudit]:
    weights = _pool_weights(pool, context.expense_groups, where)
    basis = _weighted_basis(weights, by_name, months, None,
                            context.occupancy, where)
    grossed = (
        _weighted_basis(weights, by_name, months, pool.gross_up_pct,
                        context.occupancy, where)
        if pool.gross_up_pct is not None else basis.copy()
    )

    fee_rate = pool.admin_fee_pct / 100.0
    before = pool.admin_fee_applies == AdminFeeApplies.before_stop
    effective = grossed * (1.0 + fee_rate) if before else grossed

    stop_monthly = pd.Series(0.0, index=months)
    if pool.method == PoolMethod.stop:
        stop_monthly = pd.Series(
            [pool.base_amount_per_area
             * _pool_denominator(pool, rentable_area, context, p, where) / 12.0
             for p in months], index=months,
        )
    elif pool.method == PoolMethod.base_year:
        spec = pool.base_year
        if spec is not None and spec.fiscal:
            raise NotImplementedError(
                f"{where}: fiscal base-year windows are not modeled "
                "(DEVIATIONS.md §10)"
            )
        if spec is not None and spec.known_amount is not None:
            # Known frozen base-year pool total ($/yr), used directly — the
            # computed window, gross-up, admin fee, and pre-analysis fallback
            # are all bypassed (spec §3.14); the figure is taken as given.
            annual = spec.known_amount
        else:
            if spec is not None and spec.lease_start_relative:
                # Base year = this segment's own start year, resolved by the
                # same shared window logic the base_year system method uses
                # [AE pp. 405-406, 408-409] — parity, not new behavior.
                window = _resolve_base_year_window(
                    None, 0, analysis_begin, where, lease_start=segment_start,
                )
            else:
                window = _resolve_base_year_window(
                    spec.year if spec is not None else None, 0,
                    analysis_begin, where,
                )
            window_gross = spec.gross_up_pct if spec is not None else None
            window_basis = _weighted_basis(weights, by_name, months,
                                           window_gross, context.occupancy,
                                           where)
            if before:
                window_basis = window_basis * (1.0 + fee_rate)
            annual = _frozen_stop_annual(window_basis, window, where)
        stop_monthly = pd.Series(annual / 12.0, index=months)

    share = pd.Series(0.0, index=months)
    pre_cap = pd.Series(0.0, index=months)
    admin_fee = pd.Series(0.0, index=months)
    if pool.method == PoolMethod.fixed:
        factors = _factor_series(pool.fixed_inflation, months, analysis_begin,
                                 inflation, default_flat=True, where=where)
        for period in months:
            if start <= period <= end:
                share[period] = 1.0  # a tenant amount [AE p. 409]
                pre_cap[period] = pool.fixed_amount / 12.0 * float(factors[period])
    else:
        for period in months:
            if not (start <= period <= end):
                continue
            if pool.pro_rata_share_override is not None:
                share_m = pool.pro_rata_share_override / 100.0
            else:
                denominator = _pool_denominator(pool, rentable_area, context,
                                                period, where)
                share_m = area / denominator
            share[period] = share_m
            excess = float(effective[period]) - float(stop_monthly[period])
            recovered = max(0.0, excess)
            if not before and fee_rate:
                admin_fee[period] = recovered * fee_rate
                recovered *= 1.0 + fee_rate
            elif before and fee_rate:
                admin_fee[period] = float(grossed[period]) * fee_rate
            pre_cap[period] = recovered * share_m

    capped = _apply_caps_floors(pre_cap, pool.caps_floors, start, end, months,
                                analysis_begin, inflation, where)
    audit = PoolAudit(
        tenant=tenant, segment_start=segment_start, start=start, end=end,
        structure=structure_name, pool=label, basis=basis, grossed=grossed,
        admin_fee=admin_fee, stop=stop_monthly, share=share,
        pre_cap=pre_cap, recovery=capped.copy(),
    )
    return capped, audit


def _structure_recoveries(structure: RecoveryStructure, tenant: str,
                          segment_start: pd.Period, area: float,
                          start: pd.Period, end: pd.Period,
                          months: pd.PeriodIndex, expenses: ExpenseSeries,
                          rentable_area: Union[pd.Series, float],
                          context: RecoveryContext,
                          analysis_begin: Optional[dt.date],
                          inflation: Optional[Inflation],
                          where: str) -> tuple[pd.Series, list[PoolAudit]]:
    by_name = {item.name: (item, series) for item, series in expenses}
    # double-counting across pools is an error too [AE p. 408]
    seen: set[str] = set()
    for i, pool in enumerate(structure.pools):
        members = set(_pool_weights(pool, context.expense_groups,
                                    f"{where} pool {i + 1}"))
        overlap = seen & members
        if overlap:
            raise ValueError(
                f"{where}: expense(s) {sorted(overlap)} appear in more than "
                "one pool of the structure — double counting [AE p. 408]"
            )
        seen |= members

    total = pd.Series(0.0, index=months, name="expense_recovery")
    audits: list[PoolAudit] = []
    for i, pool in enumerate(structure.pools):
        label = f"pool {i + 1} ({pool.method.value})"
        series, audit = _pool_recovery(
            pool, label, tenant, structure.name, segment_start, area, start,
            end, months, by_name, rentable_area, context, analysis_begin,
            inflation, f"{where} pool {i + 1}",
        )
        total = total + series
        audits.append(audit)
    return total, audits


# ------------------------------------------------------------------ #
# Dispatch over an occupancy window                                   #
# ------------------------------------------------------------------ #

def _fixed_annual_series(assignment: RecoveryAssignment, area: float,
                         months: pd.PeriodIndex,
                         analysis_begin: Optional[dt.date],
                         inflation: Optional[Inflation],
                         where: str) -> pd.Series:
    """The fixed method's annual tenant amount per month [AE p. 409]:
    flat unless ``fixed_inflation`` opts into an index or schedule."""
    annual = (assignment.fixed_amount
              if assignment.fixed_amount is not None
              else assignment.fixed_amount_per_area * area)
    factors = _factor_series(assignment.fixed_inflation, months,
                             analysis_begin, inflation, default_flat=True,
                             where=where)
    return annual * factors


def _window_recoveries(assignment: RecoveryAssignment, area: float,
                       start: pd.Period, end: pd.Period,
                       months: pd.PeriodIndex, expenses: ExpenseSeries,
                       rentable_area: Union[pd.Series, float], where: str,
                       analysis_begin: Optional[dt.date],
                       inflation: Optional[Inflation],
                       tenant: str, segment_start: pd.Period,
                       context: Optional[RecoveryContext],
                       abatement: Optional[pd.Series],
                       audit: Optional[list]) -> pd.Series:
    method = assignment.method
    expenses = list(expenses)
    series = pd.Series(0.0, index=months, name="expense_recovery")
    audits: list[PoolAudit] = []

    if method == RecoverySystemMethod.none:
        pass

    elif method == RecoverySystemMethod.structure:
        if context is None or assignment.structure_ref not in context.structures:
            raise ValueError(
                f"{where}: user recovery structure "
                f"{assignment.structure_ref!r} needs a RecoveryContext "
                "carrying the property's structures (run.py supplies one)"
            )
        series, audits = _structure_recoveries(
            context.structures[assignment.structure_ref], tenant,
            segment_start, area, start, end, months, expenses, rentable_area,
            context, analysis_begin, inflation, where,
        )

    elif method == RecoverySystemMethod.fixed:
        annual = _fixed_annual_series(assignment, area, months,
                                      analysis_begin, inflation, where)
        share = pd.Series(0.0, index=months)
        for period in months:
            if start <= period <= end:
                series[period] = float(annual[period]) / 12.0
                share[period] = 1.0
        audits = [PoolAudit(
            tenant=tenant, segment_start=segment_start, start=start, end=end,
            structure=None, pool="system: fixed",
            basis=pd.Series(0.0, index=months),
            grossed=pd.Series(0.0, index=months),
            admin_fee=pd.Series(0.0, index=months),
            stop=pd.Series(0.0, index=months), share=share,
            pre_cap=series.copy(), recovery=series.copy(),
        )]

    else:  # net / base_stop / base_year / base_year_plus_1
        pool = recoverable_pool(expenses, months)
        if method == RecoverySystemMethod.net:
            stop_monthly = pd.Series(0.0, index=months)
        elif method == RecoverySystemMethod.base_stop:
            # a building stop: $/SF × denominator area [AE p. 409]
            stop_monthly = pd.Series(
                [assignment.stop_amount_per_area
                 * _area_at(rentable_area, p) / 12.0 for p in months],
                index=months,
            )
        else:  # base_year / base_year_plus_1
            if assignment.base_year_amount is not None:
                # Known frozen base-year pool total ($/yr), used directly —
                # the computed window and pre-analysis fallback are bypassed
                # (spec §3.14); base_year_gross_up_pct does not apply to an
                # already-known figure.
                annual = assignment.base_year_amount
            else:
                plus = (12 if method == RecoverySystemMethod.base_year_plus_1
                        else 0)
                window = _resolve_base_year_window(
                    assignment.base_year, plus, analysis_begin, where,
                    lease_start=start,
                )
                if assignment.base_year_gross_up_pct is not None:
                    if context is None:
                        raise ValueError(
                            f"{where}: base-year gross-up needs a "
                            "RecoveryContext carrying the occupancy series"
                        )
                    window_basis = pd.Series(0.0, index=months)
                    for item, item_series in expenses:
                        if item.is_recoverable:
                            window_basis += _grossed_series(
                                item,
                                item_series.reindex(months, fill_value=0.0),
                                context.occupancy,
                                assignment.base_year_gross_up_pct, where,
                            )
                else:
                    window_basis = pool
                annual = _frozen_stop_annual(window_basis, window, where)
            stop_monthly = pd.Series(annual / 12.0, index=months)
        share = pd.Series(0.0, index=months)
        for period in months:
            if start <= period <= end:
                share_m = area / _area_at(rentable_area, period)
                share[period] = share_m
                excess = float(pool[period]) - float(stop_monthly[period])
                series[period] = max(0.0, excess) * share_m  # never pay the stop
        audits = [PoolAudit(
            tenant=tenant, segment_start=segment_start, start=start, end=end,
            structure=None, pool=f"system: {method.value}",
            basis=pool.copy(), grossed=pool.copy(),
            admin_fee=pd.Series(0.0, index=months), stop=stop_monthly,
            share=share, pre_cap=series.copy(), recovery=series.copy(),
        )]

    if abatement is not None:
        multiplier = (1.0 - abatement.reindex(months, fill_value=0.0)).clip(
            lower=0.0
        )
        series = series * multiplier
        for entry in audits:
            entry.recovery = entry.recovery * multiplier
    if audit is not None:
        audit.extend(audits)
    return series


def project_recoveries(lease: Lease, months: pd.PeriodIndex,
                       expenses: ExpenseSeries,
                       rentable_area: Union[pd.Series, float],
                       analysis_begin: Optional[dt.date] = None,
                       inflation: Optional[Inflation] = None,
                       context: Optional[RecoveryContext] = None,
                       abatement: Optional[pd.Series] = None,
                       audit: Optional[list] = None) -> pd.Series:
    """Project one lease's contract-term expense recoveries onto the
    monthly timeline (spec §4.1 step 6) per its assignment — system
    methods [AE pp. 405-406, 408-409] or a user structure via ``context``
    (spec §3.14). ``abatement`` is a free-rent fraction series applied
    when the lease's profile abates recoveries [AE p. 254]; ``audit``
    collects ``PoolAudit`` entries for the Recovery Audit report."""
    start, end = lease_term_periods(lease)
    return _window_recoveries(
        lease.recoveries, lease.area, start, end, months, expenses,
        rentable_area, where=f"lease {lease.tenant_name!r}",
        analysis_begin=analysis_begin, inflation=inflation,
        tenant=lease.tenant_name, segment_start=start, context=context,
        abatement=abatement, audit=audit,
    )


def project_segment_recoveries(segment, months: pd.PeriodIndex,
                               expenses: ExpenseSeries,
                               rentable_area: Union[pd.Series, float],
                               analysis_begin: Optional[dt.date] = None,
                               inflation: Optional[Inflation] = None,
                               context: Optional[RecoveryContext] = None,
                               abatement: Optional[pd.Series] = None,
                               audit: Optional[list] = None) -> pd.Series:
    """Recoveries for one resolved lease segment (contract or speculative).
    The segment's own ``RecoveryAssignment`` governs — speculative
    segments recover per their MLP (spec §3.6 [AE pp. 239-240]); a
    base-year segment's base year is its own start year (each segment is
    a new lease; the manual's Continue Prior carry-over is not modeled,
    DEVIATIONS.md §7). Recoveries post over occupied months only:
    downtime months post nothing (golden #1's FY2029 confirms)."""
    return _window_recoveries(
        segment.recoveries, segment.area, segment.start, segment.end,
        months, expenses, rentable_area,
        where=f"lease {segment.lease.tenant_name!r} segment {segment.start}",
        analysis_begin=analysis_begin, inflation=inflation,
        tenant=segment.lease.tenant_name, segment_start=segment.start,
        context=context, abatement=abatement, audit=audit,
    )
