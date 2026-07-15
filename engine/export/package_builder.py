"""Excel result package (Phase 4 Step 6; spec §8).

Produces one ``.xlsx`` workbook per property/scenario, a tab per selected
report (spec §8 default set), values-only (no live formulas in v1). The
exporter **formats, it does not calculate** — every tab is a Step 1-5
report builder's DataFrame written to a sheet; nothing here recomputes the
ledger, valuation, or any figure. Any building-area / occupancy /
expiration figure therefore inherits the Step 4-fix quantities (rentable
area as the building size, ``distinct_demised_area``, status-filtered
chains — DEVIATIONS.md §25); the exporter never sums contract areas.

Formatting (spec §8): a bold indigo title band, account-tree indentation
(Cash Flow), negatives in red parentheses, $ / rate number formats, frozen
panes below the header, auto column widths, a footer with property /
scenario / timestamp, and the unit/period noted under the title.

**Value integrity is the acceptance:** each tab's cell values equal the
report builder's DataFrame exactly (:func:`report_cell_grid` is the single
source of the grid the exporter writes; the Step 6 test reads the workbook
back with openpyxl and diffs it against the builders cell by cell, and is
proven capable of failing by corrupting a written cell — DEVIATIONS.md §25
standing rule). Writes with ``xlsxwriter``; the engine never imports UI
code (Iron Rule 1).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np
import pandas as pd
import xlsxwriter

from engine.reports import (
    Period,
    Report,
    assumptions_report,
    cash_flow,
    executive_summary,
    irr_matrix,
    lease_expiration,
    lease_summary,
    loan_amortization,
    present_value,
    recovery_audit_report,
    value_matrix,
)

# Number-format families (display only — the stored value is never altered).
_DOLLAR_FMT = "#,##0;[Red](#,##0)"   # negatives in red parentheses (spec §8)
_RATE_FMT = "0.00"                   # percents / ratios (header carries the %)
_HEADER_BG = "#3F3D8A"               # indigo header band (spec §8)


@dataclass(frozen=True)
class ReportSpec:
    """One tab of the package: how to build the report and how to number-
    format its numeric cells."""

    tab: str
    build: Callable[[object, object], Report]
    number_format: Optional[str] = None      # None → general
    applies: Callable[[object, object], bool] = lambda result, model: True


def _fye(model) -> int:
    return model.property.fiscal_year_end_month


def _begin(model):
    return model.property.analysis_begin


#: Spec §8 default export set (11 reports). Cash Flow appears twice (annual
#: fiscal view + monthly); reports needing valuation / loans / sensitivity
#: are included only when applicable (skipped, never a fabricated tab).
DEFAULT_REPORTS: list[ReportSpec] = [
    ReportSpec("Executive Summary",
               lambda r, m: executive_summary(r, m)),
    ReportSpec("Annual Cash Flow",
               lambda r, m: cash_flow(r, period=Period.fiscal,
                                      fiscal_year_end_month=_fye(m),
                                      analysis_begin=_begin(m)),
               number_format=_DOLLAR_FMT),
    ReportSpec("Monthly Cash Flow",
               lambda r, m: cash_flow(r, period=Period.monthly,
                                      fiscal_year_end_month=_fye(m),
                                      analysis_begin=_begin(m)),
               number_format=_DOLLAR_FMT),
    ReportSpec("Lease Summary",
               lambda r, m: lease_summary(r)),
    ReportSpec("Lease Expiration",
               lambda r, m: lease_expiration(r, fiscal_year_end_month=_fye(m))),
    ReportSpec("IRR Matrix",
               lambda r, m: irr_matrix(r), number_format=_RATE_FMT,
               applies=lambda r, m: r.sensitivity is not None),
    ReportSpec("Value Matrix",
               lambda r, m: value_matrix(r), number_format=_DOLLAR_FMT,
               applies=lambda r, m: r.sensitivity is not None),
    ReportSpec("Present Value",
               lambda r, m: present_value(r), number_format=_DOLLAR_FMT,
               applies=lambda r, m: r.valuation is not None),
    ReportSpec("Recovery Audit",
               lambda r, m: recovery_audit_report(r), number_format=_DOLLAR_FMT),
    ReportSpec("Loan Amortization",
               lambda r, m: loan_amortization(r), number_format=_DOLLAR_FMT,
               applies=lambda r, m: bool(r.loan_schedules)),
    ReportSpec("Assumptions",
               lambda r, m: assumptions_report(m)),
]


def _cellify(value):
    """Normalize a DataFrame value to the exact cell value written (and
    expected on read-back): ``NaN`` / ``None`` → ``None`` (blank);
    numpy scalars → Python ``int`` / ``float``; ``int`` / ``float`` / ``str``
    / ``bool`` native; everything else (``Period``, ``Timestamp``) → ``str``.
    The single normalization both the exporter and its test use, so the
    on-disk grid is well defined."""
    if value is None:
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, (bool, int, str)):
        return value
    return str(value)


def report_cell_grid(report: Report) -> list[list]:
    """The exact grid the exporter writes for a report's data region: the
    header row followed by one row per DataFrame row, normalized via
    :func:`_cellify`. The leading index column is written **only** when the
    frame has a meaningful (non-default) index (Cash Flow accounts, matrix
    axes, loan-schedule months); tabular reports with a RangeIndex omit it.
    This is the single source of truth for the Step 6 cell-by-cell test."""
    df = report.frame
    write_index = not isinstance(df.index, pd.RangeIndex)
    header = []
    if write_index:
        header.append(_cellify(df.index.name) if df.index.name else "")
    header.extend(_cellify(c) for c in df.columns)
    grid = [header]
    for ix, row in zip(df.index, df.itertuples(index=False, name=None)):
        cells = []
        if write_index:
            cells.append(_cellify(ix))
        cells.extend(_cellify(v) for v in row)
        grid.append(cells)
    return grid


#: The data region starts at this 0-indexed row (title band above it).
DATA_START_ROW = 3


def _write_report_sheet(workbook, worksheet, report: Report, spec: ReportSpec,
                        *, property_name: str, scenario: str, timestamp: str
                        ) -> None:
    """Write one report to a worksheet: indigo title band, the data grid
    (values only, per :func:`report_cell_grid`), number formats, tree
    indentation for Cash Flow, frozen panes, auto widths, footer."""
    title = workbook.add_format({"bold": True, "font_color": "white",
                                 "bg_color": _HEADER_BG, "font_size": 13})
    subtitle = workbook.add_format({"italic": True, "font_color": "#555555"})
    header = workbook.add_format({"bold": True, "font_color": "white",
                                  "bg_color": _HEADER_BG, "border": 1})
    footer_fmt = workbook.add_format({"italic": True, "font_color": "#888888"})

    # Cell formats, created once and cached by (is_number, indent, bold,
    # grand_total). Subtotals are bold; the bottom-line summary totals
    # (EGR / NOI / CFBDS / CFADS) additionally get a thin rule line above,
    # so the Cash Flow's summary lines read cleanly without every subtotal
    # shouting (DEVIATIONS §25 formatting pass). Presentation only — cell
    # VALUES are unchanged.
    _fmt_cache: dict = {}

    def cell_fmt(*, is_number=False, indent=0, bold=False, grand=False):
        key = (is_number, indent, bold, grand)
        if key not in _fmt_cache:
            props: dict = {}
            if is_number and spec.number_format:
                props["num_format"] = spec.number_format
            if bold:
                props["bold"] = True
            if indent:
                props["indent"] = indent
            if grand:
                props["top"] = 1
            _fmt_cache[key] = workbook.add_format(props)
        return _fmt_cache[key]

    grid = report_cell_grid(report)
    n_cols = max(len(r) for r in grid)

    unit = report.meta.unit.value if report.meta.monetary else "n/a"
    worksheet.merge_range(0, 0, 0, max(n_cols - 1, 0),
                          f"{report.meta.name}  (#{report.meta.number})", title)
    worksheet.merge_range(
        1, 0, 1, max(n_cols - 1, 0),
        f"period: {report.meta.period.value}   unit: {unit}   "
        f"{report.meta.citation}", subtitle)

    # Cash Flow tree: indent level + bold subtotals, keyed by account.
    tree = {row["account"]: row for row in report.meta.extra.get("tree", [])}

    for r, cells in enumerate(grid):
        excel_row = DATA_START_ROW + r
        if r == 0:
            for c, value in enumerate(cells):
                worksheet.write(excel_row, c, value, header)
            continue
        account = str(cells[0]) if tree else None
        node = tree.get(account) if account else None
        bold = bool(node and node["is_subtotal"])
        grand = bool(node and node.get("grand_total"))
        level = node["level"] if node else 0
        for c, value in enumerate(cells):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                worksheet.write_number(
                    excel_row, c, value,
                    cell_fmt(is_number=True, bold=bold, grand=grand))
            elif value is None:
                # a grand-total row carries its rule line across blank cells
                worksheet.write_blank(
                    excel_row, c, None,
                    cell_fmt(grand=True) if grand else None)
            else:
                # the label cell (c == 0) carries the Cash Flow tree indent
                worksheet.write_string(
                    excel_row, c, str(value),
                    cell_fmt(indent=(level if c == 0 else 0), bold=bold,
                             grand=grand))

    # Frozen panes below the header row (and right of the first column).
    worksheet.freeze_panes(DATA_START_ROW + 1, 1)

    # Auto column widths from the longest rendered cell.
    for c in range(n_cols):
        widest = 0
        for cells in grid:
            if c < len(cells) and cells[c] is not None:
                widest = max(widest, len(str(cells[c])))
        worksheet.set_column(c, c, min(max(widest + 2, 10), 60))

    footer_row = DATA_START_ROW + len(grid) + 1
    worksheet.write(footer_row, 0,
                    f"{property_name}  ·  scenario: {scenario}  ·  {timestamp}",
                    footer_fmt)


def _safe_sheet_name(name: str, used: set[str]) -> str:
    """Excel sheet names: ≤ 31 chars, no ``[]:*?/\\``, unique."""
    for ch in "[]:*?/\\":
        name = name.replace(ch, " ")
    name = name[:31].strip() or "Sheet"
    base, i = name, 2
    while name in used:
        suffix = f" ({i})"
        name = base[:31 - len(suffix)] + suffix
        i += 1
    used.add(name)
    return name


def build_package(result, model, *, path,
                  reports: Optional[list[ReportSpec]] = None,
                  scenario: str = "Base", timestamp: str = "") -> list[str]:
    """Write the Excel result package to ``path`` — a tab per applicable
    report (default: spec §8's 11-report set). Returns the list of tab names
    written (reports whose ``applies`` predicate is False are skipped, never
    fabricated). The exporter only formats already-built report DataFrames;
    it recomputes nothing."""
    reports = reports if reports is not None else DEFAULT_REPORTS
    property_name = model.property.name
    workbook = xlsxwriter.Workbook(str(path), {"in_memory": True})
    used: set[str] = set()
    written: list[str] = []
    try:
        for spec in reports:
            if not spec.applies(result, model):
                continue
            report = spec.build(result, model)
            sheet_name = _safe_sheet_name(spec.tab, used)
            worksheet = workbook.add_worksheet(sheet_name)
            _write_report_sheet(workbook, worksheet, report, spec,
                                 property_name=property_name,
                                 scenario=scenario, timestamp=timestamp)
            written.append(sheet_name)
    finally:
        workbook.close()
    return written


def export_report(report: Report, *, path, tab: Optional[str] = None,
                  number_format: Optional[str] = None,
                  property_name: str = "", scenario: str = "Base",
                  timestamp: str = "") -> str:
    """Single-report export (spec §8): write one already-built ``Report`` to
    its own one-tab workbook at ``path``. Returns the tab name. Recomputes
    nothing — it writes the DataFrame it is handed."""
    spec = ReportSpec(tab or report.meta.name, lambda r, m: report,
                      number_format=number_format)
    workbook = xlsxwriter.Workbook(str(path), {"in_memory": True})
    try:
        sheet_name = _safe_sheet_name(spec.tab, set())
        worksheet = workbook.add_worksheet(sheet_name)
        _write_report_sheet(workbook, worksheet, report, spec,
                             property_name=property_name, scenario=scenario,
                             timestamp=timestamp)
    finally:
        workbook.close()
    return sheet_name
