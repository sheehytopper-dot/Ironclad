"""The Reports-tab registry (Phase 5 Step 6; pure, browser-free).

One entry per built §7 report: how to build it from ``(result, model)``
plus the global unit/period toggles, and when it applies. **Every frame
comes from the engine's own builder** — the UI never post-processes report
numbers (the date-range slice below is a column *selection*, not math).
Benchmark Comparison (#24) builds only when the loaded property has an
``expected_annual_cash_flow.csv`` beside its ``.icprop.json`` (the golden
convention, spec §9.1). Iron Rule 1: engine imports only.
"""
from __future__ import annotations

import csv as _csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from engine.calc.ledger import to_fiscal_annual
from engine.reports import (
    CONTRACTUAL_STATUSES,
    Period,
    Report,
    Unit,
    assumptions_report,
    benchmark_comparison,
    cash_flow,
    executive_summary,
    input_assumptions_listing,
    irr_matrix,
    lease_audit_report,
    lease_expiration,
    lease_summary,
    load_expected_cash_flow,
    loan_amortization,
    occupancy,
    present_value,
    recovery_audit_report,
    resale_audit_report,
    resale_matrix,
    sources_and_uses,
    valuation_summary,
    value_matrix,
)

BENCHMARK_CSV_NAME = "expected_annual_cash_flow.csv"


@dataclass(frozen=True)
class ReportEntry:
    """One picker entry. ``build(result, model, unit, period, options)``
    returns the engine builder's ``Report`` unchanged; ``supports_unit`` /
    ``supports_period`` say which global toggles reach the builder."""

    label: str
    number: int
    build: Callable
    applies: Callable = lambda result, model: True
    supports_unit: bool = False
    supports_period: bool = False
    note: str = ""


def _fye(model) -> int:
    return model.property.fiscal_year_end_month


REGISTRY: list[ReportEntry] = [
    ReportEntry(
        "Cash Flow", 1,
        lambda r, m, u, p, o: cash_flow(r, unit=u, period=p,
                                        fiscal_year_end_month=_fye(m),
                                        analysis_begin=m.property.analysis_begin),
        supports_unit=True, supports_period=True),
    ReportEntry("Executive Summary", 2,
                lambda r, m, u, p, o: executive_summary(r, m)),
    ReportEntry("Assumptions Report", 3,
                lambda r, m, u, p, o: assumptions_report(m)),
    ReportEntry("Sources & Uses", 4,
                lambda r, m, u, p, o: sources_and_uses(r)),
    ReportEntry("IRR Matrix", 5,
                lambda r, m, u, p, o: irr_matrix(r, leveraged=False),
                applies=lambda r, m: r.sensitivity is not None),
    ReportEntry("IRR Matrix (leveraged)", 5,
                lambda r, m, u, p, o: irr_matrix(r, leveraged=True),
                applies=lambda r, m: (r.sensitivity is not None
                                      and bool(r.loan_schedules))),
    ReportEntry("Value Matrix", 6,
                lambda r, m, u, p, o: value_matrix(r),
                applies=lambda r, m: r.sensitivity is not None),
    ReportEntry("Resale Matrix", 7,
                lambda r, m, u, p, o: resale_matrix(r, m),
                applies=lambda r, m: r.sensitivity is not None),
    ReportEntry("Valuation & Return Summary", 8,
                lambda r, m, u, p, o: valuation_summary(r),
                applies=lambda r, m: r.valuation is not None),
    ReportEntry("Present Value", 9,
                lambda r, m, u, p, o: present_value(r, leveraged=False),
                applies=lambda r, m: r.valuation is not None),
    ReportEntry("Present Value (leveraged)", 9,
                lambda r, m, u, p, o: present_value(r, leveraged=True),
                applies=lambda r, m: (r.valuation is not None
                                      and bool(r.loan_schedules))),
    ReportEntry("Lease Summary", 11,
                lambda r, m, u, p, o: lease_summary(
                    r, statuses=(CONTRACTUAL_STATUSES
                                 if o.get("contractual_only")
                                 else lease_summary.__kwdefaults__["statuses"])),
                note="rows carry the Contractual/Speculative provenance"),
    ReportEntry("Lease Expiration", 12,
                lambda r, m, u, p, o: lease_expiration(
                    r, fiscal_year_end_month=_fye(m),
                    statuses=(CONTRACTUAL_STATUSES
                              if o.get("contractual_only")
                              else lease_expiration.__kwdefaults__["statuses"])),
                note="rows carry the Contractual/Speculative provenance"),
    ReportEntry("Occupancy", 15,
                lambda r, m, u, p, o: occupancy(
                    r, period=p, fiscal_year_end_month=_fye(m)),
                supports_period=True),
    ReportEntry("Lease Audit", 16,
                lambda r, m, u, p, o: lease_audit_report(r)),
    ReportEntry("Recovery Audit", 18,
                lambda r, m, u, p, o: recovery_audit_report(r)),
    ReportEntry("Loan Amortization", 20,
                lambda r, m, u, p, o: loan_amortization(
                    r, loan_index=int(o.get("loan_index", 0))),
                applies=lambda r, m: bool(r.loan_schedules)),
    ReportEntry("Property Resale Audit", 21,
                lambda r, m, u, p, o: resale_audit_report(r),
                applies=lambda r, m: r.resale is not None),
    ReportEntry("Input Assumptions", 23,
                lambda r, m, u, p, o: input_assumptions_listing(m)),
    ReportEntry(
        "Benchmark Comparison", 24,
        lambda r, m, u, p, o: build_benchmark(r, m, o["benchmark_csv"]),
        applies=lambda r, m: False,   # gated on the CSV — see applicable()
        note="renders only when the property has an "
             f"{BENCHMARK_CSV_NAME} beside it (spec §9.1)"),
]


def applicable_entries(result, model,
                       benchmark_csv: Optional[Path]) -> list[ReportEntry]:
    """The picker's entries for this run: builder applicability plus the
    #24 CSV gate."""
    entries = [e for e in REGISTRY
               if e.number != 24 and e.applies(result, model)]
    if benchmark_csv is not None:
        entries.append(next(e for e in REGISTRY if e.number == 24))
    return entries


def build_entry(entry: ReportEntry, result, model, *,
                unit: Unit = Unit.total, period: Period = Period.fiscal,
                options: Optional[dict] = None) -> Report:
    """Build one picker entry — the engine builder's Report, unchanged."""
    return entry.build(result, model, unit, period, options or {})


# ------------------------------------------------------------------ #
# Benchmark Comparison (#24) wiring                                   #
# ------------------------------------------------------------------ #

def find_benchmark_csv(model_path: Optional[Path]) -> Optional[Path]:
    """The golden convention: ``expected_annual_cash_flow.csv`` in the same
    directory as the loaded ``.icprop.json``."""
    if model_path is None:
        return None
    candidate = Path(model_path).parent / BENCHMARK_CSV_NAME
    return candidate if candidate.exists() else None


def benchmark_years_from_csv(csv_path: Path) -> list[int]:
    """The FY#### columns the transcription carries."""
    with open(csv_path, encoding="utf-8", newline="") as handle:
        header = next(_csv.reader(handle))
    return sorted(int(c[2:]) for c in header
                  if c.startswith("FY") and c[2:].isdigit())


def build_benchmark(result, model, csv_path: Path) -> Report:
    """Benchmark Comparison over the property's own expected CSV — the
    engine's builder on the ledger's own fiscal aggregation (§9.1 $500
    default tolerance). CSV accounts with no ledger column of that name are
    SKIPPED AND REPORTED (``meta.extra['skipped_accounts']``), never
    silently dropped — bridging a published name to a ledger line (e.g.
    Clorox's "Capital Expenses" → "Capital Reserves") is golden-test
    knowledge the generic UI does not guess at."""
    years = benchmark_years_from_csv(csv_path)
    expected = load_expected_cash_flow(csv_path, years)
    fiscal = to_fiscal_annual(result.ledger.frame,
                              fiscal_year_end_month=_fye(model))
    unmatched = sorted(a for a in expected if a not in fiscal.columns)
    report = benchmark_comparison(fiscal, expected, fiscal_years=years,
                                  skip_accounts=unmatched)
    report.meta.extra["skipped_accounts"] = unmatched
    return report


# ------------------------------------------------------------------ #
# Date-range column slice (presentation only — never math)            #
# ------------------------------------------------------------------ #

def slice_period_columns(frame: pd.DataFrame, start_label, end_label
                         ) -> pd.DataFrame:
    """Select the column range [start_label..end_label] of a
    periods-as-columns frame (the Cash Flow layout). A pure selection —
    values untouched."""
    columns = list(frame.columns)
    a, b = columns.index(start_label), columns.index(end_label)
    if a > b:
        a, b = b, a
    return frame.iloc[:, a:b + 1]
