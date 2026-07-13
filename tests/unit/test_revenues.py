"""Unit tests for engine/calc/revenues.py — property revenues (spec §3.10,
§4.1 step 9).

The manual gives structure, not numeric worked examples, for misc/parking/
storage income; these are engineered tests (same precedent as annual_overrides
and the %-of-EGR fixed point). Direct-projection tests pin the unit semantics;
the run_property tests pin the two-pass integration — absolute lines join PGR
once, %-of-EGR lines resolve in the same fixed point as the management fee
(DEVIATIONS.md §13).
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.revenues import project_property_revenue
from engine.calc.run import run_property
from engine.calc.timeline import build_month_index
from engine.models import (
    AreaMeasures,
    Inflation,
    Lease,
    Limits,
    MoneyRate,
    MoneyUnit,
    PropertyInfo,
    PropertyModel,
    PropertyRevenue,
    RentableAreaMode,
    RevenueUnit,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
MONTHS = build_month_index(BEGIN, 2)
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)])
GEN10 = Inflation(general_rate=[YearRate(year=1, rate=10.0)])
EXP10 = Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                  expense_rate=[YearRate(year=1, rate=10.0)])

PROP = "Parking / Storage / Miscellaneous Property Revenue"


def rev(amount, unit, name="Rev", **kwargs):
    return PropertyRevenue(name=name, amount=amount, unit=unit, **kwargs)


class TestUnits:
    """Amount/unit conversions mirror the expense units (spec §3.10)."""

    def test_dollars_per_year_and_month(self):
        assert project_property_revenue(
            rev(12_000, RevenueUnit.dollars_per_year), MONTHS, BEGIN, FLAT
        ).iloc[0] == pytest.approx(1_000)
        assert project_property_revenue(
            rev(1_000, RevenueUnit.dollars_per_month), MONTHS, BEGIN, FLAT
        ).iloc[0] == pytest.approx(1_000)

    def test_per_area_uses_property_area(self):
        series = project_property_revenue(
            rev(1.0, RevenueUnit.dollars_per_area_per_year),
            MONTHS, BEGIN, FLAT, area=120_000,
        )
        assert series.iloc[0] == pytest.approx(10_000)  # 1 × 120,000 / 12

    def test_spaces_times_rate(self):
        """number_of_spaces × annual rate per space (DEVIATIONS.md §13):
        50 spaces × $1,200/yr = $60,000/yr → $5,000/mo."""
        series = project_property_revenue(
            rev(1_200, RevenueUnit.spaces_times_rate, number_of_spaces=50),
            MONTHS, BEGIN, FLAT,
        )
        assert series.iloc[0] == pytest.approx(5_000)

    def test_per_occupied_area_scales_with_occupancy(self):
        occupied = pd.Series(50_000.0, index=MONTHS)  # 50% of 100,000
        series = project_property_revenue(
            rev(12.0, RevenueUnit.per_occupied_area),
            MONTHS, BEGIN, FLAT, occupied_area=occupied,
        )
        assert series.iloc[0] == pytest.approx(50_000)  # 12 × 50,000 / 12


class TestInflationTimingLimits:
    def test_default_index_is_general_not_expense(self):
        """Property revenue defaults to the general index. In a general-10%
        world it grows 10%/yr; in a general-0% / expense-10% world it stays
        flat (proving the default is general, not the expense index)."""
        on_general = project_property_revenue(
            rev(12_000, RevenueUnit.dollars_per_year), MONTHS, BEGIN, GEN10)
        assert on_general.iloc[0] == pytest.approx(1_000)
        assert on_general.iloc[12] == pytest.approx(1_100)  # general 10%

        default_in_expense_world = project_property_revenue(
            rev(12_000, RevenueUnit.dollars_per_year), MONTHS, BEGIN, EXP10)
        assert default_in_expense_world.iloc[12] == pytest.approx(1_000)  # general 0%
        # ...but an explicit expense index does follow the 10% expense rate
        on_expense = project_property_revenue(
            rev(12_000, RevenueUnit.dollars_per_year, inflation="expense"),
            MONTHS, BEGIN, EXP10)
        assert on_expense.iloc[12] == pytest.approx(1_100)

    def test_limits_clamp(self):
        series = project_property_revenue(
            rev(12_000, RevenueUnit.dollars_per_year, limits=Limits(max=800.0)),
            MONTHS, BEGIN, FLAT)
        assert list(series) == pytest.approx([800.0] * len(series))

    def test_pct_reference_required_then_applied(self):
        item = rev(5.0, RevenueUnit.pct_of_egr)
        with pytest.raises(ValueError, match="reference"):
            project_property_revenue(item, MONTHS, BEGIN, FLAT)
        reference = pd.Series(100_000.0, index=MONTHS)
        series = project_property_revenue(item, MONTHS, BEGIN, FLAT,
                                          reference=reference)
        assert series.iloc[0] == pytest.approx(5_000)  # 5% of 100,000


# --------------------------------------------------------------------- #
# run_property integration                                              #
# --------------------------------------------------------------------- #

def make_model(**kwargs):
    fields = dict(
        property=PropertyInfo(name="T", property_type="industrial",
                              analysis_begin=BEGIN, analysis_term_years=2),
        area_measures=AreaMeasures(property_size=100_000,
                                   rentable_area_mode=RentableAreaMode.fixed,
                                   rentable_area_fixed=100_000),
        inflation=FLAT,
        expenses=[],
        rent_roll=[Lease(
            tenant_name="Tenant", area=100_000, lease_type="industrial",
            start_date=BEGIN, term_months=120,
            base_rent=MoneyRate(amount=12.0,
                                unit=MoneyUnit.dollars_per_area_per_year),
            upon_expiration="vacate")],
    )
    fields.update(kwargs)
    return PropertyModel(**fields)


class TestRunIntegration:
    """The §4.1 step-9 pass through run_property (the guard is lifted)."""

    def test_absolute_revenue_posts_to_pgr_and_egr(self):
        """Base rent $100,000/mo + $1,000/mo parking → the property-revenue
        line posts $1,000 and lifts Total PGR and EGR by the same."""
        model = make_model(parking_revenues=[
            rev(12_000, RevenueUnit.dollars_per_year, inflation="general")])
        month = run_property(model).ledger.frame.iloc[0]
        assert month[PROP] == pytest.approx(1_000)
        assert month["Total Potential Gross Revenue"] == pytest.approx(101_000)
        assert month["Effective Gross Revenue"] == pytest.approx(101_000)

    def test_three_collections_sum_on_one_line(self):
        """Parking + storage + misc all post to the single property-revenue
        ledger line (spec §2.3). Names are distinct across the three lists
        — a cross-list name collision is now rejected at intake (the
        Codex-review uniqueness fix, DEVIATIONS.md §23)."""
        model = make_model(
            parking_revenues=[rev(12_000, RevenueUnit.dollars_per_year,
                                  name="Parking")],
            storage_revenues=[rev(6_000, RevenueUnit.dollars_per_year,
                                  name="Storage")],
            miscellaneous_revenues=[rev(1_200, RevenueUnit.dollars_per_month,
                                        name="Misc")],
        )
        month = run_property(model).ledger.frame.iloc[0]
        assert month[PROP] == pytest.approx(1_000 + 500 + 1_200)

    def test_pct_of_egr_revenue_resolves_self_consistently(self):
        """A %-of-EGR misc revenue re-enters EGR through PGR, so it resolves
        in the management-fee fixed point (DEVIATIONS.md §13): rev = 5% of
        *final* EGR. With base rent $100,000/mo and no other lines,
        EGR = 100,000 + rev and rev = 0.05 × EGR → rev = 5,263.16,
        EGR = 105,263.16."""
        model = make_model(miscellaneous_revenues=[
            rev(5.0, RevenueUnit.pct_of_egr)])
        month = run_property(model).ledger.frame.iloc[0]
        expected = 0.05 * 100_000 / 0.95
        assert month[PROP] == pytest.approx(expected)
        assert month["Effective Gross Revenue"] == pytest.approx(100_000 + expected)
        assert month[PROP] == pytest.approx(
            0.05 * month["Effective Gross Revenue"])

    def test_pct_of_account_deferred(self):
        """pct_of_account property revenue is refused (deferred,
        DEVIATIONS.md §13)."""
        model = make_model(miscellaneous_revenues=[
            PropertyRevenue(name="Linked", amount=10.0,
                            unit=RevenueUnit.pct_of_account,
                            account_ref="Base Rental Revenue")])
        with pytest.raises(NotImplementedError, match="pct_of_account"):
            run_property(model)


class TestRevenueNameUniqueness:
    """Codex-review correction (DEVIATIONS.md §23): property-revenue names
    must be unique ACROSS miscellaneous/parking/storage combined, because
    the %-of-revenue fixed point keys its series by name. A collision
    silently discarded revenue."""

    def test_same_list_duplicate_rejected(self):
        with pytest.raises(ValueError, match="property revenues"):
            make_model(parking_revenues=[
                rev(12_000, RevenueUnit.dollars_per_year, name="Fee"),
                rev(6_000, RevenueUnit.dollars_per_year, name="Fee")])

    def test_cross_list_duplicate_rejected(self):
        """The exact collision the review flagged: one 'Fee' in
        miscellaneous, one in parking — a per-list check would miss it."""
        with pytest.raises(ValueError, match="property revenues"):
            make_model(
                miscellaneous_revenues=[
                    rev(10.0, RevenueUnit.pct_of_pgr, name="Fee")],
                parking_revenues=[
                    rev(10.0, RevenueUnit.pct_of_pgr, name="Fee")])

    def test_two_distinct_pct_revenues_both_participate(self):
        """The $125.00 case: two 10%-of-PGR revenues with distinct names
        both enter the fixed point → PGR = 100,000 + 20% × PGR = 125,000
        (each posts 12,500). A name collision would have collapsed them to
        one, solving to 111,111.11 — a silent understatement."""
        model = make_model(
            miscellaneous_revenues=[
                rev(10.0, RevenueUnit.pct_of_pgr, name="Fee A")],
            parking_revenues=[
                rev(10.0, RevenueUnit.pct_of_pgr, name="Fee B")])
        month = run_property(model).ledger.frame.iloc[0]
        pgr = month["Total Potential Gross Revenue"]
        assert pgr == pytest.approx(125_000.0)
        assert month[PROP] == pytest.approx(25_000.0)  # both fees, 12,500 each
