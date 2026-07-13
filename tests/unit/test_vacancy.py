"""Unit tests for general vacancy & credit loss (Phase 2, Step 4;
engine/calc/vacancy.py).

Reproduces the manual's calculation examples with page cites (Iron
Rule 3): the three percentage-method examples [AE p. 225], the
reduce-by-A&T table (allowance shows zero when A&T exceeds it; unchecked
keeps separate lines) [AE p. 226], and credit loss after general vacancy
[AE p. 229; spec §3.5]. The Gate 2 criterion-5 test proves total vacancy
equals the stated rate of full-occupancy revenue — not rate + downtime —
through a live rollover (NEXT_STEPS_TO_GATE2.md criterion 5).
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.run import run_property
from engine.calc.timeline import build_month_index
from engine.calc.vacancy import (
    TenantRevenue,
    credit_loss_series,
    general_vacancy_series,
)
from engine.models import (
    AreaMeasures,
    CreditLoss,
    GeneralVacancy,
    Inflation,
    Lease,
    MarketLeasingProfile,
    MoneyRate,
    MoneyUnit,
    PctOfNew,
    PropertyInfo,
    PropertyModel,
    RentableAreaMode,
    TenantOverride,
    TimingBasis,
    UponExpiration,
    VacancyMethod,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
MONTHS = build_month_index(BEGIN, 2)
BASIS = TimingBasis.analysis_year


def series(value):
    return pd.Series(float(value), index=MONTHS)


def tenant(scheduled, cpi=0.0, recoveries=0.0, at=0.0):
    return TenantRevenue(
        scheduled=series(scheduled), cpi=series(cpi),
        recoveries=series(recoveries), absorption_vacancy=series(at),
    )


def gv_spec(method, rate, **kwargs):
    return GeneralVacancy(method=method,
                          rate=[YearRate(year=1, rate=rate)], **kwargs)


def run_gv(spec, tenants, property_revenue=None):
    return general_vacancy_series(spec, tenants, MONTHS, BEGIN, BASIS,
                                  property_revenue=property_revenue)


class TestMethodBases:
    """The manual's percentage-method examples [AE pp. 224-225]."""

    def test_pct_of_total_rental_revenue(self):
        """"Total Rental Revenue = $1,200,000; Rate = 5%; General Vacancy
        Amount = $60,000" [AE p. 225] — scheduled base + CPI."""
        tenants = {"T": tenant(scheduled=90_000, cpi=10_000,
                               recoveries=25_000)}  # rec excluded from base
        gv = run_gv(gv_spec(VacancyMethod.percent_of_scheduled_base_plus, 5.0),
                    tenants)
        assert gv.iloc[0] == pytest.approx(-5_000)          # 100,000 × 5%
        assert gv.iloc[:12].sum() == pytest.approx(-60_000)  # the example

    def test_pct_of_potential_gross_revenue(self):
        """"Potential Gross Revenue = $1,000,000; Rate = 5%; General
        Vacancy Amount = $50,000" [AE p. 225] — tenant revenue + other
        property income."""
        tenants = {"T": tenant(scheduled=60_000, recoveries=15_000)}
        gv = run_gv(gv_spec(VacancyMethod.percent_of_pgr, 5.0), tenants,
                    property_revenue=series(1_000_000 / 12 - 75_000))
        assert gv.iloc[:12].sum() == pytest.approx(-50_000)

    def test_pct_of_total_tenant_revenue(self):
        """"Total Tenant Revenue = $900,000; Rate = 5%; General Vacancy
        Amount = $45,000" [AE p. 225] — rental revenue + recoveries,
        excluding property income."""
        tenants = {"T": tenant(scheduled=60_000, recoveries=15_000)}
        gv = run_gv(gv_spec(VacancyMethod.percent_of_total_tenant_revenue, 5.0),
                    tenants, property_revenue=series(999_999))  # must be ignored
        assert gv.iloc[:12].sum() == pytest.approx(-45_000)

    def test_include_accounts_selects_lines(self):
        """include_in_pgr_accounts restricts the base to named revenue
        lines (spec §3.4)."""
        tenants = {"T": tenant(scheduled=100_000, recoveries=20_000)}
        spec = gv_spec(VacancyMethod.percent_of_pgr, 10.0,
                       include_in_pgr_accounts=["Expense Recovery Revenue"])
        assert run_gv(spec, tenants).iloc[0] == pytest.approx(-2_000)

    def test_unknown_include_account_raises(self):
        spec = gv_spec(VacancyMethod.percent_of_pgr, 10.0,
                       include_in_pgr_accounts=["Not A Line"])
        with pytest.raises(ValueError, match="Not A Line"):
            run_gv(spec, {"T": tenant(100_000)})


class TestReduceByAbsorptionTurnover:
    """The reduce toggle [AE pp. 225-226; spec §3.4's critical core]."""

    def test_allowance_zero_when_at_exceeds_it(self):
        """Checked (default): "Vacancy Allowance as 0 (zero) if absorption
        and turnover vacancy is greater than vacancy allowance"
        [AE p. 226]; the base is revenue at 100% occupancy [AE p. 226
        note]."""
        tenants = {"T": tenant(scheduled=70_000, at=-30_000)}
        gv = run_gv(gv_spec(VacancyMethod.percent_of_scheduled_base_plus, 5.0),
                    tenants)
        # target = 5% × (70,000 + 30,000) = 5,000 < 30,000 A&T → zero
        assert gv.iloc[0] == 0.0

    def test_allowance_tops_up_to_the_target(self):
        """When the target exceeds A&T, general vacancy posts only the
        difference (spec §3.4: max(0, target − A&T))."""
        tenants = {"T": tenant(scheduled=70_000, at=-30_000)}
        gv = run_gv(gv_spec(VacancyMethod.percent_of_scheduled_base_plus, 40.0),
                    tenants)
        # target = 40% × 100,000 = 40,000; minus 30,000 A&T → 10,000
        assert gv.iloc[0] == pytest.approx(-10_000)

    def test_unchecked_keeps_separate_lines(self):
        """Unchecked: A&T "not deducted from vacancy allowance" — separate
        line items [AE p. 226], computed on as-scheduled revenue."""
        tenants = {"T": tenant(scheduled=70_000, at=-30_000)}
        spec = gv_spec(VacancyMethod.percent_of_scheduled_base_plus, 5.0,
                       reduce_by_absorption_turnover=False)
        assert run_gv(spec, tenants).iloc[0] == pytest.approx(-3_500)


class TestOverridesAndRates:
    def test_excluded_tenant_leaves_base_and_offset(self):
        """Exclusion removes the tenant's revenue — and its A&T — from the
        calculation (spec §3.4 credit-tenant case; the manual's
        adjust/increment/replace override methods are narrowed to
        exclusion, DEVIATIONS.md §9 [AE pp. 226-227])."""
        tenants = {
            "Credit": tenant(scheduled=500_000, at=-50_000),
            "Other": tenant(scheduled=100_000),
        }
        spec = gv_spec(VacancyMethod.percent_of_scheduled_base_plus, 10.0,
                       tenant_overrides=[TenantOverride(tenant_ref="Credit")])
        # base = Other only (100,000); no A&T offset from Credit
        assert run_gv(spec, tenants).iloc[0] == pytest.approx(-10_000)

    def test_year_varying_rates(self):
        """Rates vary by year (spec §3.4; [AE p. 224 "rates that vary over
        time"]) on the analysis-year basis here."""
        spec = GeneralVacancy(
            method=VacancyMethod.percent_of_scheduled_base_plus,
            rate=[YearRate(year=1, rate=5.0), YearRate(year=2, rate=10.0)],
        )
        gv = run_gv(spec, {"T": tenant(100_000)})
        assert gv.iloc[0] == pytest.approx(-5_000)
        assert gv.iloc[12] == pytest.approx(-10_000)


class TestCreditLoss:
    """Credit loss (spec §3.5 [AE p. 229]): after general vacancy, on the
    reduced base, no A&T interaction."""

    def test_applies_after_general_vacancy_on_reduced_base(self):
        tenants = {"T": tenant(scheduled=100_000)}
        gv = series(-5_000).rename("general_vacancy")
        cl = credit_loss_series(
            CreditLoss(method=VacancyMethod.percent_of_scheduled_base_plus,
                       rate=[YearRate(year=1, rate=2.0)]),
            tenants, gv, MONTHS, BEGIN, BASIS,
        )
        assert cl.iloc[0] == pytest.approx(-0.02 * 95_000)

    def test_no_absorption_turnover_interaction(self):
        """A&T neither grosses the credit-loss base up nor reduces the
        result (spec §3.5)."""
        tenants = {"T": tenant(scheduled=70_000, at=-30_000)}
        cl = credit_loss_series(
            CreditLoss(method=VacancyMethod.percent_of_scheduled_base_plus,
                       rate=[YearRate(year=1, rate=2.0)]),
            tenants, series(0.0), MONTHS, BEGIN, BASIS,
        )
        assert cl.iloc[0] == pytest.approx(-0.02 * 70_000)  # net, ungrossed


class TestGate2Criterion5:
    """Gate 2 criterion 5 (NEXT_STEPS_TO_GATE2.md): total vacancy % of
    full-occupancy revenue equals the stated rate — turnover downtime does
    not stack on top of general vacancy (spec §3.4)."""

    def make_model(self):
        anchor = Lease(
            tenant_name="Anchor", area=500_000, lease_type="industrial",
            start_date=BEGIN, term_months=120,
            base_rent=MoneyRate(amount=12.0,
                                unit=MoneyUnit.dollars_per_area_per_year),
            upon_expiration=UponExpiration.vacate,
        )
        roller = Lease(
            tenant_name="Roller", area=100_000, lease_type="industrial",
            start_date=BEGIN, term_months=12,
            base_rent=MoneyRate(amount=12.0,
                                unit=MoneyUnit.dollars_per_area_per_year),
            market_leasing_profile="Market",
            upon_expiration=UponExpiration.market,
        )
        profile = MarketLeasingProfile(
            name="Market", term_months=24, renewal_probability=50.0,
            months_vacant=4.0,  # downtime = 2 months
            market_base_rent_new=MoneyRate(
                amount=12.0, unit=MoneyUnit.dollars_per_area_per_year),
            market_base_rent_renew=PctOfNew(pct_of_new=100.0),
            free_rent_months_new=0.0, free_rent_months_renew=0.0,
            upon_expiration=UponExpiration.market, term_growth=False,
        )
        return PropertyModel(
            property=PropertyInfo(name="C5", property_type="industrial",
                                  analysis_begin=BEGIN, analysis_term_years=2),
            area_measures=AreaMeasures(
                property_size=600_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=600_000,
            ),
            inflation=Inflation(general_rate=[YearRate(year=1, rate=0.0)]),
            market_leasing_profiles=[profile],
            rent_roll=[anchor, roller],
            general_vacancy=GeneralVacancy(
                method=VacancyMethod.percent_of_scheduled_base_plus,
                rate=[YearRate(year=1, rate=20.0)],
            ),
        )

    def test_total_vacancy_equals_stated_rate_not_rate_plus_downtime(self):
        frame = run_property(self.make_model()).ledger.frame
        full_occupancy_rent = 600_000.0  # both spaces at $12/SF/yr monthly

        downtime = pd.Period("2027-01", freq="M")  # Roller vacant Jan-Feb
        at = frame.loc[downtime, "Absorption & Turnover Vacancy"]
        gv = frame.loc[downtime, "General Vacancy"]
        assert at == pytest.approx(-100_000)
        assert gv == pytest.approx(-20_000)  # tops up to target, no stack
        total = -(at + gv)
        assert total == pytest.approx(0.20 * full_occupancy_rent)

        occupied = pd.Period("2026-06", freq="M")
        assert frame.loc[occupied, "Absorption & Turnover Vacancy"] == 0.0
        assert frame.loc[occupied, "General Vacancy"] == pytest.approx(
            -0.20 * full_occupancy_rent
        )
        # the property-level identity: total vacancy is the stated 20% in
        # downtime and fully-occupied months alike


class TestExternalIdOverrideResolution:
    """Codex-review correction (DEVIATIONS.md §23): a vacancy/credit-loss
    TenantOverride may reference a tenant by external_id (intake accepts
    it); the calc layer must resolve it to the tenant_name the tenants
    dict is keyed by, or the exclusion silently no-ops. Exercised through
    run_property (where the resolver map is built)."""

    def model(self, *, general_vacancy=None, credit_loss=None):
        credit = Lease(
            tenant_name="Credit Tenant", external_id="EXT-CREDIT",
            area=500_000, lease_type="industrial", start_date=BEGIN,
            term_months=120,
            base_rent=MoneyRate(amount=12.0,
                                unit=MoneyUnit.dollars_per_area_per_year),
            upon_expiration=UponExpiration.vacate)
        other = Lease(
            tenant_name="Other", area=100_000, lease_type="industrial",
            start_date=BEGIN, term_months=120,
            base_rent=MoneyRate(amount=12.0,
                                unit=MoneyUnit.dollars_per_area_per_year),
            upon_expiration=UponExpiration.vacate)
        kwargs = {}
        if general_vacancy is not None:
            kwargs["general_vacancy"] = general_vacancy
        if credit_loss is not None:
            kwargs["credit_loss"] = credit_loss
        return PropertyModel(
            property=PropertyInfo(name="Ext", property_type="industrial",
                                  analysis_begin=BEGIN, analysis_term_years=2),
            area_measures=AreaMeasures(
                property_size=600_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=600_000),
            inflation=Inflation(general_rate=[YearRate(year=1, rate=0.0)]),
            rent_roll=[credit, other], **kwargs)

    def test_general_vacancy_override_by_external_id_excludes(self):
        """Base = Credit 500,000 + Other 100,000 = 600,000/mo; a 10% GV
        excluding the credit tenant BY EXTERNAL_ID must fall to 10% of
        Other only (100,000) = 10,000, not stay at 60,000."""
        gv = GeneralVacancy(
            method=VacancyMethod.percent_of_scheduled_base_plus,
            rate=[YearRate(year=1, rate=10.0)],
            tenant_overrides=[TenantOverride(tenant_ref="EXT-CREDIT")])
        frame = run_property(self.model(general_vacancy=gv)).ledger.frame
        assert frame["General Vacancy"].iloc[0] == pytest.approx(-10_000.0)

    def test_general_vacancy_override_by_name_also_excludes(self):
        """The tenant_name form still works (both must resolve to the same
        identity)."""
        gv = GeneralVacancy(
            method=VacancyMethod.percent_of_scheduled_base_plus,
            rate=[YearRate(year=1, rate=10.0)],
            tenant_overrides=[TenantOverride(tenant_ref="Credit Tenant")])
        frame = run_property(self.model(general_vacancy=gv)).ledger.frame
        assert frame["General Vacancy"].iloc[0] == pytest.approx(-10_000.0)

    def test_credit_loss_override_by_external_id_excludes(self):
        """Credit loss consumes the same _base_and_at: excluding the credit
        tenant by external_id drops the CL base to Other only → 2% of
        100,000 = 2,000 (no general vacancy configured)."""
        cl = CreditLoss(
            method=VacancyMethod.percent_of_scheduled_base_plus,
            rate=[YearRate(year=1, rate=2.0)],
            tenant_overrides=[TenantOverride(tenant_ref="EXT-CREDIT")])
        frame = run_property(self.model(credit_loss=cl)).ledger.frame
        assert frame["Credit Loss"].iloc[0] == pytest.approx(-2_000.0)

    def test_without_override_credit_tenant_is_in_the_base(self):
        """Control: no override → the full 600,000 base → 10% = 60,000."""
        gv = GeneralVacancy(
            method=VacancyMethod.percent_of_scheduled_base_plus,
            rate=[YearRate(year=1, rate=10.0)])
        frame = run_property(self.model(general_vacancy=gv)).ledger.frame
        assert frame["General Vacancy"].iloc[0] == pytest.approx(-60_000.0)
