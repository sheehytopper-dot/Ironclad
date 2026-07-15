"""Dump a property's full monthly ledger to .xlsx for owner eyeball review.

Usage:
    .venv\\Scripts\\python scripts\\dump_monthly.py <property.icprop.json> [--out FILE.xlsx]

Loads the PropertyModel, runs the engine (spec §4.1 passes 1-6), and
writes one sheet: Cash Flow lines as rows in report order, months as
columns, followed by fiscal-year subtotal columns (the basis the OM
goldens assert on). Values are full precision — rounding is report-level
only (spec §4.3) and this is an audit dump, not a report; the report
modules (engine/reports/, Phase 2 Steps 5-6) are a separate surface.

Default output: next to the input, `<name>-monthly.xlsx` (gitignored —
generated artifacts are never committed).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from engine.calc.ledger import to_fiscal_annual  # noqa: E402
from engine.calc.run import run_property  # noqa: E402
from engine.models.io import load_property  # noqa: E402


def dump_monthly(input_path: Path, out_path: Path) -> Path:
    model = load_property(input_path)
    result = run_property(model)
    frame = result.ledger.frame

    monthly = frame.T
    monthly.columns = [str(p) for p in frame.index]  # "2026-06", ...

    fiscal = to_fiscal_annual(frame, model.property.fiscal_year_end_month).T
    fiscal.columns = [f"FY{y}" for y in fiscal.columns]

    table = pd.concat([monthly, fiscal], axis=1)
    table.index.name = "Account"

    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        table.to_excel(writer, sheet_name="Monthly Ledger")
        book, sheet = writer.book, writer.sheets["Monthly Ledger"]
        money = book.add_format({"num_format": "#,##0.00"})
        fiscal_fmt = book.add_format({"num_format": "#,##0.00", "bold": True})
        sheet.set_column(0, 0, 42)
        sheet.set_column(1, len(monthly.columns), 13, money)
        sheet.set_column(len(monthly.columns) + 1, len(table.columns), 15,
                         fiscal_fmt)
        sheet.freeze_panes(1, 1)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump a property's monthly ledger to .xlsx"
    )
    parser.add_argument("property_json", type=Path,
                        help="path to a .icprop.json file")
    parser.add_argument("--out", type=Path, default=None,
                        help="output .xlsx path (default: alongside input)")
    args = parser.parse_args()

    out = args.out
    if out is None:
        name = args.property_json.name.removesuffix(".icprop.json")
        out = args.property_json.parent / f"{name}-monthly.xlsx"
    path = dump_monthly(args.property_json, out)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
