"""Unit tests for space absorption (Phase 2, Step 3; engine/calc/absorption.py).

Cites per Iron Rule 3: absorption sub-divides vacant space into speculative
leases from a market leasing profile [AE p. 395]; every term comes from the
MLP — "base rent, fixed steps, ... free rent, ... recoveries, tenant
improvements, leasing commissions, and term length" [AE p. 396]; the lease
count derives from Area to Lease / Average Lease Area and starts space per
Months Between Leases [AE p. 397]; generated names follow the series
pattern "... 2 of 8" [AE p. 403]. Pre-absorption vacancy and reabsorb v1
semantics are DEVIATIONS.md §8.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.absorption import generate_absorption_leases
from engine.calc.run import run_property
from engine.calc.timeline import build_month_index
from engine.models import (
    AbsorptionSpec,
    AreaMeasures,
    ExpenseItem,
    ExpenseUnit,
    Inflation,
    Lease,
    LeaseStatus,
    MarketLeasingProfile,
    MoneyRate,
    MoneyUnit,
    PctOfNew,
    PropertyInfo,
    PropertyModel,
    RentableAreaMode,
    RentStep,
    TimingBasis,
    UponExpiration,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)])
THREE_PCT = Inflation(
    general_rate=[YearRate(year=2027, rate=3.0)],
    market_rent_rate=[YearRate(year=2027, rate=3.0)],
    inflation_month=1,
    timing_basis=TimingBasis.calendar_year,
)
PSF_YR = MoneyUnit.dollars_per_area_per_year


def make_profile(**overrides):
    fields = dict(
        name="Market", term_months=60, renewal_probability=60.0,
        months_vacant=6.0,
        market_base_rent_new=MoneyRate(amount=12.0, unit=PSF_YR),
        market_base_rent_renew=PctOfNew(pct_of_new=100.0),
        rent_increases=[RentStep(month_offset=12, pct_increase=3.0)],
        free_rent_months_new=2.0, free_rent_months_renew=0.0,
        ti_new=MoneyRate(amount=5.0, unit=MoneyUnit.dollars_per_area),
        lc_new=None,
        upon_expiration=UponExpiration.market, term_growth=True,
    )
    fields.update(overrides)
    return MarketLeasingProfile(**fields)


def make_spec(**overrides):
    fields = dict(
        name="Vacant Office", total_area=100_000, area_per_lease=30_000,
        start_date=dt.date(2026, 7, 1), interval_months=3,
        lease_type="office", market_leasing_profile="Market",
    )
    fields.update(overrides)
    return AbsorptionSpec(**fields)


def generate(spec=None, profile=None, inflation=FLAT):
    profile = profile or make_profile()
    return generate_absorption_leases(
        spec or make_spec(), {profile.name: profile}, BEGIN, inflation
    )


class TestGeneration:
    """Lease generation schedule and sizing [AE pp. 395-397, 403]."""

    def test_count_and_areas_from_average_lease_area(self):
        """# of Leases derives from Area to Lease / Average Lease Area
        [AE p. 397]; the final lease takes the remainder so areas sum to
        the total (derived rentable stays whole, spec §3.2)."""
        leases = generate()
        assert [l.area for l in leases] == [30_000, 30_000, 30_000, 10_000]
        assert sum(l.area for l in leases) == 100_000

    def test_count_from_number_of_leases_splits_evenly(self):
        spec = make_spec(area_per_lease=None, number_of_leases=4)
        leases = generate(spec)
        assert [l.area for l in leases] == [25_000] * 4

    def test_series_names_and_schedule(self):
        """Names follow the manual's "N of M" series [AE p. 403]; starts
        space per Months Between Leases [AE p. 397]."""
        leases = generate()
        assert leases[0].tenant_name == "Vacant Office 1 of 4"
        assert leases[3].tenant_name == "Vacant Office 4 of 4"
        assert [l.start_date for l in leases] == [
            dt.date(2026, 7, 1), dt.date(2026, 10, 1),
            dt.date(2027, 1, 1), dt.date(2027, 4, 1),
        ]

    def test_new_tenant_economics_from_profile(self):
        """Every term comes from the MLP at new-tenant economics
        [AE p. 396]: 100% new rent, new free rent, new TI, the profile's
        steps, term, and recovery assignment — no renewal blending."""
        leases = generate()
        first = leases[0]
        assert first.status == LeaseStatus.speculative
        assert first.term_months == 60
        assert first.base_rent.unit == MoneyUnit.dollars_per_month
        assert first.base_rent.amount == pytest.approx(12.0 * 30_000 / 12)
        assert first.free_rent.months == 2.0
        assert first.leasing_costs.ti.amount == 5.0
        assert len(first.rent_steps) == 1
        assert first.recoveries.method.value == "net"
        assert first.upon_expiration == UponExpiration.market
        assert first.market_leasing_profile == "Market"

    def test_market_rent_inflates_to_each_lease_start(self):
        """Market assumptions are "dynamically incorporated" [AE p. 395]:
        a lease starting after the January 2027 step carries the inflated
        rent; one starting before does not."""
        leases = generate(inflation=THREE_PCT)
        assert leases[0].base_rent.amount == pytest.approx(30_000)   # 2026-07
        assert leases[2].base_rent.amount == pytest.approx(30_900)   # 2027-01
        assert leases[3].base_rent.amount == pytest.approx(30_900 / 3)  # 10k SF

    def test_pct_of_last_rent_rejected_for_vacant_space(self):
        profile = make_profile(
            market_base_rent_new=MoneyRate(amount=90.0,
                                           unit=MoneyUnit.pct_of_last_rent),
        )
        with pytest.raises(ValueError, match="no prior rent"):
            generate(profile=profile)


class TestRunIntegration:
    """Absorption through run_property: occupancy, revenue timing,
    recoveries, and the reabsorb guard (DEVIATIONS.md §8)."""

    def make_model(self, **overrides):
        fields = dict(
            property=PropertyInfo(name="Dev", property_type="office",
                                  analysis_begin=BEGIN, analysis_term_years=3),
            area_measures=AreaMeasures(property_size=100_000),  # derived mode
            inflation=FLAT,
            market_leasing_profiles=[make_profile()],
            expenses=[ExpenseItem(name="CAM", amount=120_000,
                                  unit=ExpenseUnit.dollars_per_year)],
            absorption=[make_spec()],
        )
        fields.update(overrides)
        return PropertyModel(**fields)

    def test_pre_absorption_vacancy_grosses_pgr_to_market(self):
        """Pre-absorption vacant space carries its market value in Base
        Rental Revenue with the offsetting Absorption & Turnover Vacancy
        entry [AE p. 538] — Scheduled nets to zero, nothing recovers, and
        the space counts in rentable/available area (DEVIATIONS.md §8,
        corrected 2026-07-06)."""
        result = run_property(self.make_model())
        frame = result.ledger.frame
        june = pd.Period("2026-06", freq="M")  # before first lease (Jul)
        market_value = 12.0 * 100_000 / 12  # all four spaces vacant
        assert frame.loc[june, "Base Rental Revenue"] == pytest.approx(market_value)
        assert frame.loc[june, "Absorption & Turnover Vacancy"] == pytest.approx(
            -market_value
        )
        assert frame.loc[june, "Scheduled Base Rental Revenue"] == pytest.approx(0.0)
        assert frame.loc[june, "Expense Recovery Revenue"] == 0.0
        # the gross-up nets to zero inside Scheduled: EGR and NOI are what
        # the ungrossed convention would produce (DEVIATIONS.md §8) —
        # only Potential Base Rent, A&T, and the vacancy base move
        assert frame.loc[june, "Effective Gross Revenue"] == pytest.approx(0.0)
        assert frame.loc[june, "Net Operating Income"] == pytest.approx(
            -10_000  # the month's CAM, unrecovered
        )
        assert result.rentable_area[june] == 100_000  # derived incl. absorption
        assert result.occupied_area[june] == 0.0

    def test_lease_up_ramps_occupancy_and_revenue(self):
        result = run_property(self.make_model())
        frame = result.ledger.frame
        assert result.occupied_area[pd.Period("2026-07", freq="M")] == 30_000
        assert result.occupied_area[pd.Period("2026-10", freq="M")] == 60_000
        assert result.occupied_area[pd.Period("2027-04", freq="M")] == 100_000
        # month 1 of lease 1: its rent posts (free rent offsets it) while
        # the 70k SF not yet absorbed stays at market in Base + A&T
        # [AE p. 538]; recoveries at the tenant's 30% pro-rata share of
        # the pool [AE p. 405]
        july = pd.Period("2026-07", freq="M")
        assert frame.loc[july, "Base Rental Revenue"] == pytest.approx(
            30_000 + 70_000
        )
        assert frame.loc[july, "Absorption & Turnover Vacancy"] == pytest.approx(
            -70_000
        )
        assert frame.loc[july, "Free Rent"] == pytest.approx(-30_000)
        # Scheduled = Base + A&T + Free: month fully abated by free rent
        assert frame.loc[july, "Scheduled Base Rental Revenue"] == pytest.approx(0.0)
        assert frame.loc[july, "Expense Recovery Revenue"] == pytest.approx(
            10_000 * 0.30
        )

    def test_variable_expense_scales_with_absorption_occupancy(self):
        """pct_fixed scaling uses the absorption-driven occupancy series
        (spec §3.11): a fully variable expense follows the lease-up ramp."""
        model = self.make_model(
            expenses=[ExpenseItem(name="Utilities", amount=120_000,
                                  unit=ExpenseUnit.dollars_per_year,
                                  pct_fixed=0.0)],
        )
        frame = run_property(model).ledger.frame
        assert frame.loc[pd.Period("2026-06", freq="M"), "Utilities"] == 0.0
        assert frame.loc[pd.Period("2026-07", freq="M"), "Utilities"] == pytest.approx(
            -10_000 * 0.30
        )
        assert frame.loc[pd.Period("2027-05", freq="M"), "Utilities"] == pytest.approx(
            -10_000
        )

    def test_generated_leases_chain_like_rent_roll(self):
        """Each generated lease behaves like a rent roll lease thereafter
        (spec §3.15): its chain rolls over per the profile (a 24-month
        term so the first rollover lands inside the timeline)."""
        result = run_property(self.make_model(
            market_leasing_profiles=[make_profile(term_months=24)]
        ))
        chain = result.segments["Vacant Office 1 of 4"]
        assert len(chain) >= 2
        assert chain[1].speculative
        assert chain[1].renewal_weight == pytest.approx(0.60)

    def test_reabsorb_is_guarded(self):
        profile = make_profile(upon_expiration=UponExpiration.reabsorb)
        with pytest.raises(NotImplementedError, match="reabsorb"):
            run_property(self.make_model(market_leasing_profiles=[profile]))

    def test_invariants_hold_through_lease_up(self):
        # run_property asserts §9.3 invariants internally; reaching here
        # with a ramping property is the check
        result = run_property(self.make_model())
        assert (result.occupied_area <= result.rentable_area + 1e-9).all()
