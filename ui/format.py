"""Display-only number formatting (Phase 5 usability pass, Tier 1).

**The guardrail: formatting is DISPLAY-ONLY.** Every function here builds
a NEW object-dtype frame (or a Styler over one) and never mutates or
rounds the report's underlying ``frame`` — the builders, the
frame-equality tests, and the Excel exporters keep operating on the raw
full-precision data. Pure and browser-free; keyed off ``report.meta``
(monetary flag, unit) plus explicit percent-column sets.

Conventions: thousands separators; accounting-style negatives in
parentheses; monetary Total-$ at 0 decimals, per-SF/per-month views at 2;
percent columns as ``X.X%`` (fraction-scaled columns like occupancy and
pro-rata share are ×100 in DISPLAY only).
"""
from __future__ import annotations

import numbers
from typing import Optional

import pandas as pd

from engine.reports import Report, Unit

#: Columns holding 0..1 fractions (×100 for display).
FRACTION_COLUMNS = {"occupancy", "share", "renewal_weight"}
#: Columns already in percent units (display with a % sign).
PERCENT_COLUMNS = {"pct_of_building", "implied_rate_pct", "occupancy_pct",
                   "rate", "gross_up_pct", "admin_fee_pct"}
#: Integer-like columns shown plain (no thousands separator — years, ids).
PLAIN_COLUMNS = {"fiscal_year", "year", "month_offset", "term_months",
                 "expiring_leases", "number_of_spaces", "loan_index",
                 "frequency_months", "interest_only_months"}


def money(value, decimals: int = 0) -> str:
    """Accounting style: thousands separators, negatives in parentheses."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if value < 0:
        return f"({abs(value):,.{decimals}f})"
    return f"{value:,.{decimals}f}"


def percent(value, decimals: int = 1, *, from_fraction: bool = False) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    scaled = value * 100.0 if from_fraction else value
    return f"{scaled:.{decimals}f}%"


def _format_cell(value, column_name: str, decimals: int) -> object:
    if not isinstance(value, numbers.Real) or isinstance(value, bool):
        return value
    name = str(column_name).lower()
    if name in FRACTION_COLUMNS:
        return percent(value, 1, from_fraction=True)
    if name in PERCENT_COLUMNS or name.endswith("_pct") or "(%)" in name:
        return percent(value, 2)
    if name in PLAIN_COLUMNS or (isinstance(value, numbers.Integral)):
        return str(value)
    # floats: whole values at the report's decimals, fractional at 2
    cell_decimals = decimals if float(value).is_integer() else max(decimals,
                                                                   2)
    return money(value, cell_decimals)


def unit_decimals(unit: Optional[Unit]) -> int:
    """Monetary display decimals by unit: Total-$ 0, per-SF/-month/-occ 2."""
    return 0 if unit in (None, Unit.total) else 2


def frame_display(frame: pd.DataFrame, *, decimals: int = 0
                  ) -> pd.DataFrame:
    """A display-formatted COPY of any plain frame (per-column rules; the
    input frame is never touched)."""
    display = pd.DataFrame(index=frame.index, dtype=object)
    for column in frame.columns:
        display[column] = [_format_cell(v, column, decimals)
                           for v in frame[column]]
    return display


def report_display(report: Report) -> pd.DataFrame:
    """A display-formatted COPY of ``report.frame`` (object dtype, string
    cells). ``report.frame`` is never touched."""
    frame = report.frame
    decimals = unit_decimals(report.meta.unit) if report.meta.monetary else 0
    display = pd.DataFrame(index=frame.index, dtype=object)
    for column in frame.columns:
        if report.meta.monetary and pd.api.types.is_float_dtype(
                frame[column]):
            display[column] = [money(v, decimals) for v in frame[column]]
        else:
            display[column] = [_format_cell(v, column, decimals)
                               for v in frame[column]]
    return display


def cash_flow_display(report: Report, columns=None):
    """The ARGUS-style Cash Flow view: a pandas Styler over a display COPY
    — detail rows indented by their tree level, subtotal rows bold, grand
    totals (EGR/NOI/CFBDS/CFADS) bold with a top rule — driven by the
    ``tree`` metadata report #1 already carries (``meta.extra['tree']``:
    account / level / is_subtotal / grand_total). Values formatted at the
    unit's decimals; ``columns`` optionally restricts the period columns
    (the date-range slice — still a pure selection). ``report.frame`` is
    never touched."""
    tree = report.meta.extra["tree"]
    decimals = unit_decimals(report.meta.unit)
    frame = report.frame if columns is None else report.frame[list(columns)]
    display = pd.DataFrame(
        {column: [money(v, decimals) for v in frame[column]]
         for column in frame.columns})
    display.index = [" " * (4 * node["level"]) + node["account"]
                     for node in tree]
    display.index.name = frame.index.name

    bold_rows = [i for i, node in enumerate(tree) if node["is_subtotal"]]
    grand_rows = [i for i, node in enumerate(tree)
                  if node.get("grand_total")]

    def _row_style(row):
        position = display.index.get_loc(row.name)
        css = ""
        if position in bold_rows:
            css = "font-weight: bold;"
        if position in grand_rows:
            css += " border-top: 1px solid; font-weight: bold;"
        return [css] * len(row)

    return display.style.apply(_row_style, axis=1)
