"""Unit tests for TI/LC posting (Phase 3 Step 1; engine/calc/capital.py).

Cites per Iron Rule 3: "All tenant improvements are paid at the beginning
of the lease" [AE p. 246]; "All leasing commissions are paid at the
beginning of the lease. Leasing commission percentages are applied to base
rent plus fixed steps less free rent", with "Fixed %" defined as a
percentage "of the total rent, including steps, less free rent over the
5 year lease term" [AE p. 247]. Rollover amounts are §4.2
probability-weighted and inflate to segment start on the market index;
absorption leases inflate to their own start ("changes to market
assumptions ... are dynamically incorporated" [AE p. 395]).
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.capital import project_lease_capital, segment_capital
from engine.calc.leases import resolve_lease_chain
from engine.calc.ledger import (
    CFBDS,
    LEASING_COMMISSIONS,
    NOI,
    TENANT_IMPROVEMENTS,
    TOTAL_CAPITAL_COSTS,
)
from engine.calc.run import run_property
from engine.calc.timeline import build_month_index
from engine.models import (
    AbsorptionSpec,
    AreaMeasures,
    ExpenseItem,
    ExpenseUnit,
    Inflation,
    LCSpec,
    Lease,
    LeasingCosts,
    MarketLeasingProfile,
    MoneyRate,
    MoneyUnit,
    PctOfNew,
    PropertyInfo,
    PropertyModel,
    RentStep,
    RentableAreaMode,
    TimingBasis,
    UponExpiration,
    YearRate,
)
from engine.models.profiles import TICategory

BEGIN = dt.date(2026, 1, 1)
PSF_YR = MoneyUnit.dollars_per_area_per_year
PSF = MoneyUnit.dollars_per_area

FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                 timing_basis=TimingBasis.analysis_year)
# 3% every calendar year from 2027; the market factor at 2028-01 is
# exactly 1.03**2 = 1.0609 (two January bumps).
THREE_PCT = Inflation(
    general_rate=[YearRate(year=2027, rate=3.0)],
    market_rent_rate=[YearRate(year=2027, rate=3.0)],
    inflation_month=1,
    timing_basis=TimingBasis.calendar_year,
)


def build_model(leases, *, profiles=(), absorption=(), expenses=(),
                inflation=FLAT, size=12_000, years=5, ti_categories=()):
    return PropertyModel(
        property=PropertyInfo(name="Cap", property_type="industrial",
                              analysis_begin=BEGIN,
                              analysis_term_years=years),
        area_measures=AreaMeasures(
            property_size=size,
            rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=size,
        ),
        inflation=inflation,
        market_leasing_profiles=list(profiles),
        ti_categories=list(ti_categories),
        expenses=list(expenses),
        rent_roll=list(leases),
        absorption=list(absorption),
    )


class TestContractPosting:
    """Contract-term TI/LC from ``Lease.leasing_costs`` post as one lump
    sum at lease start [AE pp. 246-247]."""

    def test_ti_per_area_lump_sum_at_lease_start(self):
        """$ / SF TI unit [AE p. 245]: $5/SF x 12,000 SF, paid in the
        month the lease begins [AE p. 246]."""
        lease = Lease(
            tenant_name="T", area=12_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
            leasing_costs=LeasingCosts(ti=MoneyRate(amount=5.0, unit=PSF)),
            upon_expiration=UponExpiration.vacate,
        )
        result = run_property(build_model([lease]))
        ti = result.ledger.frame[TENANT_IMPROVEMENTS]
        assert ti[pd.Period("2026-01", freq="M")] == pytest.approx(-60_000.0)
        assert ti.drop(pd.Period("2026-01", freq="M")).abs().sum() == 0.0
        assert result.tenant_improvements["T"].sum() == pytest.approx(60_000.0)

    def test_ti_dollar_amount(self):
        """$ Amount TI unit [AE p. 245]: a flat $75,000."""
        lease = Lease(
            tenant_name="T", area=12_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
            leasing_costs=LeasingCosts(
                ti=MoneyRate(amount=75_000.0, unit=MoneyUnit.dollars)),
            upon_expiration=UponExpiration.vacate,
        )
        result = run_property(build_model([lease]))
        ti = result.ledger.frame[TENANT_IMPROVEMENTS]
        assert ti[pd.Period("2026-01", freq="M")] == pytest.approx(-75_000.0)

    def test_lc_fixed_pct_of_term_value_with_steps_less_free_rent(self):
        """The [AE p. 247] Fixed % example shape: 4% of the total rent,
        including steps, less free rent, over the 5-year term. $10/SF/yr
        stepping $1/SF each year on 12,000 SF = 720,000 total, less 3 free
        months (30,000) -> 690,000; 4% = 27,600, paid at lease start."""
        lease = Lease(
            tenant_name="T", area=12_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
            rent_steps=[RentStep(month_offset=12 * n, amount=10.0 + n,
                                 unit=PSF_YR) for n in (1, 2, 3, 4)],
            free_rent={"months": 3.0},
            leasing_costs=LeasingCosts(lc=LCSpec(pct=4.0)),
            upon_expiration=UponExpiration.vacate,
        )
        result = run_property(build_model([lease]))
        lc = result.ledger.frame[LEASING_COMMISSIONS]
        assert lc[pd.Period("2026-01", freq="M")] == pytest.approx(-27_600.0)
        assert lc.drop(pd.Period("2026-01", freq="M")).abs().sum() == 0.0

    def test_lc_pct_years_restricts_lease_years(self):
        """``pct_years`` (spec §3.9) limits the % base to the listed lease
        years: 4% of year-1 rent less year-1 free rent = 4% x 90,000."""
        lease = Lease(
            tenant_name="T", area=12_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
            rent_steps=[RentStep(month_offset=12, amount=11.0, unit=PSF_YR)],
            free_rent={"months": 3.0},
            leasing_costs=LeasingCosts(lc=LCSpec(pct=4.0, pct_years=[1])),
            upon_expiration=UponExpiration.vacate,
        )
        result = run_property(build_model([lease]))
        lc = result.ledger.frame[LEASING_COMMISSIONS]
        assert lc[pd.Period("2026-01", freq="M")] == pytest.approx(-3_600.0)

    def test_lc_dollar_forms(self):
        """$ / SF and $ Amount LC units [AE p. 247]."""
        per_sf = Lease(
            tenant_name="A", area=12_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
            leasing_costs=LeasingCosts(
                lc=LCSpec(rate=MoneyRate(amount=2.0, unit=PSF))),
            upon_expiration=UponExpiration.vacate,
        )
        flat = Lease(
            tenant_name="B", area=12_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
            leasing_costs=LeasingCosts(
                lc=LCSpec(rate=MoneyRate(amount=9_000.0,
                                         unit=MoneyUnit.dollars))),
            upon_expiration=UponExpiration.vacate,
        )
        result = run_property(build_model([per_sf, flat], size=24_000))
        assert result.leasing_commissions["A"].sum() == pytest.approx(24_000.0)
        assert result.leasing_commissions["B"].sum() == pytest.approx(9_000.0)

    def test_pre_analysis_lease_start_posts_nothing(self):
        """Costs are paid at the beginning of the lease [AE pp. 246-247];
        a lease that began before the analysis window paid them then."""
        lease = Lease(
            tenant_name="T", area=12_000, lease_type="industrial",
            start_date=dt.date(2024, 1, 1), term_months=120,
            base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
            leasing_costs=LeasingCosts(
                ti=MoneyRate(amount=5.0, unit=PSF), lc=LCSpec(pct=4.0)),
            upon_expiration=UponExpiration.vacate,
        )
        result = run_property(build_model([lease]))
        assert result.ledger.frame[TENANT_IMPROVEMENTS].abs().sum() == 0.0
        assert result.ledger.frame[LEASING_COMMISSIONS].abs().sum() == 0.0

    def test_non_lump_ti_unit_refused(self):
        """No silent numbers: a $/SF/yr TI is not a one-time cost unit."""
        lease = Lease(
            tenant_name="T", area=12_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
            leasing_costs=LeasingCosts(ti=MoneyRate(amount=5.0, unit=PSF_YR)),
            upon_expiration=UponExpiration.vacate,
        )
        with pytest.raises(ValueError, match="one-time cost unit"):
            run_property(build_model([lease]))


def rollover_profile(**overrides):
    """p = 75%, no downtime: contract expires 2027-12, the speculative
    segment starts 2028-01 (market factor 1.0609 under THREE_PCT)."""
    fields = dict(
        name="Market", term_months=60, renewal_probability=75.0,
        months_vacant=0.0,
        market_base_rent_new=MoneyRate(amount=12.0, unit=PSF_YR),
        market_base_rent_renew=PctOfNew(pct_of_new=100.0),
        ti_new=MoneyRate(amount=2.0, unit=PSF),
        ti_renew=MoneyRate(amount=0.5, unit=PSF),
        lc_new=LCSpec(pct=6.0), lc_renew=LCSpec(pct=4.0),
        upon_expiration=UponExpiration.market, term_growth=True,
    )
    fields.update(overrides)
    return MarketLeasingProfile(**fields)


def roller(**overrides):
    fields = dict(
        tenant_name="Roller", area=10_000, lease_type="industrial",
        start_date=BEGIN, term_months=24,
        base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
        market_leasing_profile="Market",
        upon_expiration=UponExpiration.market,
    )
    fields.update(overrides)
    return Lease(**fields)


class TestRolloverPosting:
    """Speculative-segment TI/LC: §4.2 probability-weighted [AE p. 245],
    inflated to segment start on the market index (golden #1's published
    rollover TI is the external evidence for the factor)."""

    def test_blended_ti_inflates_to_segment_start(self):
        """0.75 x $0.50 + 0.25 x $2.00 = $0.875/SF; x 10,000 SF x 1.0609
        at the 2028-01 segment start = 9,282.875."""
        model = build_model([roller()], profiles=[rollover_profile()],
                            inflation=THREE_PCT, size=10_000)
        result = run_property(model)
        ti = result.ledger.frame[TENANT_IMPROVEMENTS]
        assert ti[pd.Period("2028-01", freq="M")] == pytest.approx(
            -0.875 * 10_000 * 1.0609)

    def test_blended_lc_rate_inflates_like_ti(self):
        """$-form LC blends the same way: 0.75 x $1 + 0.25 x $4 =
        $1.75/SF x 10,000 x 1.0609 [AE p. 247 '$ / SF']."""
        profile = rollover_profile(
            lc_new=LCSpec(rate=MoneyRate(amount=4.0, unit=PSF)),
            lc_renew=LCSpec(rate=MoneyRate(amount=1.0, unit=PSF)),
        )
        model = build_model([roller()], profiles=[profile],
                            inflation=THREE_PCT, size=10_000)
        result = run_property(model)
        lc = result.ledger.frame[LEASING_COMMISSIONS]
        assert lc[pd.Period("2028-01", freq="M")] == pytest.approx(
            -1.75 * 10_000 * 1.0609)

    def test_blended_lc_pct_of_blended_term_value_less_weighted_free(self):
        """Weighted 4.5% (0.75 x 4 + 0.25 x 6) of the blended term value
        less the weighted free month [AE p. 247]: rent $12/SF on 10,000 SF
        = 10,000/mo x 60 months = 600,000, less 1.0 weighted free month
        (0.25 x 4 new) -> 590,000; 4.5% = 26,550."""
        profile = rollover_profile(free_rent_months_new=4.0,
                                   free_rent_months_renew=0.0)
        model = build_model([roller()], profiles=[profile],
                            inflation=FLAT, size=10_000)
        result = run_property(model)
        lc = result.ledger.frame[LEASING_COMMISSIONS]
        assert lc[pd.Period("2028-01", freq="M")] == pytest.approx(
            -0.045 * (60 * 10_000 - 1.0 * 10_000))

    def test_lc_pct_base_uses_full_term_beyond_timeline(self):
        """The Fixed % base is the entire lease value over the term
        [AE p. 247], even where the speculative term runs past the
        analysis end: with a 3-year analysis the 2028-01 segment posts the
        same 26,550 as under the 5-year analysis above."""
        profile = rollover_profile(free_rent_months_new=4.0,
                                   free_rent_months_renew=0.0)
        model = build_model([roller()], profiles=[profile],
                            inflation=FLAT, size=10_000, years=3)
        result = run_property(model)
        lc = result.ledger.frame[LEASING_COMMISSIONS]
        assert lc[pd.Period("2028-01", freq="M")] == pytest.approx(-26_550.0)


class TestAbsorption:
    """Absorption leases carry MLP new-tenant TI/LC inflated to each
    lease's own start [AE p. 395], posted at that start month."""

    def test_ti_posts_at_each_lease_start_with_its_own_factor(self):
        spec = AbsorptionSpec(
            name="Bay", total_area=20_000, number_of_leases=2,
            start_date=dt.date(2027, 1, 1), interval_months=12,
            lease_type="industrial", market_leasing_profile="Market",
        )
        model = build_model([], profiles=[rollover_profile()],
                            absorption=[spec], inflation=THREE_PCT,
                            size=20_000)
        result = run_property(model)
        ti = result.ledger.frame[TENANT_IMPROVEMENTS]
        assert ti[pd.Period("2027-01", freq="M")] == pytest.approx(
            -2.0 * 10_000 * 1.03)
        assert ti[pd.Period("2028-01", freq="M")] == pytest.approx(
            -2.0 * 10_000 * 1.0609)


class TestLedgerWiring:
    """Capital-section rollups [AE pp. 535-539]: Total Capital Costs =
    TI + LC + capital expense lines; CFBDS = NOI + Total Capital Costs
    (report signs — the Cedar Alt CSV's exact identity)."""

    def test_total_capital_costs_and_cfbds_identities(self):
        lease = Lease(
            tenant_name="T", area=12_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
            leasing_costs=LeasingCosts(
                ti=MoneyRate(amount=5.0, unit=PSF), lc=LCSpec(pct=4.0)),
            upon_expiration=UponExpiration.vacate,
        )
        reserves = ExpenseItem(name="Capital Reserves", amount=0.10,
                               unit=ExpenseUnit.dollars_per_area_per_year,
                               category="capital")
        result = run_property(build_model([lease], expenses=[reserves]))
        frame = result.ledger.frame
        total = (frame[TENANT_IMPROVEMENTS] + frame[LEASING_COMMISSIONS]
                 + frame["Capital Reserves"])
        assert (frame[TOTAL_CAPITAL_COSTS] - total).abs().max() < 1e-9
        cfbds = frame[NOI] + frame[TOTAL_CAPITAL_COSTS]
        assert (frame[CFBDS] - cfbds).abs().max() < 1e-9
        assert frame["Capital Reserves"].iloc[0] == pytest.approx(-100.0)

    def test_category_refs_refused_loudly(self):
        """TICategory/LCCategory are schema-present with no calc consumer
        (DEVIATIONS.md §16) — refused, never silently dropped."""
        lease = Lease(
            tenant_name="T", area=12_000, lease_type="industrial",
            start_date=BEGIN, term_months=60,
            base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
            leasing_costs=LeasingCosts(ti_category="Standard TI"),
            upon_expiration=UponExpiration.vacate,
        )
        model = build_model([lease], ti_categories=[TICategory(
            name="Standard TI",
            new=MoneyRate(amount=5.0, unit=PSF),
            renew=MoneyRate(amount=1.0, unit=PSF),
        )])
        with pytest.raises(NotImplementedError, match="TI/LC categories"):
            run_property(model)

    def test_mlp_lc_category_ref_refused_at_resolution(self):
        profile = rollover_profile(
            lc_new=LCSpec(category_ref="LCX"), lc_renew=None)
        months = build_month_index(BEGIN, 5)
        with pytest.raises(NotImplementedError, match="LC categories"):
            resolve_lease_chain(roller(), months, BEGIN, FLAT,
                                {"Market": profile})

    def test_blend_with_differing_pct_years_refused(self):
        profile = rollover_profile(
            lc_new=LCSpec(pct=6.0, pct_years=[1]), lc_renew=LCSpec(pct=4.0))
        months = build_month_index(BEGIN, 5)
        with pytest.raises(ValueError, match="different pct_years"):
            resolve_lease_chain(roller(), months, BEGIN, FLAT,
                                {"Market": profile})
