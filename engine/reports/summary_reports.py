"""Summary / echo reports (Phase 4 Step 5; spec §7 reports 2-4, 23)
[AE pp. 535-549]:

* **#2 Executive Summary** — key assumptions, year-1 metrics, valuation
  results (:func:`executive_summary`).
* **#4 Sources & Uses** — acquisition through disposition, tying to the
  below-the-line ledger columns (:func:`sources_and_uses`).
* **#3 Assumptions Report** / **#23 Input Assumptions listing** — the model
  input echo, sectioned (:func:`assumptions_report`) and flat
  (:func:`input_assumptions_listing`); the two overlap by design (spec §7).

All are views over the assembled ``RunResult`` and the input ``model`` — no
new calculation. Each reconciles to its source: the Executive Summary's
year-1 NOI to the ledger's annual view and its valuation figures to the
ValuationResult; Sources & Uses to the below-the-line ledger columns
(purchase / closing / debt funding / resale). Building **area** is the run's
rentable area (the stated building metric), never a summed-contract-area
(DEVIATIONS.md §25); occupancy is the corrected occupancy series.

Count/echo reports — not $-unit-toggled (``monetary=False``). The engine
never imports UI code (Iron Rule 1).
"""
from __future__ import annotations

import pandas as pd

from engine.calc.ledger import (
    CFBDS,
    CLOSING_COSTS,
    DEBT_FUNDING,
    EGR,
    LOAN_COSTS,
    LOAN_PAYOFF_AT_RESALE,
    NET_RESALE_PROCEEDS,
    NOI,
    PURCHASE_PRICE,
    to_annual,
)
from engine.reports.base import Report, ReportMeta


def _analysis_begin(result):
    return result.months[0].to_timestamp().date()


def _year1(result) -> pd.Series:
    """The analysis-year-1 column of the ledger's annual aggregation."""
    annual = to_annual(result.ledger.frame, _analysis_begin(result))
    return annual.loc[1]


# ------------------------------------------------------------------ #
# #4 Sources & Uses                                                   #
# ------------------------------------------------------------------ #

#: Sources & Uses rows backed by a ledger column: (phase, category, item,
#: ledger account, sign to turn the column sum into a positive magnitude).
_SU_LEDGER_ROWS = [
    ("Acquisition", "use", "Purchase Price", PURCHASE_PRICE, -1.0),
    ("Acquisition", "use", "Closing Costs", CLOSING_COSTS, -1.0),
    ("Acquisition", "use", "Financing Costs", LOAN_COSTS, -1.0),
    ("Acquisition", "source", "Loan Proceeds", DEBT_FUNDING, +1.0),
    ("Disposition", "source", "Net Resale Proceeds", NET_RESALE_PROCEEDS, +1.0),
    ("Disposition", "use", "Loan Payoff at Resale", LOAN_PAYOFF_AT_RESALE, -1.0),
]

SU_COLUMNS = ["phase", "category", "item", "amount"]


def sources_and_uses(result) -> Report:
    """Sources & Uses (#4): acquisition through disposition [AE pp. 535-549].
    Each dollar line ties to a below-the-line ledger column; **Equity** is
    the balancing plug so acquisition sources equal acquisition uses (loan
    proceeds + equity = purchase + closing + financing). Zero lines are
    omitted (Equity and Purchase Price always shown)."""
    frame = result.ledger.frame

    def magnitude(account, sign):
        # + 0.0 normalizes -0.0 (a no-purchase / no-debt column) to 0.0
        return sign * float(frame[account].sum()) + 0.0

    rows = []
    acq_uses = 0.0
    loan_proceeds = 0.0
    for phase, category, item, account, sign in _SU_LEDGER_ROWS:
        amount = magnitude(account, sign)
        if phase == "Acquisition" and category == "use":
            acq_uses += amount
        if item == "Loan Proceeds":
            loan_proceeds = amount
        if amount or item == "Purchase Price":
            rows.append({"phase": phase, "category": category,
                         "item": item, "amount": amount})
    # Equity plug balances acquisition sources to uses.
    equity = acq_uses - loan_proceeds
    rows.insert(
        _insert_after_acquisition_sources(rows),
        {"phase": "Acquisition", "category": "source", "item": "Equity",
         "amount": equity})

    out = pd.DataFrame(rows, columns=SU_COLUMNS)
    acq = out[out["phase"] == "Acquisition"]
    meta = ReportMeta(
        name="Sources & Uses", number=4, monetary=False,
        citation="[AE pp. 535-549]",
        extra={
            "equity": equity,
            "acquisition_uses": float(acq[acq["category"] == "use"]["amount"].sum()),
            "acquisition_sources": float(
                acq[acq["category"] == "source"]["amount"].sum()),
        })
    return Report(frame=out, meta=meta)


def _insert_after_acquisition_sources(rows) -> int:
    """Index at which to insert Equity — right after Loan Proceeds if
    present, else after the last acquisition-use row."""
    for i, row in enumerate(rows):
        if row["item"] == "Loan Proceeds":
            return i + 1
    last_acq_use = 0
    for i, row in enumerate(rows):
        if row["phase"] == "Acquisition" and row["category"] == "use":
            last_acq_use = i + 1
    return last_acq_use


def reconcile_sources_and_uses(report: Report, result) -> pd.Series:
    """Each ledger-backed row minus its below-the-line ledger column
    magnitude (exact zeros when reconciled), plus the acquisition
    sources-equal-uses balance. Capable of failing if a line drifts from
    its column or the equity plug does not balance."""
    frame = result.ledger.frame
    by_item = report.frame.set_index("item")["amount"]
    diffs = {}
    for _phase, _cat, item, account, sign in _SU_LEDGER_ROWS:
        if item in by_item.index:
            diffs[item] = float(by_item[item]) - sign * float(frame[account].sum())
    acq = report.frame[report.frame["phase"] == "Acquisition"]
    diffs["acquisition_balance"] = (
        float(acq[acq["category"] == "source"]["amount"].sum())
        - float(acq[acq["category"] == "use"]["amount"].sum()))
    return pd.Series(diffs)


# ------------------------------------------------------------------ #
# #2 Executive Summary                                                #
# ------------------------------------------------------------------ #

def executive_summary(result, model) -> Report:
    """Executive Summary (#2): key assumptions, year-1 metrics, and
    valuation results as a (metric, value, detail) cascade
    [AE pp. 535-549]. ``None`` valuation metrics render as ``NaN`` (blank),
    never a misleading zero. Building area is the run's **rentable area**
    (the stated building metric, not a summed contract area — DEVIATIONS
    §25)."""
    prop = model.property
    rentable = float(result.rentable_area.iloc[0])
    y1 = _year1(result)
    # year-1 average occupancy = mean occupied / mean rentable over months 1-12
    occ_y1 = (float(result.occupied_area.iloc[:12].mean())
              / float(result.rentable_area.iloc[:12].mean()))
    price = (model.purchase.price
             if model.purchase is not None and model.purchase.price is not None
             else None)
    going_in_cap = (float(y1[NOI]) / price * 100.0
                    if price not in (None, 0) else None)
    val = result.valuation
    resale = result.resale

    def num(x):
        return float("nan") if x is None else float(x)

    rows = [
        ("Property Name", prop.name, "", "property"),
        ("Property Type", prop.property_type.value, "", "property"),
        ("Analysis Begin", str(prop.analysis_begin), "", "property"),
        ("Analysis Term (years)", float(prop.analysis_term_years), "", "property"),
        ("Rentable Area (SF)", rentable, "stated building area", "property"),
        ("Year-1 Occupancy (%)", occ_y1 * 100.0, "mean occupied / rentable",
         "year1"),
        ("Year-1 EGR", num(y1[EGR]), "", "year1"),
        ("Year-1 NOI", num(y1[NOI]), "", "year1"),
        ("Year-1 Cash Flow (CFBDS)", num(y1[CFBDS]), "", "year1"),
        ("Purchase Price", num(price), "", "investment"),
        ("Going-in Cap Rate (%)", num(going_in_cap), "Year-1 NOI / price",
         "investment"),
    ]
    if val is not None:
        rows += [
            ("Unleveraged PV", num(val.unleveraged_pv), "", "valuation"),
            ("Unleveraged IRR (%)", num(val.unleveraged_irr), "annual nominal",
             "valuation"),
            ("Leveraged PV", num(val.leveraged_pv), "", "valuation"),
            ("Leveraged IRR (%)", num(val.leveraged_irr), "annual nominal",
             "valuation"),
            ("Direct Cap Value", num(val.direct_cap_value), "", "valuation"),
        ]
    if resale is not None:
        rows += [
            ("Net Resale Proceeds", num(resale.net_unleveraged),
             f"at {resale.resale_month}", "valuation"),
            ("Exit Cap Rate (%)", num(model.valuation.resale.exit_cap_rate),
             "", "valuation"),
        ]
    out = pd.DataFrame(
        [{"metric": m, "value": v, "detail": d, "section": s}
         for m, v, d, s in rows],
        columns=["metric", "value", "detail", "section"])
    meta = ReportMeta(name="Executive Summary", number=2, monetary=False,
                      citation="[AE pp. 535-549]",
                      extra={"has_valuation": val is not None})
    return Report(frame=out, meta=meta)


def reconcile_executive_summary(report: Report, result, model) -> pd.Series:
    """Key Executive-Summary metrics minus their independent sources — the
    ledger's own annual view and the ValuationResult — exact zeros when the
    summary echoes them faithfully."""
    by_metric = report.frame.set_index("metric")["value"]
    y1 = _year1(result)
    diffs = {
        "rentable_area": float(by_metric["Rentable Area (SF)"])
        - float(result.rentable_area.iloc[0]),
        "year1_noi": float(by_metric["Year-1 NOI"]) - float(y1[NOI]),
        "year1_egr": float(by_metric["Year-1 EGR"]) - float(y1[EGR]),
    }
    if result.valuation is not None:
        diffs["unleveraged_pv"] = (float(by_metric["Unleveraged PV"])
                                   - float(result.valuation.unleveraged_pv))
    return pd.Series(diffs)


# ------------------------------------------------------------------ #
# #3 Assumptions Report / #23 Input Assumptions listing               #
# ------------------------------------------------------------------ #

def _model_assumptions(model) -> list[tuple[str, str, object]]:
    """(section, assumption, value) rows echoing the model's key scalar
    inputs — the shared basis of the Assumptions Report (#3, sectioned) and
    the Input Assumptions listing (#23, flat). Big collections (rent roll,
    expenses, loans) are summarized by count; their detail has its own
    reports (Lease Summary #11, Loan Amortization #20)."""
    prop = model.property
    am = model.area_measures
    rows: list[tuple[str, str, object]] = [
        ("Property", "Name", prop.name),
        ("Property", "Type", prop.property_type.value),
        ("Property", "Analysis Begin", str(prop.analysis_begin)),
        ("Property", "Analysis Term (years)", prop.analysis_term_years),
        ("Property", "Fiscal Year End Month", prop.fiscal_year_end_month),
        ("Area", "Rentable Area Mode", am.rentable_area_mode.value),
        ("Area", "Property Size (SF)", am.property_size),
        ("Area", "Rentable Area Fixed (SF)", am.rentable_area_fixed),
        ("Tenancy", "Rent Roll Leases", len(model.rent_roll)),
        ("Tenancy", "Absorption Specs", len(model.absorption)),
        ("Tenancy", "Market Leasing Profiles", len(model.market_leasing_profiles)),
        ("Expenses", "Expense Items", len(model.expenses)),
        ("Expenses", "Recovery Structures", len(model.recovery_structures)),
    ]
    gv = model.general_vacancy
    if gv is not None:
        rows.append(("Market", "General Vacancy Method", gv.method.value))
    if model.purchase is not None:
        rows.append(("Investment", "Purchase Price", model.purchase.price))
    rows.append(("Investment", "Loans", len(model.loans)))
    if model.valuation is not None:
        v = model.valuation
        rows += [
            ("Valuation", "Discount Rate (%)", v.discount_rate),
            ("Valuation", "Discount Method", v.discount_method.value),
            ("Valuation", "Resale Method", v.resale.method.value),
            ("Valuation", "Exit Cap Rate (%)", v.resale.exit_cap_rate),
        ]
    return rows


def assumptions_report(model) -> Report:
    """Assumptions Report (#3): the model input echo grouped by section
    (Property / Area / Tenancy / Expenses / Market / Investment /
    Valuation)."""
    rows = _model_assumptions(model)
    out = pd.DataFrame(
        [{"section": s, "assumption": a, "value": str(v)} for s, a, v in rows],
        columns=["section", "assumption", "value"])
    meta = ReportMeta(name="Assumptions Report", number=3, monetary=False,
                      citation="[AE pp. 535-549]",
                      extra={"assumption_count": len(out)})
    return Report(frame=out, meta=meta)


def input_assumptions_listing(model) -> Report:
    """Input Assumptions listing (#23): the same model echo as #3 as a flat
    ``assumption / value`` table (overlaps #3 by design, spec §7 — see
    docs/SCHEMA_GUIDE)."""
    rows = _model_assumptions(model)
    out = pd.DataFrame(
        [{"assumption": f"{s} · {a}", "value": str(v)} for s, a, v in rows],
        columns=["assumption", "value"])
    meta = ReportMeta(name="Input Assumptions", number=23, monetary=False,
                      citation="[AE pp. 535-549]",
                      extra={"assumption_count": len(out)})
    return Report(frame=out, meta=meta)
