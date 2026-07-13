"""Gate 1 golden comparison — Clorox Northlake (golden #1, spec §9.1;
NEXT_STEPS_TO_GATE1.md Step 5).

The engine's fiscal-year cash flow is compared to the OM's published
Argus-based cash flow transcribed in ``expected_annual_cash_flow.csv``
(owner-verified 2026-07-04, fixture-lock satisfied). Assertion phasing is
owner-approved (2026-07-03):

- **Gate 1: FY2027 and FY2028, every line within $500** (passed
  2026-07-05).
- **Gate 2 scope (activated 2026-07-06 with rollover projection):
  FY2029-FY2031 revenue, vacancy, expense, and NOI lines.**
- **Gate 3 scope (activated 2026-07-11 with TI/LC posting, Phase 3
  Step 1): FY2029-FY2031 Tenant Improvements, Leasing Commissions,
  Capital Expenses, Total Capital Costs, and CFBDS** join the same test
  (NEXT_STEPS_TO_GATE3.md criterion 1). Amortized CAM Revenue stays
  unasserted but is arithmetically pinned by the Total Capital Costs
  assertion. FY2032 is the resale look-forward (Phase 3, later steps) —
  transcribed but not asserted yet.

Disputes beyond tolerance go to owner per-cell adjudication (NEXT_STEPS
Step 3) — inputs are never tuned to force a match (fixture-lock rule).

Account-name note: the CSV's "Capital Expenses" row is the spec §2.3 line
name for the OM's Capital Reserves line; the engine posts the expense under
its fixture input name ("Capital Reserves"). The mapping below bridges the
two so neither the locked fixture nor the locked CSV needs editing.
"""
import csv
from pathlib import Path

import pytest

from engine.calc.ledger import to_fiscal_annual
from engine.calc.run import run_property
from engine.models.io import load_property
from engine.reports import benchmark_comparison, miss_lines

FIXTURE_DIR = Path(__file__).parent / "clorox_northlake"
GATE1_FISCAL_YEARS = [2027, 2028]
GATE2_FISCAL_YEARS = [2029, 2030, 2031]
TOLERANCE = 500.0  # $ per line per fiscal year (spec §9.1)

#: CSV account name → engine ledger column, where the two differ.
ACCOUNT_TO_COLUMN = {"Capital Expenses": "Capital Reserves"}

#: Still-skipped capital line (Phase 3 Step 1 activated the rest,
#: 2026-07-11): Amortized CAM Revenue is pinned by the Total Capital
#: Costs assertion (zero in FY2029-FY2031 on both sides).
GATE3_ONLY_ACCOUNTS = {
    "Amortized CAM Revenue",
}


@pytest.fixture(scope="module")
def result():
    model = load_property(FIXTURE_DIR / "clorox_northlake.icprop.json")
    return run_property(model)


@pytest.fixture(scope="module")
def fiscal(result):
    return to_fiscal_annual(result.ledger.frame, fiscal_year_end_month=5)


@pytest.fixture(scope="module")
def expected():
    with open(FIXTURE_DIR / "expected_annual_cash_flow.csv",
              encoding="utf-8", newline="") as handle:
        return {row["account"]: row for row in csv.DictReader(handle)}


def _collect_misses(fiscal, expected, years, skip_accounts=frozenset()):
    """The per-line diff, delegated to the reusable Benchmark Comparison
    builder (spec §7 report 24; engine/reports/benchmark.py). Identical
    comparison and miss-line formatting as before the Phase 4 Step 2
    refactor. ``expected`` here is ``{account: csv_row}`` (this file's
    fixture shape), reshaped to the builder's ``{account: {year: $}}``; the
    ``ACCOUNT_TO_COLUMN`` bridge (Capital Expenses → Capital Reserves) is
    passed through unchanged."""
    by_account = {account: {year: float(row[f"FY{year}"]) for year in years}
                  for account, row in expected.items()}
    report = benchmark_comparison(fiscal, by_account, fiscal_years=years,
                                  tolerance=TOLERANCE,
                                  account_to_column=ACCOUNT_TO_COLUMN,
                                  skip_accounts=skip_accounts)
    return miss_lines(report)


def test_gate1_every_line_within_tolerance(fiscal, expected):
    """Gate 1: FY2027 + FY2028, every transcribed line within $500 of the
    OM's published Argus cash flow (spec §9.1, §10 Phase 1 gate)."""
    misses = _collect_misses(fiscal, expected, GATE1_FISCAL_YEARS)
    assert not misses, (
        "Gate 1 lines beyond $500 tolerance — refer to owner per-cell "
        "adjudication (NEXT_STEPS Step 3), do not tune inputs:\n"
        + "\n".join(misses)
    )


def test_gate2_rollover_years_within_tolerance(fiscal, expected):
    """Gate 2 scope: FY2029-FY2031 revenue/vacancy/expense/NOI lines within
    $500 — the rollover-blending validation §4.2 calls the most common
    source of divergence. Gate 3 scope (2026-07-11): TI, LC, Capital
    Expenses, Total Capital Costs, and CFBDS join for the same years
    (Phase 3 Step 1; NEXT_STEPS_TO_GATE3.md criterion 1)."""
    misses = _collect_misses(fiscal, expected, GATE2_FISCAL_YEARS,
                             skip_accounts=GATE3_ONLY_ACCOUNTS)
    assert not misses, (
        "Gate 2 lines beyond $500 tolerance — refer to owner per-cell "
        "adjudication (NEXT_STEPS_TO_GATE2.md), do not tune inputs:\n"
        + "\n".join(misses)
    )


def test_monthly_sums_equal_fiscal_annual(result, fiscal):
    """Sum(monthly) = annual for every account (spec §9.3), on the fiscal
    aggregation the golden asserts against."""
    frame = result.ledger.frame
    for account in frame.columns:
        assert fiscal[account].sum() == pytest.approx(frame[account].sum())


def test_fiscal_years_cover_the_transcription(fiscal, expected):
    """The engine timeline produces exactly the transcribed fiscal years
    FY2027-FY2032 (5 analysis years + resale look-forward, June-May)."""
    sample = next(iter(expected.values()))
    csv_years = sorted(
        int(key[2:]) for key in sample if key.startswith("FY")
    )
    assert list(fiscal.index) == csv_years
