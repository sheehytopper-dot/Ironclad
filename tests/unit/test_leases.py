"""Unit tests for engine/calc/leases.py (Phase 1, Step 4 item 1).

Reproduces the manual's worked examples with page cites per Iron Rule 3:
base rent calculation examples [AE p. 391], rent review calculations
[AE p. 392], rental value unit [AE p. 394], CPI increases [AE pp. 255-257],
free rent element defaults [AE pp. 253-254].

Not reproduced — no §3 schema inputs exist for them in v1 (spec §3.12):
the ratchet examples, % of sales review, and average prior rent
[AE pp. 392-393].
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.leases import (
    contract_base_rent,
    cpi_adjustments,
    free_rent,
    monthly_base_rent,
    project_contract_rent,
    rent_level,
)
from engine.calc.timeline import build_month_index
from engine.models import (
    CPISpec,
    FreeRent,
    FreeRentProfile,
    Inflation,
    Lease,
    LeaseType,
    MoneyRate,
    MoneyUnit,
    RentStep,
    UponExpiration,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
MONTHS = build_month_index(BEGIN, 4)  # 4-year window + look-forward


def make_lease(amount, unit, area=2_000, start=BEGIN, term_months=60, **kwargs):
    return Lease(
        tenant_name="Example",
        area=area,
        lease_type=LeaseType.office,
        start_date=start,
        term_months=term_months,
        base_rent=MoneyRate(amount=amount, unit=unit),
        upon_expiration=UponExpiration.vacate,
        **kwargs,
    )


def flat_inflation(cpi_pct):
    return Inflation(
        general_rate=[YearRate(year=1, rate=0.0)],
        cpi_rate=[YearRate(year=1, rate=cpi_pct)],
    )


def year_sum(series, year_index):
    """Sum of analysis year N (1-based) of a monthly series."""
    lo, hi = (year_index - 1) * 12, year_index * 12
    return series.iloc[lo:hi].sum()


class TestBaseRentUnits:
    """Rental Income calculation examples — normative [AE p. 391]."""

    def test_amount_per_square_unit_per_year(self):
        """$100/SF/yr × 2,000 SF = $200,000 per year [AE p. 391]."""
        lease = make_lease(100, MoneyUnit.dollars_per_area_per_year)
        series = contract_base_rent(lease, MONTHS)
        assert year_sum(series, 1) == pytest.approx(200_000)
        assert series.iloc[0] == pytest.approx(200_000 / 12)

    def test_amount_per_square_unit_per_month(self):
        """$100/SF/mo × 2,000 SF = $200,000 per month [AE p. 391]."""
        lease = make_lease(100, MoneyUnit.dollars_per_area_per_month)
        assert contract_base_rent(lease, MONTHS).iloc[0] == pytest.approx(200_000)

    def test_amount_per_year(self):
        """$125,000/yr = $125,000 per year [AE p. 391]."""
        lease = make_lease(125_000, MoneyUnit.dollars_per_year)
        series = contract_base_rent(lease, MONTHS)
        assert year_sum(series, 1) == pytest.approx(125_000)

    def test_amount_per_month(self):
        """$15,000/mo = $15,000 per month [AE p. 391]."""
        lease = make_lease(15_000, MoneyUnit.dollars_per_month)
        assert contract_base_rent(lease, MONTHS).iloc[0] == pytest.approx(15_000)

    def test_amount_per_square_unit_per_month_second_example(self):
        """$10/SF/mo × 2,000 SF = $20,000 per month [AE p. 391]."""
        lease = make_lease(10, MoneyUnit.dollars_per_area_per_month)
        assert contract_base_rent(lease, MONTHS).iloc[0] == pytest.approx(20_000)

    def test_percent_of_market(self):
        """105% of $100,000/yr market rent = $105,000 per year [AE p. 391]."""
        lease = make_lease(105, MoneyUnit.pct_of_market)
        series = contract_base_rent(lease, MONTHS, market_rent_annual=100_000)
        assert year_sum(series, 1) == pytest.approx(105_000)

    def test_percent_of_market_requires_market_rent(self):
        """pct_of_market cannot be converted without a market rent."""
        with pytest.raises(ValueError, match="market_rent_annual"):
            monthly_base_rent(
                MoneyRate(amount=105, unit=MoneyUnit.pct_of_market), 2_000
            )

    def test_percent_of_market_with_step_amounts_compounds(self):
        """Percent steps compound multiplicatively on the prior rent
        [AE p. 391]: 100,000 × 1.05 = 105,000; × 1.05 again = $110,250."""
        lease = make_lease(
            100, MoneyUnit.pct_of_market,
            rent_steps=[
                RentStep(month_offset=12, pct_increase=5.0),
                RentStep(month_offset=24, pct_increase=5.0),
            ],
        )
        series = contract_base_rent(lease, MONTHS, market_rent_annual=100_000)
        assert year_sum(series, 1) == pytest.approx(100_000)
        assert year_sum(series, 2) == pytest.approx(105_000)
        assert year_sum(series, 3) == pytest.approx(110_250)


class TestRentReviewSteps:
    """Rent Review calculations [AE p. 392]: amount steps re-base the rent
    per their own unit."""

    def test_review_amount_per_sf_per_year(self):
        """$9/SF/yr × 2,500 SF = $22,500 per year after the review
        [AE p. 392]."""
        lease = make_lease(
            5, MoneyUnit.dollars_per_area_per_year, area=2_500,
            rent_steps=[RentStep(month_offset=12, amount=9,
                                 unit=MoneyUnit.dollars_per_area_per_year)],
        )
        series = contract_base_rent(lease, MONTHS)
        assert year_sum(series, 2) == pytest.approx(22_500)

    def test_review_amount_per_sf_per_month(self):
        """$4/SF/mo × 1,500 SF = $6,000 after the review [AE p. 392].
        (The manual prints "$6,000 per year"; the arithmetic 4 × 1,500 =
        6,000 is per month by the unit's definition — the printed unit label
        is a typo; the figure is normative.)"""
        lease = make_lease(
            2, MoneyUnit.dollars_per_area_per_month, area=1_500,
            rent_steps=[RentStep(month_offset=12, amount=4,
                                 unit=MoneyUnit.dollars_per_area_per_month)],
        )
        series = contract_base_rent(lease, MONTHS)
        assert series.iloc[12] == pytest.approx(6_000)

    def test_review_amount_per_year(self):
        """$15,000/yr after the review [AE p. 392]."""
        lease = make_lease(
            10_000, MoneyUnit.dollars_per_year,
            rent_steps=[RentStep(month_offset=12, amount=15_000,
                                 unit=MoneyUnit.dollars_per_year)],
        )
        series = contract_base_rent(lease, MONTHS)
        assert year_sum(series, 2) == pytest.approx(15_000)

    def test_review_amount_per_month(self):
        """$5,000/mo after the review [AE p. 392]."""
        lease = make_lease(
            4_000, MoneyUnit.dollars_per_month,
            rent_steps=[RentStep(month_offset=12, amount=5_000,
                                 unit=MoneyUnit.dollars_per_month)],
        )
        series = contract_base_rent(lease, MONTHS)
        assert series.iloc[12] == pytest.approx(5_000)

    def test_review_percent_of_market(self):
        """95% of $50,000 market = $47,500 after the review [AE p. 392]."""
        lease = make_lease(
            100, MoneyUnit.pct_of_market,
            rent_steps=[RentStep(month_offset=12, amount=95,
                                 unit=MoneyUnit.pct_of_market)],
        )
        series = contract_base_rent(lease, MONTHS, market_rent_annual=50_000)
        assert year_sum(series, 2) == pytest.approx(47_500)

    def test_dated_step_equivalent_to_offset(self):
        """A step located by date lands in the same month as the equivalent
        month_offset (spec §3.12; all timing snaps to months, spec §3.1)."""
        by_offset = make_lease(
            10_000, MoneyUnit.dollars_per_year,
            rent_steps=[RentStep(month_offset=12, amount=15_000,
                                 unit=MoneyUnit.dollars_per_year)],
        )
        by_date = make_lease(
            10_000, MoneyUnit.dollars_per_year,
            rent_steps=[RentStep(date=dt.date(2027, 1, 1), amount=15_000,
                                 unit=MoneyUnit.dollars_per_year)],
        )
        assert contract_base_rent(by_offset, MONTHS).equals(
            contract_base_rent(by_date, MONTHS)
        )


class TestCPIIncreases:
    """CPI increases [AE pp. 255-257] and the indexed review example
    [AE p. 392]."""

    def test_indexed_review_each_lease_year(self):
        """Indexed review at 3% CPI on $40,000 annual rent: new lease year
        rent = 40,000 × 1.03 = $41,200 [AE p. 392; "Each Lease Year" timing
        AE p. 255] — a $1,200/yr CPI adjustment on top of unchanged base."""
        lease = make_lease(40_000, MoneyUnit.dollars_per_year, cpi=CPISpec())
        cpi = cpi_adjustments(lease, MONTHS, BEGIN, flat_inflation(3.0))
        base = contract_base_rent(lease, MONTHS)
        assert year_sum(cpi, 1) == pytest.approx(0.0)
        assert year_sum(cpi, 2) == pytest.approx(1_200)
        assert year_sum(base, 2) + year_sum(cpi, 2) == pytest.approx(41_200)

    def test_pct_of_cpi_scales_the_calculated_result(self):
        """"If calculated CPI is $1,000, if you enter 57% in this field, the
        CPI rent will be $570" [AE p. 257]: $20,000 rent × 5% CPI = $1,000
        full CPI; at 57% the adjustment is $570/yr."""
        lease = make_lease(
            20_000, MoneyUnit.dollars_per_year,
            cpi=CPISpec(method="pct_of_cpi", pct=57.0),
        )
        cpi = cpi_adjustments(lease, MONTHS, BEGIN, flat_inflation(5.0))
        assert year_sum(cpi, 2) == pytest.approx(570)

    def test_maximum_increase_caps_the_rate(self):
        """Maximum increase bounds the increase over the prior rent
        [AE p. 257]: 10% CPI capped at 4% yields a 4% increase."""
        lease = make_lease(
            100_000, MoneyUnit.dollars_per_year,
            cpi=CPISpec(cap_pct=4.0),
        )
        cpi = cpi_adjustments(lease, MONTHS, BEGIN, flat_inflation(10.0))
        assert year_sum(cpi, 2) == pytest.approx(4_000)

    def test_minimum_increase_floors_the_rate(self):
        """Minimum increase bounds the increase over the prior rent
        [AE p. 257]: 1% CPI floored at 2% yields a 2% increase."""
        lease = make_lease(
            100_000, MoneyUnit.dollars_per_year,
            cpi=CPISpec(floor_pct=2.0),
        )
        cpi = cpi_adjustments(lease, MONTHS, BEGIN, flat_inflation(1.0))
        assert year_sum(cpi, 2) == pytest.approx(2_000)

    def test_cpi_compounds_on_rent_plus_prior_cpi(self):
        """The increase base is "the prior rent (rent + prior CPI)"
        [AE p. 257]: at 3%, year-3 CPI = 40,000×3% + (40,000+1,200)×3% =
        $2,436/yr."""
        lease = make_lease(40_000, MoneyUnit.dollars_per_year, cpi=CPISpec())
        cpi = cpi_adjustments(lease, MONTHS, BEGIN, flat_inflation(3.0))
        assert year_sum(cpi, 3) == pytest.approx(1_200 + 41_200 * 0.03)


class TestFreeRent:
    """Free rent element defaults [AE pp. 253-254]: base rent 100%, fixed
    steps 100%, CPI 0%."""

    def test_front_months_abate_base_rent(self):
        """New-lease free months abate base rent in the first N lease months
        [AE pp. 253-254]: 3 months on $15,000/mo → −$15,000 × 3."""
        lease = make_lease(15_000, MoneyUnit.dollars_per_month,
                           free_rent=FreeRent(months=3))
        series = free_rent(lease, MONTHS)
        assert list(series.iloc[:4]) == pytest.approx([-15_000] * 3 + [0.0])
        assert series.sum() == pytest.approx(-45_000)

    def test_fixed_steps_abate_at_100_percent(self):
        """Fixed steps are included in free rent at 100% by default
        [AE p. 254]: a free month after a step abates the stepped rent."""
        lease = make_lease(
            10_000, MoneyUnit.dollars_per_month,
            rent_steps=[RentStep(month_offset=12, amount=12_000,
                                 unit=MoneyUnit.dollars_per_month)],
            free_rent=FreeRent(months=13, timing="custom", custom_months=[13]),
        )
        series = free_rent(lease, MONTHS)
        assert series.iloc[12] == pytest.approx(-12_000)

    def test_cpi_not_abated(self):
        """CPI is included in free rent at 0% by default [AE p. 254]: a free
        month after a CPI increase abates only the base rent, and the CPI
        adjustment series is untouched."""
        lease = make_lease(
            12_000, MoneyUnit.dollars_per_year, cpi=CPISpec(),
            free_rent=FreeRent(months=13, timing="custom", custom_months=[13]),
        )
        inflation = flat_inflation(3.0)
        free = free_rent(lease, MONTHS)
        cpi = cpi_adjustments(lease, MONTHS, BEGIN, inflation)
        assert free.iloc[12] == pytest.approx(-1_000)      # base only
        assert cpi.iloc[12] == pytest.approx(12_000 * 0.03 / 12)  # unabated

    def test_fractional_free_months(self):
        """A fractional month count abates a fraction of the final free month
        (spec §3.12): 1.5 months on $10,000/mo → −10,000 then −5,000."""
        lease = make_lease(10_000, MoneyUnit.dollars_per_month,
                           free_rent=FreeRent(months=1.5))
        series = free_rent(lease, MONTHS)
        assert series.iloc[0] == pytest.approx(-10_000)
        assert series.iloc[1] == pytest.approx(-5_000)
        assert series.iloc[2] == 0.0

    def test_profile_disabling_base_rent_abates_nothing(self):
        """A free rent profile with base rent excluded abates nothing in
        Phase 1 (recoveries/misc components arrive with their modules)
        [AE pp. 253-254]."""
        lease = make_lease(10_000, MoneyUnit.dollars_per_month,
                           free_rent=FreeRent(months=2))
        profile = FreeRentProfile(name="Nothing", abate_base_rent=False)
        assert free_rent(lease, MONTHS, profile=profile).sum() == 0.0


class TestRentalValueUnit:
    """Rental Value Unit calculations [AE p. 394] — the same converter used
    for market rental values."""

    def test_amount_per_square_unit_per_year(self):
        """900 SF × $50/SF/yr = $45,000 per year [AE p. 394]."""
        monthly = monthly_base_rent(
            MoneyRate(amount=50, unit=MoneyUnit.dollars_per_area_per_year), 900
        )
        assert monthly * 12 == pytest.approx(45_000)


class TestTimelineWindowing:
    """Spec §2.3 conventions: Period[M]-indexed series, zero outside the
    lease term, correct clipping for leases straddling the window."""

    def test_series_are_period_indexed_and_zero_outside_term(self):
        lease = make_lease(12_000, MoneyUnit.dollars_per_year,
                           start=dt.date(2026, 7, 1), term_months=12)
        series = contract_base_rent(lease, MONTHS)
        assert isinstance(series.index, pd.PeriodIndex)
        assert series[pd.Period("2026-06", freq="M")] == 0.0
        assert series[pd.Period("2026-07", freq="M")] == pytest.approx(1_000)
        assert series[pd.Period("2027-06", freq="M")] == pytest.approx(1_000)
        assert series[pd.Period("2027-07", freq="M")] == 0.0

    def test_lease_started_before_window_carries_its_steps(self):
        """A lease commenced pre-analysis enters the window at its stepped
        rent (the Clorox shape: old lease, exact dollar steps)."""
        lease = make_lease(
            10_000, MoneyUnit.dollars_per_month, start=dt.date(2024, 1, 1),
            term_months=60,
            rent_steps=[RentStep(month_offset=24, amount=11_000,
                                 unit=MoneyUnit.dollars_per_month)],
        )
        series = contract_base_rent(lease, MONTHS)
        assert series.iloc[0] == pytest.approx(11_000)  # Jan 2026 = month 24

    def test_project_contract_rent_bundles_all_three_series(self):
        lease = make_lease(12_000, MoneyUnit.dollars_per_year, cpi=CPISpec(),
                           free_rent=FreeRent(months=1))
        flows = project_contract_rent(
            lease, MONTHS, BEGIN, inflation=flat_inflation(3.0)
        )
        assert flows.base_rent.iloc[0] == pytest.approx(1_000)
        assert flows.free_rent.iloc[0] == pytest.approx(-1_000)
        assert flows.cpi_adjustment.iloc[12] == pytest.approx(30.0)

    def test_cpi_requires_inflation(self):
        lease = make_lease(12_000, MoneyUnit.dollars_per_year, cpi=CPISpec())
        with pytest.raises(ValueError, match="inflation"):
            project_contract_rent(lease, MONTHS, BEGIN)
