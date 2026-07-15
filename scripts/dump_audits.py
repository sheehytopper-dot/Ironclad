"""Dump the Lease Audit and Recovery Audit reports to .xlsx for the
Gate 2 owner review (NEXT_STEPS_TO_GATE2.md: owner review of both audit
reports is a Gate 2 criterion).

Usage:
    .venv\\Scripts\\python scripts\\dump_audits.py <property.icprop.json> [--out FILE.xlsx]

Loads the PropertyModel, runs the engine, and writes three sheets:
"Lease Audit" (spec §7 report 16), "Recovery Audit" (report 18), and
"Reconciliation" — the per-month report-minus-ledger differences for
both reports, which must be exactly zero everywhere. Full precision
(spec §4.3): this is an audit dump, not a formatted report (Phase 4).

Default output: next to the input, `<name>-audits.xlsx` (gitignored —
generated artifacts are never committed).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from engine.calc.run import run_property  # noqa: E402
from engine.models.io import load_property  # noqa: E402
from engine.reports import (  # noqa: E402
    lease_audit,
    reconcile_lease_audit,
    reconcile_recovery_audit,
    recovery_audit,
)


def dump_audits(input_path: Path, out_path: Path) -> Path:
    result = run_property(load_property(input_path))

    lease_report = lease_audit(result)
    recovery_report = recovery_audit(result)

    lease_diff = reconcile_lease_audit(lease_report, result)
    recovery_diff = reconcile_recovery_audit(recovery_report, result)
    reconciliation = lease_diff.copy()
    reconciliation["recovery_audit_total"] = recovery_diff
    reconciliation.index = [str(p) for p in reconciliation.index]
    reconciliation.index.name = "month"

    for frame in (lease_report, recovery_report):
        if not frame.empty:
            frame["month"] = frame["month"].astype(str)
    if not recovery_report.empty:
        recovery_report["segment_start"] = (
            recovery_report["segment_start"].astype(str)
        )

    with pd.ExcelWriter(out_path, engine="xlsxwriter") as writer:
        lease_report.to_excel(writer, sheet_name="Lease Audit", index=False)
        recovery_report.to_excel(writer, sheet_name="Recovery Audit",
                                 index=False)
        reconciliation.to_excel(writer, sheet_name="Reconciliation")
        money = writer.book.add_format({"num_format": "#,##0.00"})
        for name, frame in (("Lease Audit", lease_report),
                            ("Recovery Audit", recovery_report)):
            sheet = writer.sheets[name]
            sheet.set_column(0, max(len(frame.columns) - 1, 0), 14, money)
            sheet.freeze_panes(1, 0)
        writer.sheets["Reconciliation"].set_column(0, 6, 16)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump the Lease Audit + Recovery Audit reports to .xlsx"
    )
    parser.add_argument("property_json", type=Path,
                        help="path to a .icprop.json file")
    parser.add_argument("--out", type=Path, default=None,
                        help="output .xlsx path (default: alongside input)")
    args = parser.parse_args()

    out = args.out
    if out is None:
        name = args.property_json.name.removesuffix(".icprop.json")
        out = args.property_json.parent / f"{name}-audits.xlsx"
    path = dump_audits(args.property_json, out)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
