"""Valuation report family (Phase 4 Step 3; spec §7 reports 5-6, 8-9)
[AE pp. 550-572]:

* **#5 IRR Matrix** — IRR grid over price × exit cap
  (:func:`irr_matrix`; unleveraged or leveraged).
* **#6 Value Matrix** — PV grid over discount rate × exit cap
  (:func:`value_matrix`).
* **#8 Valuation & Return Summary** — the ValuationResult metrics as a
  labeled cascade (:func:`valuation_summary`).
* **#9 Present Value report** — per-period cash flow, discount factor, and
  present value, reconciling to the ValuationResult PV
  (:func:`present_value`).

These are **thin views over data already on ``RunResult``** — the
sensitivity matrices (Step 6), the ValuationResult (Step 5), and the
valuation helpers — so each reconciles to its source exactly and the
ledger is never recomputed (spec §4.1). Reports #5/#6 render NaN cells as
blanks (non-conventional-IRR or no-loan cells — never a silent zero,
Step 5's convention).

**EXTERNALLY UNVALIDATED** like everything valuation-shaped: no golden
populates ``valuation`` and none will (no OM publishes a valuation result,
verified 2026-07-11). Validation is RunResult reconciliation + the §21
cross-check (the IRR-matrix center cell equals the ValuationResult IRR for
a model priced at the grid's base) + the owner's Excel hand-checks
(DEVIATIONS.md §20/§21). These are presentation layers over already-tested
numbers; they add no new calculation. The engine never imports UI code
(Iron Rule 1).
"""
from __future__ import annotations

import pandas as pd

from engine.calc.ledger import CFADS, CFBDS
from engine.calc.resale import compute_resale
from engine.calc.sensitivity import _CAP_METHODS, _centered_axis
from engine.calc.valuation import (
    _PERIODS_PER_YEAR,
    _apply_loan_proceeds,
    _period_buckets,
    holding_stream,
)
from engine.reports.base import Report, ReportMeta


def _require_sensitivity(result):
    if result.sensitivity is None:
        raise ValueError(
            "this run has no sensitivity matrices — model.valuation is unset "
            "or the resale method has no exit cap (fixed_amount / "
            "pct_increase_over_price; spec §7 reports 5-6 need a cap axis)"
        )
    return result.sensitivity


def _require_valuation(result):
    if result.valuation is None:
        raise ValueError(
            "this run has no valuation (model.valuation is unset); spec §7 "
            "reports 8-9 have nothing to present"
        )
    return result.valuation


# ------------------------------------------------------------------ #
# #6 Value Matrix / #5 IRR Matrix — thin views over sensitivity       #
# ------------------------------------------------------------------ #

def value_matrix(result) -> Report:
    """Value Matrix (#6): unleveraged PV over discount rate (rows) × exit
    cap (columns), straight from ``result.sensitivity.value_matrix``
    [AE pp. 550-572]. Axis labels are percents."""
    sens = _require_sensitivity(result)
    frame = sens.value_matrix.copy()
    frame.index.name = "discount_rate_pct"
    frame.columns.name = "exit_cap_pct"
    meta = ReportMeta(
        name="Value Matrix", number=6, monetary=False,
        citation="[AE pp. 550-572]",
        extra={"axes": "discount_rate × exit_cap", "values": "unleveraged_pv"},
    )
    return Report(frame=frame, meta=meta)


def irr_matrix(result, *, leveraged: bool = False) -> Report:
    """IRR Matrix (#5): IRR grid over price (rows) × exit cap (columns)
    [AE pp. 550-572]. ``leveraged=False`` reads
    ``unleveraged_irr_matrix``; ``leveraged=True`` the leveraged grid
    (all-NaN without loans — never a silent zero). NaN cells (ambiguous
    IRR or no leverage) render blank. Axis labels: price in dollars, cap in
    percent."""
    sens = _require_sensitivity(result)
    source = (sens.leveraged_irr_matrix if leveraged
              else sens.unleveraged_irr_matrix)
    frame = source.copy()
    frame.index.name = "price"
    frame.columns.name = "exit_cap_pct"
    meta = ReportMeta(
        name=("Leveraged IRR Matrix" if leveraged else "IRR Matrix"),
        number=5, monetary=False, citation="[AE pp. 550-572]",
        extra={"axes": "price × exit_cap", "leveraged": leveraged,
               "values": "annual_nominal_irr_pct"},
    )
    return Report(frame=frame, meta=meta)


def reconcile_matrix_to_source(report: Report, result) -> pd.DataFrame:
    """Report cells minus the ``sensitivity`` matrix they view — exact
    zeros when the thin view is faithful (NaN cells compare equal). Picks
    the source matrix from ``report.meta`` (Value vs IRR, leveraged flag)."""
    sens = _require_sensitivity(result)
    if report.meta.number == 6:
        source = sens.value_matrix
    elif report.meta.extra.get("leveraged"):
        source = sens.leveraged_irr_matrix
    else:
        source = sens.unleveraged_irr_matrix
    a = report.frame.to_numpy(dtype=float)
    b = source.to_numpy(dtype=float)
    # NaN in the same cells on both sides is a match; difference elsewhere.
    diff = pd.DataFrame(a - b, index=report.frame.index,
                        columns=report.frame.columns)
    both_nan = pd.DataFrame(
        pd.isna(a) & pd.isna(b), index=report.frame.index,
        columns=report.frame.columns)
    return diff.mask(both_nan, 0.0)


# ------------------------------------------------------------------ #
# #8 Valuation & Return Summary — labeled cascade over ValuationResult #
# ------------------------------------------------------------------ #

#: Summary rows: (label, ValuationResult attribute, detail). ``None``
#: values (no loans / no price / no direct cap) render blank, not zero.
_SUMMARY_ROWS = [
    ("Discount Rate (APR %)", "discount_rate", "[AE p. 472]"),
    ("Unleveraged PV", "unleveraged_pv", "CFBDS + net resale, discounted"),
    ("Unleveraged IRR (%)", "unleveraged_irr", "annual nominal"),
    ("Unleveraged t0 outlay", "unleveraged_t0", "price + closing/financing"),
    ("Leveraged PV", "leveraged_pv", "CFADS + leveraged resale"),
    ("Leveraged IRR (%)", "leveraged_irr", "annual nominal"),
    ("Leveraged equity (t0)", "leveraged_equity", "price − day-one proceeds"),
    ("Direct Cap Value", "direct_cap_value", "[AE pp. 453-454]"),
]


def valuation_summary(result) -> Report:
    """Valuation & Return Summary (#8): the ValuationResult metrics as a
    (metric, value, detail) cascade [AE pp. 550-572]. ``None`` metrics
    (no loans / no price / no direct-cap input) carry ``NaN`` so they
    render blank rather than as a misleading zero."""
    valuation = _require_valuation(result)
    rows = []
    for label, attr, detail in _SUMMARY_ROWS:
        value = getattr(valuation, attr)
        rows.append({"metric": label,
                     "value": float("nan") if value is None else float(value),
                     "detail": detail})
    frame = pd.DataFrame(rows, columns=["metric", "value", "detail"])
    frame.attrs["discount_method"] = valuation.discount_method.value
    frame.attrs["period_convention"] = valuation.period_convention.value
    frame.attrs["pv_start"] = str(valuation.pv_start)
    meta = ReportMeta(
        name="Valuation & Return Summary", number=8, monetary=False,
        citation="[AE pp. 550-572]", extra=dict(frame.attrs),
    )
    return Report(frame=frame, meta=meta)


def reconcile_valuation_summary(report: Report, result) -> pd.Series:
    """Summary values minus the ValuationResult fields — exact zeros when
    the summary faithfully echoes the source (``None`` ↔ ``NaN`` match)."""
    valuation = _require_valuation(result)
    by_metric = report.frame.set_index("metric")["value"]
    diffs = {}
    for label, attr, _ in _SUMMARY_ROWS:
        source = getattr(valuation, attr)
        reported = float(by_metric[label])
        if source is None:
            diffs[label] = 0.0 if pd.isna(reported) else reported
        else:
            diffs[label] = reported - float(source)
    return pd.Series(diffs)


# ------------------------------------------------------------------ #
# #9 Present Value report — per-period CF, discount factor, PV        #
# ------------------------------------------------------------------ #

def present_value(result, *, leveraged: bool = False) -> Report:
    """Present Value report (#9): one row per discount period with the
    period's cash flow, the discount factor, and the present value —
    exposing the per-period factors the valuation helpers apply
    [AE pp. 550-572]. The ``present_value`` column **sums to the
    ValuationResult PV** (:func:`reconcile_present_value`).

    Unleveraged uses CFBDS + the net resale over the holding period;
    leveraged uses CFADS + the leveraged resale with staged loan draws
    posted at funding (mirroring ``compute_valuation`` exactly). Leveraged
    requires loans (raises otherwise — no silent empty report)."""
    valuation = _require_valuation(result)
    if result.resale is None:
        raise ValueError("this run has no resale; the PV stream is undefined")
    frame = result.ledger.frame
    resale = result.resale
    method = valuation.discount_method
    p = _PERIODS_PER_YEAR[method]
    periodic = (valuation.discount_rate / 100.0) / p

    if leveraged:
        if not result.loan_schedules:
            raise ValueError(
                "leveraged Present Value needs loans; this run has none "
                "(unleveraged PV is always available)")
        stream = holding_stream(frame[CFADS], resale.net_leveraged,
                                resale.resale_month)
        stream, _ = _apply_loan_proceeds(stream, result.loan_schedules,
                                         valuation.pv_start, resale.resale_month)
    else:
        stream = holding_stream(frame[CFBDS], resale.net_unleveraged,
                                resale.resale_month)

    buckets = _period_buckets(stream, valuation.pv_start, method,
                              valuation.period_convention)
    rows = []
    for index, (exponent, amount) in enumerate(buckets, start=1):
        factor = 1.0 / (1.0 + periodic) ** exponent
        rows.append({
            "period": index, "exponent": exponent, "cash_flow": amount,
            "discount_factor": factor, "present_value": amount * factor,
        })
    frame_out = pd.DataFrame(
        rows, columns=["period", "exponent", "cash_flow", "discount_factor",
                       "present_value"])
    meta = ReportMeta(
        name=("Leveraged Present Value" if leveraged else "Present Value"),
        number=9, monetary=False, citation="[AE pp. 550-572]",
        extra={"leveraged": leveraged,
               "discount_rate_pct": valuation.discount_rate,
               "discount_method": method.value,
               "period_convention": valuation.period_convention.value,
               "pv_start": str(valuation.pv_start)},
    )
    return Report(frame=frame_out, meta=meta)


def reconcile_present_value(report: Report, result) -> float:
    """The report's total present value minus the ValuationResult PV
    (unleveraged or leveraged per the report) — ~0 when reconciled. Proves
    the per-period breakdown ties to the single-figure PV Step 5 computed."""
    valuation = _require_valuation(result)
    leveraged = report.meta.extra.get("leveraged", False)
    target = valuation.leveraged_pv if leveraged else valuation.unleveraged_pv
    if target is None:
        raise ValueError("the ValuationResult has no PV for this report")
    return float(report.frame["present_value"].sum()) - float(target)


# ------------------------------------------------------------------ #
# #7 Resale Matrix — net resale over exit cap × resale year           #
# ------------------------------------------------------------------ #

def _resale_year_ends(result, model) -> list[tuple[int, "pd.Period"]]:
    """``(analysis_year, year-end month)`` for each analysis year — the
    candidate resale dates (each year's end is a valid saleable month; year
    N's end is the analysis end, spec §2.3). The resale-year axis of the
    Resale Matrix."""
    begin = result.months[0]
    n = model.property.analysis_term_years
    return [(k, begin + 12 * k - 1) for k in range(1, n + 1)]


def resale_matrix(result, model) -> Report:
    """Resale Matrix (#7): net (unleveraged) resale proceeds over **resale
    year (rows) × exit cap (columns)** [AE pp. 550-572]. A NEW resale-year
    axis — each cell re-runs Step 4's :func:`compute_resale` at that year's
    end and that exit cap against the existing ledger (the ledger is never
    recomputed, spec §4.1; the §21 cross-check pattern — each cell equals a
    direct single-point resale). The cap axis is centered on the base exit
    cap with the sensitivity intervals, matching the Value/IRR matrices.

    Needs a cap-rate resale method (the exit-cap axis is meaningless for
    ``fixed_amount`` / ``pct_increase_over_price``); raises otherwise."""
    if model.valuation is None:
        raise ValueError(
            "this run has no valuation (model.valuation is unset); the Resale "
            "Matrix has nothing to sweep")
    valuation = model.valuation
    base = valuation.resale
    if base.method not in _CAP_METHODS:
        raise ValueError(
            "the Resale Matrix sweeps exit cap × resale year, so it needs a "
            f"cap-rate resale method; method {base.method.value!r} has no "
            "exit cap (fixed_amount / pct_increase_over_price)")
    year_ends = _resale_year_ends(result, model)
    intervals = valuation.sensitivity_intervals
    cap_axis = _centered_axis(base.exit_cap_rate, intervals.cap_rate_step,
                              intervals.count)
    data = {}
    for cap in cap_axis:
        column = {}
        for year, end in year_ends:
            substituted = base.model_copy(update={
                "exit_cap_rate": cap,
                "resale_date": end.to_timestamp().date(),
            })
            resale = compute_resale(substituted, result.ledger, result.months,
                                    result.occupancy, model,
                                    result.loan_schedules)
            column[year] = resale.net_unleveraged
        data[cap] = column
    frame = pd.DataFrame(data, index=[y for y, _ in year_ends], columns=cap_axis)
    frame.index.name = "resale_year"
    frame.columns.name = "exit_cap_pct"
    meta = ReportMeta(
        name="Resale Matrix", number=7, monetary=False,
        citation="[AE pp. 550-572]",
        extra={"axes": "resale_year × exit_cap",
               "values": "net_unleveraged_resale",
               "base_exit_cap": base.exit_cap_rate,
               "resale_months": {y: str(e) for y, e in year_ends}})
    return Report(frame=frame, meta=meta)


def reconcile_resale_matrix(report: Report, result, model) -> pd.Series:
    """Two failable checks (not a self-subtraction): (a) an **independent
    anchor** — the cell at the base exit cap and the resale year matching
    the run's own resale month equals ``result.resale.net_unleveraged`` (the
    already-computed RunResult resale the matrix did not produce); (b)
    **monotonicity** — within every resale-year row, net resale strictly
    decreases as the exit cap rises (value = income / cap). Returns the
    anchor diff and a count of monotonicity violations."""
    base_cap = model.valuation.resale.exit_cap_rate
    resale_month = str(result.resale.resale_month)
    anchor_year = next(
        (y for y, m in report.meta.extra["resale_months"].items()
         if m == resale_month), None)
    if anchor_year is None:
        anchor_diff = float("nan")  # custom resale date not on a year-end
    else:
        anchor_diff = (float(report.frame.loc[anchor_year, base_cap])
                       - float(result.resale.net_unleveraged))
    violations = 0
    for _year, row in report.frame.iterrows():
        values = list(row.values)
        if any(b >= a for a, b in zip(values, values[1:])):
            violations += 1
    return pd.Series({"anchor_diff": anchor_diff,
                      "monotonicity_violations": float(violations)})
