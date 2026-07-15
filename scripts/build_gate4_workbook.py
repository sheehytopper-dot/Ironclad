"""Build the Excel result package(s) for the Phase 4 Gate 4 owner spot-check
(§8 export review; NEXT_STEPS_TO_PHASE4.md Step 8).

The Gate 4 §8 criterion is an **owner workbook spot-check**: open the
formatted package and eyeball the tabs, formatting, PSF/unit note, and a
couple of totals against a report view (the plan's analogue of the Step
3/4/5 owner hand-checks). This script produces the workbook to open.

Usage:
    .venv\\Scripts\\python scripts\\build_gate4_workbook.py [property.icprop.json] [--out FILE]

With a property path, it exports that property's package. With no path it
exports **two** demonstration packages so every tab is exercised:
  * the Clorox golden (real OM inputs; no valuation → valuation tabs are
    correctly skipped, not fabricated), and
  * a small valuation+debt property (so IRR/Value Matrix, Present Value,
    and Loan Amortization tabs are populated).
It also writes the rent-roll template (export half of the §5.2 round-trip)
and re-imports it, printing whether the round-trip reproduced the rent roll.

Outputs are ``*-package.xlsx`` / ``*-rentroll.xlsx`` next to this repo
(gitignored — generated artifacts are never committed).
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.calc.run import run_property  # noqa: E402
from engine.export import build_package, export_rent_roll  # noqa: E402
from engine.intake import import_rent_roll  # noqa: E402
from engine.models.io import load_property  # noqa: E402
from engine.models import (  # noqa: E402
    AreaMeasures, ExpenseItem, ExpenseUnit, Inflation, Lease, MoneyRate,
    MoneyUnit, PropertyInfo, PropertyModel, Purchase, RentableAreaMode,
    RentStep, TimingBasis, UponExpiration, YearRate,
)
from engine.models.investment import (  # noqa: E402
    ClosingCost, Loan, LoanAmount, LoanCosts,
)
from engine.models.valuation import (  # noqa: E402
    DirectCap, Resale, SensitivityIntervals, ValuationInputs,
)

ROOT = Path(__file__).resolve().parents[1]
STAMP = "2026-07-14 (Gate 4 review)"


def _valuation_demo() -> PropertyModel:
    """A small office property with a purchase, a mortgage, and a full
    valuation so IRR / Value Matrix / Present Value / Loan Amortization
    tabs populate."""
    psf = MoneyUnit.dollars_per_area_per_year
    lease = Lease(tenant_name="Acme Co", suite="100", area=12_000,
                  lease_type="office", start_date=dt.date(2026, 1, 1),
                  term_months=120, base_rent=MoneyRate(amount=28.0, unit=psf),
                  upon_expiration=UponExpiration.vacate,
                  rent_steps=[RentStep(month_offset=24, amount=30.0, unit=psf)])
    return PropertyModel(
        property=PropertyInfo(name="Gate4 Valuation Demo",
                              property_type="office",
                              analysis_begin=dt.date(2026, 1, 1),
                              analysis_term_years=5),
        area_measures=AreaMeasures(property_size=12_000,
                                   rentable_area_mode=RentableAreaMode.fixed,
                                   rentable_area_fixed=12_000),
        inflation=Inflation(general_rate=[YearRate(year=1, rate=3.0)],
                            timing_basis=TimingBasis.analysis_year),
        rent_roll=[lease],
        expenses=[ExpenseItem(name="CAM", amount=60_000.0,
                              unit=ExpenseUnit.dollars_per_year,
                              recoverable=True)],
        loans=[Loan(name="Mortgage", amount=LoanAmount(value=2_000_000.0),
                    term_months=360, rate=6.5,
                    amortization="fully_amortizing",
                    loan_costs=LoanCosts(points_pct=1.0))],
        purchase=Purchase(price=4_000_000.0,
                          closing_costs=[ClosingCost(name="Legal",
                                                     amount=60_000.0)]),
        valuation=ValuationInputs(
            discount_rate=8.0, direct_cap=DirectCap(cap_rate=7.5),
            resale=Resale(method="cap_noi_current_year", exit_cap_rate=7.5,
                          selling_costs_pct=2.0),
            sensitivity_intervals=SensitivityIntervals(
                discount_rate_step=0.5, cap_rate_step=0.25, count=5)))


def _export(model, out: Path) -> None:
    # Generated-file convention: kebab-case stem + a single real extension
    # (with_name, not with_suffix — the suffix has no leading dot).
    result = run_property(model)
    pkg = out.with_name(f"{out.stem}-package.xlsx")
    tabs = build_package(result, model, path=pkg, scenario="Base",
                         timestamp=STAMP)
    print(f"  package: {pkg}")
    print(f"    tabs ({len(tabs)}): {', '.join(tabs)}")

    rr = out.with_name(f"{out.stem}-rentroll.xlsx")
    counts = export_rent_roll(model, path=rr)
    reimported = import_rent_roll(rr)
    ok = len(reimported) == len(model.rent_roll) and all(
        a.tenant_name == b.tenant_name and a.area == b.area
        and a.base_rent.amount == b.base_rent.amount
        for a, b in zip(model.rent_roll, reimported))
    print(f"  rent roll: {rr}  ({counts['Rent Roll']} leases; "
          f"export->import round-trip {'OK' if ok else 'MISMATCH'})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("property", nargs="?", type=Path,
                    help="a .icprop.json property (default: demo set)")
    ap.add_argument("--out", type=Path, help="output base path")
    args = ap.parse_args()

    if args.property is not None:
        model = load_property(args.property)
        out = args.out or ROOT / args.property.stem
        print(f"Exporting {model.property.name!r}:")
        _export(model, out)
        return

    clorox = ROOT / "tests/golden/clorox_northlake/clorox_northlake.icprop.json"
    print("Exporting the Clorox golden (real OM; no valuation → those tabs "
          "are correctly skipped):")
    _export(load_property(clorox), ROOT / "clorox")
    print("\nExporting the valuation demo (all valuation/debt tabs populated):")
    _export(_valuation_demo(), ROOT / "valuation-demo")
    print("\nOpen the -package.xlsx files and spot-check: tabs present, "
          "indigo header band, Cash Flow tree indentation, negatives in red "
          "parens, frozen panes, the unit/period note under each title, and a "
          "couple of totals against the on-screen report. This is the §8 "
          "Gate 4 owner spot-check.")


if __name__ == "__main__":
    main()
