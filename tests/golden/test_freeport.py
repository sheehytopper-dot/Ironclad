"""Gate 2 golden comparison — 8505 Freeport Parkway (golden #2, spec §9.1;
NEXT_STEPS_TO_GATE2.md Step 7).

The engine's fiscal-year cash flow is compared to the OM's published
Argus-based cash flow (Argus Enterprise; owner-verified 2026-07-08,
fixture-lock satisfied) transcribed in ``expected_annual_cash_flow.csv``.

Scope (owner-set): the **revenue / vacancy / expense / NOI** lines across all
eleven published fiscal years **FY2027-FY2037** — Freeport's rollover touches
every year, so there is no clean contract-only early subset like Clorox's
FY2027-FY2028 (README). The **capital lines (TI, LC, Capital
Expenditures/Reserves, Total Capital Costs, CFBDS) activate 2026-07-11
as a separate test function** (Phase 3 Step 1; NEXT_STEPS_TO_GATE3.md
criterion 1) so this file's deferred-B red assertion stays isolated; a
CFBDS miss here is the arithmetic pass-through of the adjudicated NOI
gaps plus any capital-line gap (criterion 1's 2026-07-11 supersession).

**Misses are expected output, not bugs to fix.** Per the Golden-File Strategy
(CLAUDE.md), inputs are never tuned to force a match; lines beyond the
$500/line tolerance are logged in ``DISCREPANCY_LOG.md`` and go to owner
per-cell adjudication — Claude does not resolve them. Two large families are
already-documented open questions: the base-year / MLP-electricity recovery
gap understating Expense Recovery Revenue (DEVIATIONS.md §5/§7) and the
undetermined general-vacancy basis (ASSUMPTIONS §8).

CSV structure note: three rows (Parking Income, Other Income, Pylon / Facia
Sign Rental) share the account ``Parking / Storage / Miscellaneous Property
Revenue`` — they are summed to compare against the single ledger column.
"""
import csv
from collections import defaultdict
from pathlib import Path

import pytest

from engine.calc.ledger import to_fiscal_annual
from engine.calc.run import run_property
from engine.models.io import load_property
from engine.reports import benchmark_comparison, miss_lines

FIXTURE_DIR = Path(__file__).parent / "freeport"
FISCAL_YEARS = list(range(2027, 2038))  # FY2027-FY2037 (11 published columns)
TOLERANCE = 500.0  # $ per line per fiscal year (spec §9.1)
FISCAL_YEAR_END_MONTH = 6  # June (analysis July 2026 → June)

#: Capital-section lines assert in their own Gate 3 test function below
#: (activated 2026-07-11, Phase 3 Step 1) and stay excluded from the
#: Gate 2 revenue/NOI assertion so the two red sets remain separable.
GATE3_ONLY_ACCOUNTS = {
    "Tenant Improvements",
    "Leasing Commissions",
    "Capital Expenditures",
    "Capital Reserves",
    "Total Capital Costs",
    "Cash Flow Before Debt Service",
}


@pytest.fixture(scope="module")
def result():
    model = load_property(FIXTURE_DIR / "freeport.icprop.json")
    return run_property(model)


@pytest.fixture(scope="module")
def fiscal(result):
    return to_fiscal_annual(result.ledger.frame,
                            fiscal_year_end_month=FISCAL_YEAR_END_MONTH)


@pytest.fixture(scope="module")
def expected():
    """account → {fiscal_year: published $}, summing rows that share an
    account (the three property-revenue lines)."""
    totals: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    with open(FIXTURE_DIR / "expected_annual_cash_flow.csv",
              encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            for year in FISCAL_YEARS:
                totals[row["account"]][year] += float(row[f"FY{year}"])
    return totals


def _collect_misses(fiscal, expected, years, skip_accounts=frozenset()):
    """The per-line diff, delegated to the reusable Benchmark Comparison
    builder (spec §7 report 24; engine/reports/benchmark.py). Identical
    comparison and miss-line formatting as before the Phase 4 Step 2
    refactor — the by-design red counts are unchanged."""
    report = benchmark_comparison(fiscal, expected, fiscal_years=years,
                                  tolerance=TOLERANCE,
                                  skip_accounts=skip_accounts)
    return miss_lines(report)


def test_gate2_revenue_vacancy_expense_noi_within_tolerance(fiscal, expected):
    """Gate 2 scope: FY2027-FY2037 revenue/vacancy/expense/NOI lines within
    $500 of the OM's published Argus cash flow. Misses are logged in
    DISCREPANCY_LOG.md for owner per-cell adjudication — inputs are never
    tuned to force a match (fixture-lock rule)."""
    misses = _collect_misses(fiscal, expected, FISCAL_YEARS,
                             skip_accounts=GATE3_ONLY_ACCOUNTS)
    assert not misses, (
        f"{len(misses)} line-years beyond $500 tolerance — logged in "
        "DISCREPANCY_LOG.md, refer to owner per-cell adjudication "
        "(NEXT_STEPS_TO_GATE2.md), do not tune inputs:\n"
        + "\n".join(misses)
    )


def test_gate3_capital_lines_within_tolerance(fiscal, expected):
    """Gate 3 scope (Phase 3 Step 1, activated 2026-07-11): the capital
    section — TI, LC, Capital Expenditures, Capital Reserves, Total
    Capital Costs, CFBDS — across FY2027-FY2037 within $500
    (NEXT_STEPS_TO_GATE3.md criterion 1). Misses are expected output
    logged in DISCREPANCY_LOG.md (root cause E; CFBDS additionally
    carries the adjudicated NOI gaps arithmetically) and go to owner
    per-cell adjudication — inputs are never tuned."""
    misses = _collect_misses(fiscal, expected, FISCAL_YEARS,
                             skip_accounts=set(expected) - GATE3_ONLY_ACCOUNTS)
    assert not misses, (
        f"{len(misses)} capital line-years beyond $500 tolerance — logged "
        "in DISCREPANCY_LOG.md (root cause E), refer to owner per-cell "
        "adjudication, do not tune inputs:\n" + "\n".join(misses)
    )


def test_monthly_sums_equal_fiscal_annual(result, fiscal):
    """Sum(monthly) = annual for every account (spec §9.3), on the fiscal
    aggregation the golden asserts against."""
    frame = result.ledger.frame
    for account in frame.columns:
        assert fiscal[account].sum() == pytest.approx(frame[account].sum())


def test_fiscal_years_cover_the_transcription(fiscal, expected):
    """The engine produces every transcribed fiscal year FY2027-FY2037 (the
    OM's full 11-year projection), plus one more — FY2038 — from the engine's
    12-month resale look-forward, which the OM did not publish and the
    comparison does not assert."""
    assert list(fiscal.index) == FISCAL_YEARS + [2038]
