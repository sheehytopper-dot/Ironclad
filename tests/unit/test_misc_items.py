"""Unit tests for engine/calc/misc_items.py — tenant miscellaneous items
(spec §3.12; §4.1 pass 8) [AE pp. 378-381 contract; pp. 240-244 MLP].

Iron Rule 3: the manual's misc-item pages give input definitions rather
than numeric walkthroughs, so each test cites the definitional statement it
reproduces — the amount/$-per-tenant-area input methods with annual/monthly
frequency [AE p. 379; pp. 241-242], the selectable inflation index
[AE p. 380], and the monthly min/max limits [AE pp. 380-381].

**EXTERNALLY UNVALIDATED** (checked 2026-07-11): no golden fixture uses
miscellaneous_items — Clorox, Freeport, and Cedar Alt all carry none — so
this module ships on these manual-definition tests only, the same standing
as percentage rent pending golden #3.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.leases import resolve_lease_chain
from engine.calc.misc_items import project_segment_misc_items
from engine.calc.run import run_property
from engine.models import (
    AreaMeasures,
    FreeRent,
    FreeRentProfile,
    GeneralVacancy,
    Inflation,
    Lease,
    Limits,
    MarketLeasingProfile,
    MiscItemSpec,
    MoneyRate,
    MoneyUnit,
    PctOfNew,
    PropertyInfo,
    PropertyModel,
    RentableAreaMode,
    VacancyMethod,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
MONTHS_3Y = None  # built per-test via chains
PSF_YR = MoneyUnit.dollars_per_area_per_year
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)])
GEN10 = Inflation(general_rate=[YearRate(year=1, rate=10.0)])

from engine.calc.timeline import build_month_index

MONTHS = build_month_index(BEGIN, 2)


def item(amount, unit, **kwargs):
    return MiscItemSpec(name="Storage", amount=amount, unit=unit, **kwargs)


def contract_segment(items, area=10_000, term_months=24, **lease_kwargs):
    lease = Lease(
        tenant_name="Tenant", area=area, lease_type="industrial",
        start_date=BEGIN, term_months=term_months,
        base_rent=MoneyRate(amount=12.0, unit=PSF_YR),
        miscellaneous_items=items, upon_expiration="vacate", **lease_kwargs,
    )
    return resolve_lease_chain(lease, MONTHS, BEGIN, FLAT, {})[0]


class TestInputMethods:
    """The manual's Detail-grid input methods [AE p. 379; pp. 241-242]."""

    def test_amount_annually_posts_one_twelfth(self):
        """'Amount 1' at the default 'Annually' frequency [AE p. 379]:
        $12,000/yr posts $1,000 per occupied month."""
        segment = contract_segment([item(12_000, MoneyUnit.dollars_per_year)])
        series = project_segment_misc_items(
            segment, MONTHS, analysis_begin=BEGIN, inflation=FLAT)
        assert series.iloc[0] == pytest.approx(1_000)
        assert series.iloc[:12].sum() == pytest.approx(12_000)

    def test_amount_monthly(self):
        """'Amount 1' at 'Monthly' frequency [AE p. 379]."""
        segment = contract_segment([item(750, MoneyUnit.dollars_per_month)])
        series = project_segment_misc_items(
            segment, MONTHS, analysis_begin=BEGIN, inflation=FLAT)
        assert series.iloc[0] == pytest.approx(750)

    def test_amount_per_tenant_area(self):
        """'$/Tenant Area' [AE p. 379]: the rate multiplies the tenant's
        own area — $0.60/SF/yr × 10,000 SF / 12 = $500/mo."""
        segment = contract_segment([item(0.60, PSF_YR)])
        series = project_segment_misc_items(
            segment, MONTHS, analysis_begin=BEGIN, inflation=FLAT)
        assert series.iloc[0] == pytest.approx(500)

    def test_negative_amount_is_an_abatement(self):
        """A negative amount posts as a per-tenant abatement (spec §3.12
        schema docstring)."""
        segment = contract_segment([item(-6_000, MoneyUnit.dollars_per_year)])
        series = project_segment_misc_items(
            segment, MONTHS, analysis_begin=BEGIN, inflation=FLAT)
        assert series.iloc[0] == pytest.approx(-500)

    def test_percent_of_rent_units_rejected(self):
        """The manual's '% of Rent' input method (with Rent Components
        [AE p. 379]) is not modeled — pct units fail loudly rather than
        posting a silent number (DEVIATIONS.md §15)."""
        segment = contract_segment(
            [item(5.0, MoneyUnit.pct_of_market)])
        with pytest.raises(ValueError, match="not supported"):
            project_segment_misc_items(
                segment, MONTHS, analysis_begin=BEGIN, inflation=FLAT)


class TestInflationAndLimits:
    def test_inflates_on_selected_index_general_by_default(self):
        """Amounts inflate on a selectable index [AE p. 380]; the engine's
        default is the general rate (revenue-side convention)."""
        segment = contract_segment([item(12_000, MoneyUnit.dollars_per_year)])
        series = project_segment_misc_items(
            segment, MONTHS, analysis_begin=BEGIN, inflation=GEN10)
        assert series.iloc[0] == pytest.approx(1_000)
        assert series.iloc[12] == pytest.approx(1_100)  # year 2 at +10%

    def test_monthly_limits_clamp(self):
        """Limits set 'a lower or upper monthly limit on the projected
        miscellaneous rent amounts' [AE p. 380]."""
        capped = contract_segment([
            item(12_000, MoneyUnit.dollars_per_year, limits=Limits(max=800.0))
        ])
        series = project_segment_misc_items(
            capped, MONTHS, analysis_begin=BEGIN, inflation=FLAT)
        assert series.iloc[0] == pytest.approx(800)
        floored = contract_segment([
            item(3_000, MoneyUnit.dollars_per_year, limits=Limits(min=400.0))
        ])
        series = project_segment_misc_items(
            floored, MONTHS, analysis_begin=BEGIN, inflation=FLAT)
        assert series.iloc[0] == pytest.approx(400)  # 250 raised to the floor


class TestOccupiedMonthsAndRollover:
    """Per-segment projection over occupied months only — the Step 2
    convention recoveries and percentage rent follow; rollover terms carry
    the MLP's items [AE pp. 240-244]."""

    def make_model(self, lease_items, mlp_items, **kwargs):
        profile = MarketLeasingProfile(
            name="MLA", term_months=24, renewal_probability=50.0,
            months_vacant=6.0,  # weighted downtime 3 months
            market_base_rent_new=MoneyRate(amount=12.0, unit=PSF_YR),
            market_base_rent_renew=PctOfNew(pct_of_new=100.0),
            miscellaneous_items=mlp_items,
            upon_expiration="market", term_growth=False,
        )
        fields = dict(
            property=PropertyInfo(name="T", property_type="industrial",
                                  analysis_begin=BEGIN, analysis_term_years=3),
            area_measures=AreaMeasures(
                property_size=10_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=10_000),
            inflation=FLAT,
            market_leasing_profiles=[profile],
            rent_roll=[Lease(
                tenant_name="Tenant", area=10_000, lease_type="industrial",
                start_date=BEGIN, term_months=12,
                base_rent=MoneyRate(amount=12.0, unit=PSF_YR),
                miscellaneous_items=lease_items,
                market_leasing_profile="MLA", upon_expiration="market")],
        )
        fields.update(kwargs)
        return PropertyModel(**fields)

    def test_downtime_posts_nothing_speculative_uses_mlp_items(self):
        """Contract months post the lease's items; the 3 weighted downtime
        months (2027-01..03) post nothing; the speculative term posts the
        MLP's items [AE pp. 240-241 'The Miscellaneous Items section ...
        link[s] miscellaneous rent ... to tenants' on the Market Leasing
        profile]."""
        model = self.make_model(
            [item(12_000, MoneyUnit.dollars_per_year)],
            [MiscItemSpec(name="MLA Storage", amount=2_400,
                          unit=MoneyUnit.dollars_per_year)],
        )
        frame = run_property(model).ledger.frame
        line = frame["Miscellaneous Tenant Revenue"]
        assert line[pd.Period("2026-06", freq="M")] == pytest.approx(1_000)
        for m in ("2027-01", "2027-02", "2027-03"):  # downtime
            assert line[pd.Period(m, freq="M")] == pytest.approx(0.0)
        assert line[pd.Period("2027-06", freq="M")] == pytest.approx(200)

    def test_joins_pgr_egr_and_vacancy_base(self):
        """Misc tenant revenue joins Total PGR/EGR and the percent-of-PGR
        general-vacancy base, threaded like percentage rent (§4.1 pass 8)."""
        model = self.make_model(
            [item(12_000, MoneyUnit.dollars_per_year)], [],
            general_vacancy=GeneralVacancy(
                method=VacancyMethod.percent_of_pgr,
                rate=[YearRate(year=1, rate=5.0)],
                reduce_by_absorption_turnover=False,
            ),
        )
        month = run_property(model).ledger.frame.iloc[0]
        # base 10,000 + misc 1,000 = PGR 11,000; GV 5% of it
        assert month["Miscellaneous Tenant Revenue"] == pytest.approx(1_000)
        assert month["Total Potential Gross Revenue"] == pytest.approx(11_000)
        assert month["General Vacancy"] == pytest.approx(-550.0)
        assert month["Effective Gross Revenue"] == pytest.approx(10_450.0)

    def test_lease_audit_reconciles_with_misc(self):
        """Lease Audit gains the misc column and still reconciles exactly
        to the ledger (Gate 2 discipline, extended)."""
        from engine.reports.lease_audit import lease_audit, reconcile_to_ledger

        model = self.make_model(
            [item(12_000, MoneyUnit.dollars_per_year)],
            [MiscItemSpec(name="MLA Storage", amount=2_400,
                          unit=MoneyUnit.dollars_per_year)],
        )
        result = run_property(model)
        report = lease_audit(result)
        assert report["misc"].iloc[0] == pytest.approx(1_000)
        differences = reconcile_to_ledger(report, result)
        assert float(differences.abs().max().max()) < 1e-9


class TestFreeRentAbatement:
    """free_rent_abates suppresses an item during free-rent months only
    when the governing free-rent profile abates miscellaneous items
    ([AE pp. 253-254] free-rent elements; schema comment 'abated by free
    rent when the profile says so') — mirroring abate_recoveries."""

    def model(self, *, item_abates: bool, profile_abates: bool):
        return PropertyModel(
            property=PropertyInfo(name="T", property_type="industrial",
                                  analysis_begin=BEGIN, analysis_term_years=2),
            area_measures=AreaMeasures(
                property_size=10_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=10_000),
            inflation=FLAT,
            free_rent_profiles=[FreeRentProfile(
                name="FR", abate_base_rent=True,
                abate_recoveries=False,
                abate_miscellaneous=profile_abates)],
            rent_roll=[Lease(
                tenant_name="Tenant", area=10_000, lease_type="industrial",
                start_date=BEGIN, term_months=24,
                base_rent=MoneyRate(amount=12.0, unit=PSF_YR),
                free_rent=FreeRent(months=2, profile="FR"),
                miscellaneous_items=[item(
                    12_000, MoneyUnit.dollars_per_year,
                    free_rent_abates=item_abates)],
                upon_expiration="vacate")],
        )

    def test_suppressed_when_both_sides_opt_in(self):
        frame = run_property(
            self.model(item_abates=True, profile_abates=True)).ledger.frame
        line = frame["Miscellaneous Tenant Revenue"]
        assert line.iloc[0] == pytest.approx(0.0)      # free month 1
        assert line.iloc[1] == pytest.approx(0.0)      # free month 2
        assert line.iloc[2] == pytest.approx(1_000.0)  # rent resumes

    def test_item_opt_out_unaffected(self):
        frame = run_property(
            self.model(item_abates=False, profile_abates=True)).ledger.frame
        assert frame["Miscellaneous Tenant Revenue"].iloc[0] == pytest.approx(1_000)

    def test_profile_opt_out_unaffected(self):
        frame = run_property(
            self.model(item_abates=True, profile_abates=False)).ledger.frame
        assert frame["Miscellaneous Tenant Revenue"].iloc[0] == pytest.approx(1_000)
