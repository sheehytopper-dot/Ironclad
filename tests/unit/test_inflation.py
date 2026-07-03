"""Unit tests for engine/calc/inflation.py (Phase 0) [AE pp. 219-223].

Normative behavior under test (spec §3.3): inflation factor for month m =
Π(1 + rate_y) over completed inflation anniversaries before or at m; rates
step on ``inflation_month``, and mid-year analysis starts must respect it.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.inflation import factor_table, inflation_factors, rate_for_year
from engine.calc.timeline import build_month_index
from engine.models import CustomIndex, Inflation, TimingBasis, YearRate


def factors(rates, begin, years=3, inflation_month=None, basis=TimingBasis.analysis_year):
    months = build_month_index(begin, years)
    return inflation_factors(
        [YearRate(year=y, rate=r) for y, r in rates],
        months,
        begin,
        inflation_month,
        basis,
    )


class TestBasicCompounding:
    def test_year_one_is_uninflated(self):
        """Year-1 amounts are stated in year-1 dollars: factor 1.0 for all 12
        months before the first anniversary [AE pp. 219-223]."""
        s = factors([(1, 3.0)], dt.date(2026, 1, 1))
        assert (s[pd.Period("2026-01", freq="M"):pd.Period("2026-12", freq="M")] == 1.0).all()

    def test_rates_compound_on_anniversaries(self):
        """3% then 2.5%: year 2 factor = 1.03, year 3 = 1.03 × 1.025
        (spec §3.3: Π(1 + rate_y) over completed anniversaries)."""
        s = factors([(1, 3.0), (2, 3.0), (3, 2.5)], dt.date(2026, 1, 1))
        assert s[pd.Period("2027-01", freq="M")] == pytest.approx(1.03)
        assert s[pd.Period("2027-12", freq="M")] == pytest.approx(1.03)
        assert s[pd.Period("2028-01", freq="M")] == pytest.approx(1.03 * 1.025)

    def test_last_rate_carries_forward(self):
        """A schedule shorter than the term carries its last rate forward."""
        s = factors([(1, 3.0)], dt.date(2026, 1, 1), years=4)
        assert s[pd.Period("2030-01", freq="M")] == pytest.approx(1.03**4)

    def test_empty_schedule_is_flat(self):
        s = factors([], dt.date(2026, 1, 1))
        assert (s == 1.0).all()


class TestMidYearAnalysisStart:
    """Mid-year starts must respect inflation_month: rates step on that month,
    not necessarily January and not necessarily the analysis anniversary
    (spec §3.3) [AE pp. 219-223]."""

    def test_default_steps_on_analysis_anniversary(self):
        """July 2026 start, default inflation_month (= July): June 2027 is
        still uninflated; July 2027 steps to 1.03; July 2028 to 1.03²."""
        s = factors([(1, 3.0)], dt.date(2026, 7, 1))
        assert s[pd.Period("2027-06", freq="M")] == 1.0
        assert s[pd.Period("2027-07", freq="M")] == pytest.approx(1.03)
        assert s[pd.Period("2028-06", freq="M")] == pytest.approx(1.03)
        assert s[pd.Period("2028-07", freq="M")] == pytest.approx(1.03**2)

    def test_explicit_inflation_month_overrides_anniversary(self):
        """July 2026 start with inflation_month=1: the first step lands on
        January 2027 — six months in — not on the July analysis anniversary."""
        s = factors([(1, 3.0), (2, 3.0)], dt.date(2026, 7, 1), inflation_month=1)
        assert s[pd.Period("2026-12", freq="M")] == 1.0
        assert s[pd.Period("2027-01", freq="M")] == pytest.approx(1.03)
        assert s[pd.Period("2027-07", freq="M")] == pytest.approx(1.03)  # no July step
        assert s[pd.Period("2028-01", freq="M")] == pytest.approx(1.03**2)

    def test_mid_year_start_calendar_year_basis(self):
        """Calendar-year basis keys rates by calendar year: with a July 2026
        start, inflation_month=1, and distinct rates for 2027/2028, the
        January 2027 step uses the 2027 rate and January 2028 the 2028 rate."""
        s = factors(
            [(2027, 4.0), (2028, 2.0)],
            dt.date(2026, 7, 1),
            inflation_month=1,
            basis=TimingBasis.calendar_year,
        )
        assert s[pd.Period("2026-12", freq="M")] == 1.0
        assert s[pd.Period("2027-01", freq="M")] == pytest.approx(1.04)
        assert s[pd.Period("2028-01", freq="M")] == pytest.approx(1.04 * 1.02)


class TestRateLookup:
    def test_rate_for_year_carry_forward(self):
        rates = [YearRate(year=1, rate=3.0), YearRate(year=3, rate=2.0)]
        assert rate_for_year(rates, 1) == 3.0
        assert rate_for_year(rates, 2) == 3.0
        assert rate_for_year(rates, 3) == 2.0
        assert rate_for_year(rates, 10) == 2.0

    def test_years_before_first_entry_are_zero(self):
        assert rate_for_year([YearRate(year=3, rate=2.0)], 2) == 0.0


class TestFactorTable:
    def test_all_indices_present_and_defaulted(self):
        """market_rent/expense/cpi default to the general index when not
        given; custom indices get their own column (spec §3.3, §4.1 step 2)."""
        begin = dt.date(2026, 1, 1)
        inflation = Inflation(
            general_rate=[YearRate(year=1, rate=3.0)],
            market_rent_rate=[YearRate(year=1, rate=4.0)],
            custom_indices=[CustomIndex(name="utility_index", rates=[YearRate(year=1, rate=5.0)])],
        )
        table = factor_table(inflation, build_month_index(begin, 2), begin)
        assert list(table.columns) == ["general", "market_rent", "expense", "cpi", "utility_index"]
        feb_2027 = pd.Period("2027-02", freq="M")
        assert table.loc[feb_2027, "general"] == pytest.approx(1.03)
        assert table.loc[feb_2027, "market_rent"] == pytest.approx(1.04)
        assert table.loc[feb_2027, "expense"] == pytest.approx(1.03)  # defaulted
        assert table.loc[feb_2027, "cpi"] == pytest.approx(1.03)      # defaulted
        assert table.loc[feb_2027, "utility_index"] == pytest.approx(1.05)

    def test_inflation_month_from_model(self):
        """factor_table honors Inflation.inflation_month for mid-year starts."""
        begin = dt.date(2026, 7, 1)
        inflation = Inflation(
            general_rate=[YearRate(year=1, rate=3.0)],
            inflation_month=1,
        )
        table = factor_table(inflation, build_month_index(begin, 2), begin)
        assert table.loc[pd.Period("2026-12", freq="M"), "general"] == 1.0
        assert table.loc[pd.Period("2027-01", freq="M"), "general"] == pytest.approx(1.03)
