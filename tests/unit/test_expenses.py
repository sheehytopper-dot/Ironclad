"""Unit tests for engine/calc/expenses.py (Phase 1, Step 4 item 2).

Reproduces the manual's Repeating Payments calculation examples with page
cites per Iron Rule 3 [AE pp. 361-362], plus the §3.10/§3.11 unit, timing,
inflation, occupancy-scaling, and limits semantics [AE pp. 313-345, 279].

The manual states repeating amounts via a Frequency + Repeat pair; the §3
schema states the amount's frequency in its unit (``dollars_per_year``,
``dollars_per_month``) and the repeat interval in ``Timing`` — quarterly and
semi-annual amounts are entered as their annual totals. Each test docstring
maps its example accordingly.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.expenses import project_expense
from engine.calc.timeline import build_month_index
from engine.models import (
    AnnualOverride,
    ExpenseItem,
    ExpenseUnit,
    Inflation,
    Limits,
    Timing,
    TimingMethod,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
MONTHS = build_month_index(BEGIN, 3)

FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)])
TEN_PCT = Inflation(
    general_rate=[YearRate(year=1, rate=0.0)],
    expense_rate=[YearRate(year=1, rate=10.0)],
)


def make_item(amount, unit, timing=None, **kwargs):
    return ExpenseItem(
        name="Test Expense", amount=amount, unit=unit,
        timing=timing or Timing(), **kwargs,
    )


def repeating(every=None, months_list=None, start=None, end=None):
    return Timing(
        method=TimingMethod.repeating,
        start=start, end=end,
        repeat_every_months=every, repeat_months=months_list,
    )


class TestRepeatingPayments:
    """Repeating Payments calculation examples [AE pp. 361-362]."""

    def test_annual_repeat_quarterly(self):
        """Annual $12,000 repeating quarterly posts $3,000 every third month
        from trigger [AE p. 361]."""
        item = make_item(12_000, ExpenseUnit.dollars_per_year, repeating(every=3))
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert series.iloc[0] == pytest.approx(3_000)
        assert series.iloc[3] == pytest.approx(3_000)
        assert series.iloc[1] == 0.0
        assert series.iloc[:12].sum() == pytest.approx(12_000)

    def test_annual_repeat_monthly(self):
        """Annual $12,000 repeating monthly posts $1,000 every month
        [AE p. 361]."""
        item = make_item(12_000, ExpenseUnit.dollars_per_year, repeating(every=1))
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert list(series.iloc[:12]) == pytest.approx([1_000.0] * 12)

    def test_annual_repeat_semi_annually(self):
        """Annual $12,000 repeating semi-annually posts $6,000 every sixth
        month [AE p. 361]."""
        item = make_item(12_000, ExpenseUnit.dollars_per_year, repeating(every=6))
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert series.iloc[0] == pytest.approx(6_000)
        assert series.iloc[6] == pytest.approx(6_000)
        assert series.iloc[1:6].sum() == 0.0

    def test_monthly_repeat_monthly(self):
        """Monthly $12,000 repeating monthly posts $12,000 every month
        [AE p. 361]."""
        item = make_item(12_000, ExpenseUnit.dollars_per_month, repeating(every=1))
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert list(series.iloc[:12]) == pytest.approx([12_000.0] * 12)

    def test_quarterly_amount_repeat_quarterly(self):
        """Quarterly $12,000 repeating quarterly posts $12,000 every third
        month [AE p. 361]; the schema states the quarterly amount as its
        annual total ($48,000/yr)."""
        item = make_item(48_000, ExpenseUnit.dollars_per_year, repeating(every=3))
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert series.iloc[0] == pytest.approx(12_000)
        assert series.iloc[3] == pytest.approx(12_000)

    def test_semi_annual_amount_repeat_semi_annually(self):
        """Semi-annual $12,000 repeating semi-annually posts $12,000 every
        sixth month [AE p. 361]; entered as its annual total ($24,000/yr)."""
        item = make_item(24_000, ExpenseUnit.dollars_per_year, repeating(every=6))
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert series.iloc[0] == pytest.approx(12_000)
        assert series.iloc[6] == pytest.approx(12_000)

    def test_repeat_annually(self):
        """$12,000 repeating annually posts $12,000 every year from trigger
        [AE pp. 361-362]; entered as $1,000/mo repeating every 12 months."""
        item = make_item(1_000, ExpenseUnit.dollars_per_month, repeating(every=12))
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert series.iloc[0] == pytest.approx(12_000)
        assert series.iloc[12] == pytest.approx(12_000)
        assert series.iloc[1:12].sum() == 0.0

    def test_single_payment_annualized_at_trigger(self):
        """A single payment posts the amount annualized at the trigger
        [AE p. 362]: $1,000/mo, trigger June 2026, one 12-month posting."""
        item = make_item(
            1_000, ExpenseUnit.dollars_per_month,
            repeating(every=12, start=dt.date(2026, 6, 1), end=dt.date(2026, 6, 30)),
        )
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert series[pd.Period("2026-06", freq="M")] == pytest.approx(12_000)
        assert series.sum() == pytest.approx(12_000)

    def test_inflated_amount_times_interval(self):
        """A repeating posting is the inflated amount for the trigger month
        multiplied by the interval [AE p. 362]: $1,000/mo quarterly at 10%
        expense inflation posts 1,100 × 3 in analysis year 2."""
        item = make_item(1_000, ExpenseUnit.dollars_per_month, repeating(every=3))
        series = project_expense(item, MONTHS, BEGIN, TEN_PCT)
        assert series.iloc[0] == pytest.approx(3_000)          # year 1
        assert series.iloc[12] == pytest.approx(3_300)         # year 2: 1,100 × 3
        assert series.iloc[:12].sum() == pytest.approx(12_000)
        assert series.iloc[12:24].sum() == pytest.approx(13_200)

    def test_calendar_repeat_months(self):
        """``repeat_months`` posts in the listed calendar months, each
        covering the cyclic gap (spec §3.11 schema form of the accrual rule
        [AE pp. 361-362]): $120,000/yr in [6, 12] → $60,000 each June and
        December."""
        item = make_item(
            120_000, ExpenseUnit.dollars_per_year, repeating(months_list=[6, 12])
        )
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert series[pd.Period("2026-06", freq="M")] == pytest.approx(60_000)
        assert series[pd.Period("2026-12", freq="M")] == pytest.approx(60_000)
        assert series.iloc[:12].sum() == pytest.approx(120_000)


class TestUnitsAndScaling:
    """Amount/unit types and %-fixed occupancy scaling (spec §3.10/§3.11)."""

    def test_dollars_per_area_per_year(self):
        item = make_item(2.10, ExpenseUnit.dollars_per_area_per_year)
        series = project_expense(item, MONTHS, BEGIN, FLAT, area=120_000)
        assert series.iloc[0] == pytest.approx(2.10 * 120_000 / 12)
        assert series.iloc[:12].sum() == pytest.approx(252_000)

    def test_dollars_per_area_per_month(self):
        item = make_item(0.75, ExpenseUnit.dollars_per_area_per_month)
        series = project_expense(item, MONTHS, BEGIN, FLAT, area=10_000)
        assert series.iloc[0] == pytest.approx(7_500)

    def test_pct_fixed_scales_variable_portion_with_occupancy(self):
        """Variable portion scales with occupancy (spec §3.11): 50% fixed at
        80% occupancy → amount × (0.5 + 0.5 × 0.8) = 90% of full."""
        item = make_item(1_200, ExpenseUnit.dollars_per_year, pct_fixed=50.0)
        series = project_expense(item, MONTHS, BEGIN, FLAT, occupancy=0.8)
        assert series.iloc[0] == pytest.approx(100 * 0.9)

    def test_per_occupied_area(self):
        """$/occupied SF/yr on the monthly occupied-area series (spec §3.10)."""
        occupied = pd.Series(30_000.0, index=MONTHS)
        item = make_item(1.20, ExpenseUnit.per_occupied_area)
        series = project_expense(item, MONTHS, BEGIN, FLAT, occupied_area=occupied)
        assert series.iloc[0] == pytest.approx(1.20 * 30_000 / 12)

    def test_per_available_area(self):
        """$/available SF/yr on the monthly vacant-area series (spec §3.10)."""
        available = pd.Series(5_000.0, index=MONTHS)
        item = make_item(2.40, ExpenseUnit.per_available_area)
        series = project_expense(item, MONTHS, BEGIN, FLAT, available_area=available)
        assert series.iloc[0] == pytest.approx(1_000)

    def test_pct_of_egr_applies_percentage_to_reference(self):
        """A %-of-EGR item is amount% of the reference series and carries no
        inflation of its own — the reference already inflates (spec §3.10,
        §4.1 step 9; the Clorox management fee shape)."""
        egr = pd.Series(100_000.0, index=MONTHS)
        item = make_item(3.0, ExpenseUnit.pct_of_egr)
        series = project_expense(item, MONTHS, BEGIN, TEN_PCT, reference=egr)
        assert series.iloc[0] == pytest.approx(3_000)
        assert series.iloc[12] == pytest.approx(3_000)  # no double inflation

    def test_pct_unit_requires_reference(self):
        item = make_item(3.0, ExpenseUnit.pct_of_egr)
        with pytest.raises(ValueError, match="reference"):
            project_expense(item, MONTHS, BEGIN, FLAT)


class TestTimingInflationLimits:
    """Date-range windows, inflation index selection, and per-period limits
    [AE p. 279; spec §3.3, §3.10-3.11]."""

    def test_date_range_window(self):
        item = make_item(
            1_200, ExpenseUnit.dollars_per_year,
            timing=Timing(method=TimingMethod.date_range,
                          start=dt.date(2026, 6, 1), end=dt.date(2026, 8, 31)),
        )
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert series[pd.Period("2026-05", freq="M")] == 0.0
        assert series[pd.Period("2026-06", freq="M")] == pytest.approx(100)
        assert series[pd.Period("2026-08", freq="M")] == pytest.approx(100)
        assert series[pd.Period("2026-09", freq="M")] == 0.0

    def test_default_expense_index_and_explicit_override(self):
        """Expenses inflate on the expense index by default; an explicit
        YearRate schedule overrides it (spec §3.3, §3.11)."""
        default = make_item(1_200, ExpenseUnit.dollars_per_year)
        assert project_expense(default, MONTHS, BEGIN, TEN_PCT).iloc[12] == pytest.approx(110)
        flat = make_item(
            1_200, ExpenseUnit.dollars_per_year,
            inflation=[YearRate(year=1, rate=0.0)],
        )
        assert project_expense(flat, MONTHS, BEGIN, TEN_PCT).iloc[12] == pytest.approx(100)

    def test_limits_clamp_per_month(self):
        """Per-period max clamps the monthly amount [AE p. 279]."""
        item = make_item(1_200, ExpenseUnit.dollars_per_year,
                         limits=Limits(max=80.0))
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert list(series) == pytest.approx([80.0] * len(series))

    def test_limits_min_applies_only_to_active_months(self):
        """A min limit raises active postings, never the zero months between
        repeating postings [AE p. 279]."""
        item = make_item(
            12_000, ExpenseUnit.dollars_per_year,
            timing=repeating(every=3), limits=Limits(min=5_000.0),
        )
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert series.iloc[0] == pytest.approx(5_000)
        assert series.iloc[1] == 0.0


class TestAnnualOverrides:
    """Known per-year actuals win completely for their fiscal year while
    surrounding years compute normally (DEVIATIONS.md §12; engineered escape
    hatch, no manual worked example). ``MONTHS`` is calendar-aligned (Jan
    begin), so the default December fiscal-year-end makes fiscal year =
    calendar year here."""

    def test_override_year_used_directly_surrounding_years_grow_off_base(self):
        """A $1,200/yr expense inflating 10%/yr: 2026 base $1,200, 2027 would
        be $1,320. Override 2027 to a known $5,000 → 2027 posts $5,000/12 per
        month ($5,000 total); 2026 and 2028 still compute off the base
        ($1,200 and $1,452 = 1,200×1.21) — the override does not re-base the
        formula."""
        item = make_item(
            1_200, ExpenseUnit.dollars_per_year,
            annual_overrides=[AnnualOverride(year=2027, amount=5_000.0)],
        )
        series = project_expense(item, MONTHS, BEGIN, TEN_PCT)
        assert series.iloc[0] == pytest.approx(100.0)           # 2026 base
        assert series.iloc[:12].sum() == pytest.approx(1_200)   # 2026 total
        assert series.iloc[12] == pytest.approx(5_000 / 12)     # 2027 override
        assert series.iloc[12:24].sum() == pytest.approx(5_000)  # 2027 total
        assert series.iloc[24] == pytest.approx(121.0)          # 2028: 1,200×1.21/12
        assert series.iloc[24:36].sum() == pytest.approx(1_452)  # off base, not 5,000

    def test_multiple_year_overrides(self):
        """Overrides for two years both apply; unlisted years compute."""
        item = make_item(
            1_200, ExpenseUnit.dollars_per_year,
            annual_overrides=[AnnualOverride(year=2027, amount=5_000.0),
                              AnnualOverride(year=2028, amount=9_000.0)],
        )
        series = project_expense(item, MONTHS, BEGIN, TEN_PCT)
        assert series.iloc[:12].sum() == pytest.approx(1_200)   # 2026 computed
        assert series.iloc[12:24].sum() == pytest.approx(5_000)  # 2027 override
        assert series.iloc[24:36].sum() == pytest.approx(9_000)  # 2028 override
        assert series.iloc[36:48].sum() == pytest.approx(1_200 * 1.1 ** 3)  # 2029 computed

    def test_override_wins_over_limits(self):
        """The override is applied after — and is not re-clamped by — the
        limits clamp (override wins completely). A max of $80/mo clamps the
        computed months; the overridden year posts $5,000/12 = $416.67/mo,
        well above the cap, untouched."""
        item = make_item(
            1_200, ExpenseUnit.dollars_per_year, limits=Limits(max=80.0),
            annual_overrides=[AnnualOverride(year=2027, amount=5_000.0)],
        )
        series = project_expense(item, MONTHS, BEGIN, FLAT)
        assert series.iloc[0] == pytest.approx(80.0)            # 2026 clamped
        assert series.iloc[12] == pytest.approx(5_000 / 12)     # 2027 override, not 80

    def test_fiscal_year_matching_off_calendar(self):
        """With a May (5) fiscal-year-end — the Cedar Alt shape — an override
        for fiscal year 2027 covers Jun-2026 through May-2027, and nothing
        outside it. A flat $2,400/yr expense ($200/mo) with FY2027 overridden
        to $1,200 ($100/mo): the FY2027 window posts $100, the FY2026 tail
        (Jan-May 2026) and the FY2028 start (Jun-2027) keep the computed
        $200."""
        item = make_item(
            2_400, ExpenseUnit.dollars_per_year,
            annual_overrides=[AnnualOverride(year=2027, amount=1_200.0)],
        )
        series = project_expense(item, MONTHS, BEGIN, FLAT,
                                 fiscal_year_end_month=5)
        assert series[pd.Period("2026-05", freq="M")] == pytest.approx(200)  # FY2026
        assert series[pd.Period("2026-06", freq="M")] == pytest.approx(100)  # FY2027
        assert series[pd.Period("2027-05", freq="M")] == pytest.approx(100)  # FY2027
        assert series[pd.Period("2027-06", freq="M")] == pytest.approx(200)  # FY2028

    def test_duplicate_override_year_rejected(self):
        """Two amounts for the same year is a contradiction — rejected."""
        with pytest.raises(ValueError, match="same year"):
            make_item(1_200, ExpenseUnit.dollars_per_year,
                      annual_overrides=[AnnualOverride(year=2027, amount=1.0),
                                        AnnualOverride(year=2027, amount=2.0)])
