"""Report-builder contract + the unit / period / rounding engine (Phase 4
Step 1; spec §7 intro, §4.3).

Spec §7: "Every report is a builder function returning ``(DataFrame,
metadata)``; the UI renders and the exporter writes it. All monetary
reports respect the PSF/unit toggle." This module is the shared layer
every §7 report sits on:

* :class:`Report` — the ``(frame, metadata)`` a builder returns (a small
  dataclass, unpackable as ``frame, meta = report`` so callers may treat
  it as the spec's tuple).
* :class:`Unit` / :class:`Period` — the global toggles (spec §7 intro,
  §6 tab 8): Total $ / $ per SF / per-month / per-occupied-SF, and
  monthly / quarterly / annual / fiscal.
* :func:`aggregate_period` / :func:`apply_unit` / :func:`apply_rounding`
  — reusable transforms over a monetary monthly DataFrame, built on the
  existing ledger aggregations (:func:`engine.calc.ledger.to_annual` &c.)
  and the run's area series. Full precision inside; rounding is
  report-level only (§4.3 — never round the ledger).
* :func:`build_monetary_report` — ties them together for the account-tree
  monetary reports (Cash Flow &c., Phase 4 Step 2+).

**The toggles (spec §7 intro; the plan's definitions).** A *monetary*
report is a monthly DataFrame (one column per account, Period[M] index).

* **Period** aggregates the monthly frame with the ledger's own
  aggregations, so the §9.3 identity **sum(monthly) = annual = fiscal**
  holds for the Total-$ representation (asserted in tests, and by
  :func:`assert_period_consistency`).
* **Unit** then re-expresses each period figure:

  ===================  ==========================================
  ``Unit.total``       the period $ as-is
  ``Unit.per_sf``      period $ ÷ the period's mean rentable SF
  ``Unit.per_month``   period $ ÷ the period's month count
  ``Unit.per_occ_sf``  period $ ÷ the period's mean occupied SF
  ===================  ==========================================

  Per-SF and per-occupied-SF divide by the **mean** area over the
  period's months (area varies month to month via schedules / rollover);
  per-month divides by the month count (which correctly handles partial
  first/last fiscal years). Dividing by area breaks additivity, so the
  sum(monthly)=annual identity is a property of the Total-$ view only —
  the unit transform is a presentation layer over it.

:class:`ModelingPolicies` (§4.3) carries the report-layer rounding
policy. Its default and the adjacent ARGUS policy defaults are the
manual's stated defaults [AE pp. 504-527] — see the class docstring.

The audit reports (Lease/Recovery/Resale, §7 reports 16/18/21) are
per-tenant / per-line detail, not account-tree ledger views; they conform
to the :class:`Report` contract via the thin wrappers in their own
modules (``*_report``) and are marked ``monetary=False`` so the unit /
period toggles pass them through untouched — their reconciliation
helpers are unchanged. The engine never imports UI code (Iron Rule 1).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator, Optional

import numpy as np
import pandas as pd

from engine.calc.ledger import to_annual, to_fiscal_annual, to_quarterly
from engine.calc.timeline import analysis_year_of, fiscal_year_of


class Unit(str, Enum):
    """The global unit toggle (spec §7 intro; CLAUDE.md Conventions).

    ``total`` Total $ · ``per_sf`` $ per SF · ``per_month`` per-month ·
    ``per_occ_sf`` per-occupied-SF. Non-monetary reports (counts, %) ignore
    the toggle (they always render ``total``)."""

    total = "total"
    per_sf = "per_sf"
    per_month = "per_month"
    per_occ_sf = "per_occupied_sf"


class Period(str, Enum):
    """The global period toggle (spec §7 intro; §3.1). Aggregations of the
    monthly ledger, never separately computed (spec §2.3)."""

    monthly = "monthly"
    quarterly = "quarterly"
    annual = "annual"
    fiscal = "fiscal"


class Rounding(str, Enum):
    """Report-level rounding (§4.3). ARGUS default is ``none`` — every
    Rounding option in Modeling Policies defaults to None [AE p. 508]. The
    engine always computes full precision; this rounds the displayed frame
    only (never the ledger)."""

    none = "none"
    nearest_dollar = "nearest_dollar"


@dataclass(frozen=True)
class ModelingPolicies:
    """Report/calculation policy defaults (spec §4.3 [AE pp. 504-527]).

    Phase 4 Step 1 wires the one policy the report layer consumes —
    ``rounding`` — defaulting to ARGUS's stated default (``none``; the
    Rounding section's Vendor's Cost Net / AREA ERV / 'Say' Value options
    all default to None [AE p. 508]). Report-level only; never round the
    ledger (§4.3).

    The other Modeling-Policies defaults the manual states are already the
    engine's fixed behavior and are recorded here for owner visibility
    rather than re-plumbed (they have no separate consumer — adding dead
    toggles would violate "no silent numbers"):

    * General Vacancy & Credit Loss **Calculation Frequency = Monthly**,
      Calculation Month = Analysis Date [AE pp. 506-507] — the engine
      computes GV/CL monthly inside the fixed point (run.py).
    * **Apply Admin Fees As = % of Recoverable Expenses** [AE p. 520] —
      the recoveries default (engine/calc/recoveries.py).
    * Monthly Detail Inflation = **Nominal Growth Factors** [AE p. 507];
      Inflate Market Rates monthly from month 2 — the inflation module's
      behavior (engine/calc/inflation.py).
    * Rent for CPI Increases = **Rent in Prior 12 Months** [AE p. 514];
      Timing for CPI = Analysis Begin (``Inflation.timing_basis``).
    * Base Rent Input = Amount/SF/Year, Calculate Potential Rent = Base
      Rent, TIs/LCs as **Capital Expenses** [AE pp. 512-515] — the
      posting the ledger already uses (above no line for TI/LC, below NOI).

    Future steps add a policy field here only when a real consumer needs
    it to vary (e.g. the UK/traditional-valuation and multifamily toggles
    are permanently out of scope — spec §1.2)."""

    rounding: Rounding = Rounding.none


@dataclass
class ReportMeta:
    """Report metadata carried alongside the DataFrame (spec §7). ``name``
    and ``number`` identify the §7 catalog entry; ``unit``/``period``/
    ``rounding`` record the view produced; ``monetary`` is False for the
    audit / count reports the unit toggle does not apply to; ``denominator``
    names the per-period divisor series used (None for Total $); ``extra``
    holds per-report notes (citations, flags)."""

    name: str
    number: int
    unit: Unit = Unit.total
    period: Period = Period.monthly
    rounding: Rounding = Rounding.none
    monetary: bool = True
    citation: str = ""
    denominator: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class Report:
    """A built report: the ``(DataFrame, metadata)`` of spec §7. Unpackable
    as ``frame, meta = report`` so a caller may treat it as the spec's
    tuple, while ``.frame`` / ``.meta`` read clearly."""

    frame: pd.DataFrame
    meta: ReportMeta

    def __iter__(self) -> Iterator:
        yield self.frame
        yield self.meta


# ------------------------------------------------------------------ #
# Period grouping (shared labels so money and denominators align)     #
# ------------------------------------------------------------------ #

def _period_labels(index: pd.PeriodIndex, period: Period, *,
                   analysis_begin: dt.date,
                   fiscal_year_end_month: int) -> list:
    """The group label per month for ``period`` — identical to the labels
    the ledger aggregations use, so a money aggregation and its area
    denominator share the exact same result index (spec §2.3)."""
    if period == Period.monthly:
        return list(index)
    if period == Period.quarterly:
        return list(index.asfreq("Q"))
    if period == Period.annual:
        return [analysis_year_of(analysis_begin, p) for p in index]
    if period == Period.fiscal:
        return [fiscal_year_of(p, fiscal_year_end_month) for p in index]
    raise ValueError(f"unknown period {period!r}")


def aggregate_period(frame: pd.DataFrame, period: Period, *,
                     analysis_begin: dt.date,
                     fiscal_year_end_month: int = 12) -> pd.DataFrame:
    """Aggregate a monthly monetary frame to ``period`` using the ledger's
    own aggregations (spec §2.3 — aggregations of the monthly ledger, never
    separately computed). Monthly returns the frame unchanged."""
    if period == Period.monthly:
        return frame.copy()
    if period == Period.quarterly:
        return to_quarterly(frame)
    if period == Period.annual:
        return to_annual(frame, analysis_begin)
    if period == Period.fiscal:
        return to_fiscal_annual(frame, fiscal_year_end_month)
    raise ValueError(f"unknown period {period!r}")


def period_month_counts(index: pd.PeriodIndex, period: Period, *,
                        analysis_begin: dt.date,
                        fiscal_year_end_month: int = 12) -> pd.Series:
    """Number of months in each aggregation group (the per-month divisor).
    Handles partial first/last fiscal years correctly (a short group
    divides by its actual month count)."""
    labels = _period_labels(index, period, analysis_begin=analysis_begin,
                            fiscal_year_end_month=fiscal_year_end_month)
    return pd.Series(1.0, index=index).groupby(labels).sum()


def period_mean_area(area: pd.Series, period: Period, *,
                     analysis_begin: dt.date,
                     fiscal_year_end_month: int = 12) -> pd.Series:
    """Mean area over each aggregation group's months (the per-SF divisor).
    Area varies month to month (schedule / rollover), so a period figure
    divides by the period's average area."""
    labels = _period_labels(area.index, period, analysis_begin=analysis_begin,
                            fiscal_year_end_month=fiscal_year_end_month)
    return area.groupby(labels).mean()


# ------------------------------------------------------------------ #
# Unit + rounding transforms                                          #
# ------------------------------------------------------------------ #

def apply_unit(aggregated: pd.DataFrame, unit: Unit, *,
               month_counts: pd.Series,
               rentable_mean: pd.Series,
               occupied_mean: pd.Series) -> pd.DataFrame:
    """Re-express a period-aggregated Total-$ frame in ``unit``. The three
    divisor series are indexed to match ``aggregated`` (per :func:`
    period_month_counts` / :func:`period_mean_area`). Division by zero
    area yields NaN (a genuinely undefined per-SF figure — e.g. a
    fully-vacant period per occupied SF — not a silent zero)."""
    if unit == Unit.total:
        return aggregated.copy()
    if unit == Unit.per_month:
        divisor = month_counts
    elif unit == Unit.per_sf:
        divisor = rentable_mean
    elif unit == Unit.per_occ_sf:
        divisor = occupied_mean
    else:
        raise ValueError(f"unknown unit {unit!r}")
    divisor = divisor.reindex(aggregated.index)
    safe = divisor.replace(0.0, np.nan)
    return aggregated.div(safe, axis=0)


def apply_rounding(frame: pd.DataFrame, rounding: Rounding) -> pd.DataFrame:
    """Report-level rounding (§4.3). ``none`` (the ARGUS default,
    [AE p. 508]) passes through at full precision; ``nearest_dollar``
    rounds to whole units. Applies to the displayed frame only — the
    ledger is never rounded."""
    if rounding == Rounding.none:
        return frame
    if rounding == Rounding.nearest_dollar:
        return frame.round(0)
    raise ValueError(f"unknown rounding {rounding!r}")


# ------------------------------------------------------------------ #
# High-level monetary-report assembly                                 #
# ------------------------------------------------------------------ #

def build_monetary_report(monthly: pd.DataFrame, *, name: str, number: int,
                          result, unit: Unit = Unit.total,
                          period: Period = Period.monthly,
                          policies: Optional[ModelingPolicies] = None,
                          analysis_begin: dt.date,
                          fiscal_year_end_month: int = 12,
                          citation: str = "") -> Report:
    """Assemble a monetary report from a monthly Total-$ frame: aggregate to
    ``period``, re-express in ``unit`` against the run's area series, apply
    report-level rounding, and return a :class:`Report`. The shared path
    every §7 monetary report (Cash Flow &c.) uses so the toggles behave
    identically everywhere.

    ``result`` supplies the ``rentable_area`` / ``occupied_area`` series for
    the per-SF / per-occupied-SF denominators (:class:`
    engine.calc.run.RunResult`, or any object exposing those Series over the
    same month index)."""
    policies = policies or ModelingPolicies()
    aggregated = aggregate_period(monthly, period,
                                  analysis_begin=analysis_begin,
                                  fiscal_year_end_month=fiscal_year_end_month)
    counts = period_month_counts(monthly.index, period,
                                 analysis_begin=analysis_begin,
                                 fiscal_year_end_month=fiscal_year_end_month)
    rentable = period_mean_area(result.rentable_area, period,
                                analysis_begin=analysis_begin,
                                fiscal_year_end_month=fiscal_year_end_month)
    occupied = period_mean_area(result.occupied_area, period,
                                analysis_begin=analysis_begin,
                                fiscal_year_end_month=fiscal_year_end_month)
    framed = apply_unit(aggregated, unit, month_counts=counts,
                        rentable_mean=rentable, occupied_mean=occupied)
    framed = apply_rounding(framed, policies.rounding)
    denominator = {
        Unit.total: None, Unit.per_sf: "rentable_area",
        Unit.per_month: "month_count", Unit.per_occ_sf: "occupied_area",
    }[unit]
    meta = ReportMeta(name=name, number=number, unit=unit, period=period,
                      rounding=policies.rounding, monetary=True,
                      citation=citation, denominator=denominator)
    return Report(frame=framed, meta=meta)


def assert_period_consistency(monthly: pd.DataFrame, *, analysis_begin: dt.date,
                              fiscal_year_end_month: int = 12,
                              atol: float = 1e-6) -> None:
    """Assert sum(monthly) == annual == fiscal == quarterly totals for
    every account (§9.3), raising ``ValueError`` naming the first view that
    disagrees. The Total-$ representation is the additive one; the unit
    transforms are presentation over it."""
    monthly_totals = monthly.sum()
    for period in (Period.annual, Period.quarterly, Period.fiscal):
        view = aggregate_period(monthly, period, analysis_begin=analysis_begin,
                                fiscal_year_end_month=fiscal_year_end_month)
        if not np.allclose(view.sum().to_numpy(dtype=float),
                           monthly_totals.to_numpy(dtype=float), atol=atol):
            raise ValueError(
                f"period-consistency invariant violated: sum(monthly) != "
                f"sum({period.value}) aggregation (spec §9.3)"
            )
