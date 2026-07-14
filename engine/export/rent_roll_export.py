"""Rent-roll Excel export (Phase 4 Step 6; spec §5.2 / §8).

Writes the rent roll to the §5.2 import-template layout: a **Rent Roll**
sheet with one row per lease over the flat §3.12 fields, plus **Rent Steps**
and **Misc Items** companion sheets keyed by tenant. This is the export
half of the round-trip; the importer and the export→import round-trip test
are Phase 4 Step 7 (spec §5.2). Values-only; the engine never imports UI
code (Iron Rule 1).

The flat template carries the scalar lease fields that round-trip cleanly
(names, area, dates/term, base rent amount+unit, status, expiration, the
market-leasing-profile reference). Nested structures (free-rent profiles,
recovery assignments, percentage rent, security deposits, leasing costs)
live in the JSON document (§5.1) and are out of the flat template's scope —
the same narrowing §5.2 states ("columns matching §3.12 flat fields").
"""
from __future__ import annotations

from typing import Optional

import xlsxwriter

#: Rent Roll sheet columns (flat §3.12 fields), in order.
RENT_ROLL_COLUMNS = [
    "tenant_name", "suite", "external_id", "area", "lease_type", "status",
    "start_date", "end_date", "term_months", "base_rent_amount",
    "base_rent_unit", "upon_expiration", "market_leasing_profile", "notes",
]
RENT_STEP_COLUMNS = [
    "tenant_name", "amount", "unit", "pct_increase", "date", "month_offset",
]
MISC_ITEM_COLUMNS = ["tenant_name", "name", "amount", "unit", "free_rent_abates"]

_HEADER_BG = "#3F3D8A"


def _lease_row(lease) -> list:
    return [
        lease.tenant_name,
        lease.suite or "",
        lease.external_id or "",
        float(lease.area),
        lease.lease_type.value,
        lease.status.value,
        str(lease.start_date) if lease.start_date is not None else "",
        str(lease.end_date) if lease.end_date is not None else "",
        (lease.term_months if lease.term_months is not None else ""),
        float(lease.base_rent.amount),
        lease.base_rent.unit.value,
        lease.upon_expiration.value,
        lease.market_leasing_profile or "",
        lease.notes or "",
    ]


def _step_rows(lease) -> list[list]:
    rows = []
    for step in lease.rent_steps:
        rows.append([
            lease.tenant_name,
            (float(step.amount) if step.amount is not None else ""),
            (step.unit.value if step.unit is not None else ""),
            (float(step.pct_increase) if step.pct_increase is not None else ""),
            (str(step.date) if step.date is not None else ""),
            (step.month_offset if step.month_offset is not None else ""),
        ])
    return rows


def _misc_rows(lease) -> list[list]:
    rows = []
    for item in lease.miscellaneous_items:
        rows.append([
            lease.tenant_name, item.name, float(item.amount),
            item.unit.value, bool(item.free_rent_abates),
        ])
    return rows


def _write_sheet(workbook, name: str, columns: list[str],
                 rows: list[list]) -> None:
    worksheet = workbook.add_worksheet(name)
    header = workbook.add_format({"bold": True, "font_color": "white",
                                  "bg_color": _HEADER_BG, "border": 1})
    for c, col in enumerate(columns):
        worksheet.write_string(0, c, col, header)
    for r, row in enumerate(rows, start=1):
        for c, value in enumerate(row):
            if value == "" or value is None:
                worksheet.write_blank(r, c, None)
            elif isinstance(value, bool):
                worksheet.write_boolean(r, c, value)
            elif isinstance(value, (int, float)):
                worksheet.write_number(r, c, value)
            else:
                worksheet.write_string(r, c, str(value))
    widths = [max([len(str(columns[c]))]
                  + [len(str(row[c])) for row in rows if row[c] not in ("", None)],
                  default=10) for c in range(len(columns))]
    for c, w in enumerate(widths):
        worksheet.set_column(c, c, min(max(w + 2, 10), 40))
    worksheet.freeze_panes(1, 0)


def export_rent_roll(model, *, path) -> dict[str, int]:
    """Write the rent roll to ``path`` in the §5.2 template layout. Returns
    ``{sheet_name: row_count}`` (excluding headers). Recomputes nothing — a
    faithful echo of ``model.rent_roll``."""
    lease_rows = [_lease_row(l) for l in model.rent_roll]
    step_rows = [r for l in model.rent_roll for r in _step_rows(l)]
    misc_rows = [r for l in model.rent_roll for r in _misc_rows(l)]
    workbook = xlsxwriter.Workbook(str(path), {"in_memory": True})
    try:
        _write_sheet(workbook, "Rent Roll", RENT_ROLL_COLUMNS, lease_rows)
        _write_sheet(workbook, "Rent Steps", RENT_STEP_COLUMNS, step_rows)
        _write_sheet(workbook, "Misc Items", MISC_ITEM_COLUMNS, misc_rows)
    finally:
        workbook.close()
    return {"Rent Roll": len(lease_rows), "Rent Steps": len(step_rows),
            "Misc Items": len(misc_rows)}
