"""Gate 2 golden comparison — Cedar Alt Distribution Center (golden #4,
spec §9.1; NEXT_STEPS_TO_GATE2.md Step 7).

The engine's fiscal-year cash flow is compared to the OM's published
Argus-based cash flow (Argus Enterprise 14.0.2, OM p. 28 footnote;
owner-verified 2026-07-08, fixture-lock satisfied) transcribed in
``expected_annual_cash_flow.csv``.

Scope (owner-set): the **revenue / vacancy / expense / NOI** lines across all
eleven published fiscal years **FY2027-FY2037** — ten analysis years plus the
resale look-forward FY2037, which the OM publishes (ASSUMPTIONS §1). The
**capital lines (TI, LC, Capital Reserves, Total Capital Costs, CFBDS)
activate 2026-07-11 as a separate test function** (Phase 3 Step 1;
NEXT_STEPS_TO_GATE3.md criterion 1) so this file's deferred-B red assertion
stays isolated; a CFBDS miss here is the arithmetic pass-through of the
adjudicated NOI gaps plus any capital-line gap (criterion 1's 2026-07-11
supersession).

**Misses are expected output, not bugs to fix.** Per the Golden-File Strategy
(CLAUDE.md), inputs are never tuned to force a match; lines beyond the
$500/line tolerance are logged in ``DISCREPANCY_LOG.md`` and go to owner
per-cell adjudication — Claude does not resolve them. Cedar Alt's README
pre-flagged two candidates: rollover-year recovery timing during downtime
(FY2031/2034/2036) and the ~0.07% GPR day-count residual from Crane's
mid-fiscal-year rent steps.

Calendar note: Cedar Alt runs June 1 → May 31 (``fiscal_year_end_month: 5``,
the Clorox calendar), unlike Freeport's July/June (month 6).
"""
import csv
from collections import defaultdict
from pathlib import Path

import pytest

from engine.calc.ledger import to_fiscal_annual
from engine.calc.run import run_property
from engine.models.io import load_property

FIXTURE_DIR = Path(__file__).parent / "cedar_alt"
FISCAL_YEARS = list(range(2027, 2038))  # FY2027-FY2037 (11 published columns)
TOLERANCE = 500.0  # $ per line per fiscal year (spec §9.1)
FISCAL_YEAR_END_MONTH = 5  # May (analysis June 2026 → May; fixture field)

#: Capital-section lines assert in their own Gate 3 test function below
#: (activated 2026-07-11, Phase 3 Step 1) and stay excluded from the
#: Gate 2 revenue/NOI assertion so the two red sets remain separable
#: ("Capital Expenditures" has no row in Cedar Alt's CSV; harmless).
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
    model = load_property(FIXTURE_DIR / "cedar_alt.icprop.json")
    return run_property(model)


@pytest.fixture(scope="module")
def fiscal(result):
    return to_fiscal_annual(result.ledger.frame,
                            fiscal_year_end_month=FISCAL_YEAR_END_MONTH)


@pytest.fixture(scope="module")
def expected():
    """account → {fiscal_year: published $}, summing rows that share an
    account (none do in Cedar Alt's CSV, but the loader matches Freeport's)."""
    totals: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    with open(FIXTURE_DIR / "expected_annual_cash_flow.csv",
              encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            for year in FISCAL_YEARS:
                totals[row["account"]][year] += float(row[f"FY{year}"])
    return totals


def _collect_misses(fiscal, expected, years, skip_accounts=frozenset()):
    misses = []
    for account, by_year in expected.items():
        if account in skip_accounts:
            continue
        assert account in fiscal.columns, f"ledger is missing line {account!r}"
        for year in years:
            published = by_year[year]
            engine = float(fiscal.loc[year, account])
            if abs(engine - published) > TOLERANCE:
                misses.append(
                    f"  {account} FY{year}: engine {engine:,.0f} vs "
                    f"OM {published:,.0f} (diff {engine - published:+,.0f})"
                )
    return misses


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
    section — TI, LC, Capital Reserves, Total Capital Costs, CFBDS —
    across FY2027-FY2037 within $500 (NEXT_STEPS_TO_GATE3.md criterion 1).
    Misses are expected output logged in DISCREPANCY_LOG.md (root cause D;
    CFBDS additionally carries the adjudicated NOI gaps arithmetically)
    and go to owner per-cell adjudication — inputs are never tuned."""
    misses = _collect_misses(fiscal, expected, FISCAL_YEARS,
                             skip_accounts=set(expected) - GATE3_ONLY_ACCOUNTS)
    assert not misses, (
        f"{len(misses)} capital line-years beyond $500 tolerance — logged "
        "in DISCREPANCY_LOG.md (root cause D), refer to owner per-cell "
        "adjudication, do not tune inputs:\n" + "\n".join(misses)
    )


def test_monthly_sums_equal_fiscal_annual(result, fiscal):
    """Sum(monthly) = annual for every account (spec §9.3), on the fiscal
    aggregation the golden asserts against."""
    frame = result.ledger.frame
    for account in frame.columns:
        assert fiscal[account].sum() == pytest.approx(frame[account].sum())


def test_fiscal_years_cover_the_transcription(fiscal, expected):
    """The engine produces exactly the transcribed fiscal years
    FY2027-FY2037: ten analysis years plus the 12-month resale look-forward,
    which lands in FY2037 — the OM's own final published column
    (ASSUMPTIONS §1). No extra year, unlike Freeport's unpublished FY2038."""
    assert list(fiscal.index) == FISCAL_YEARS
