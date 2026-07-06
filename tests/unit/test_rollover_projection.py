"""Unit tests for speculative-segment projection (Phase 2, Step 2):
engine/calc/leases.py project_segment_rent, ledger.py
occupied_area_from_chains, recoveries.py project_segment_recoveries, and
run.py integration.

Cites per Iron Rule 3: downtime posts as Absorption & Turnover Vacancy —
"loss in rent due to downtime between leases" [AE p. 538] — at the rent
the space would have earned, offsetting the full-occupancy Base Rental
Revenue (spec §4.2/§2.3); free rent "is applied at the beginning of the
lease" [AE p. 239] with the profile's elements [AE p. 254]; net
recoveries are the tenant's pro-rata share [AE p. 405] over occupied
months. Downtime occupancy weighting (occupied drops by (1−p) × area) is
spec §4.2's ARGUS-default treatment.
"""
import datetime as dt

import pandas as pd
import pytest

from engine.calc.leases import (
    project_segment_rent,
    resolve_lease_chain,
)
from engine.calc.ledger import occupied_area_from_chains
from engine.calc.recoveries import project_segment_recoveries
from engine.calc.timeline import build_month_index
from engine.models import (
    AreaMeasures,
    ExpenseItem,
    ExpenseUnit,
    FreeRentProfile,
    Inflation,
    Lease,
    MarketLeasingProfile,
    MoneyRate,
    MoneyUnit,
    PctOfNew,
    PropertyInfo,
    PropertyModel,
    RentableAreaMode,
    TimingBasis,
    UponExpiration,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
MONTHS = build_month_index(BEGIN, 4)  # through 2030-12
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                 timing_basis=TimingBasis.analysis_year)

PSF_YR = MoneyUnit.dollars_per_area_per_year


def make_profile(**overrides):
    fields = dict(
        name="Market", term_months=24, renewal_probability=50.0,
        months_vacant=6.0,  # downtime = round(0.5 × 6) = 3
        market_base_rent_new=MoneyRate(amount=12.0, unit=PSF_YR),
        market_base_rent_renew=PctOfNew(pct_of_new=100.0),
        free_rent_months_new=3.0, free_rent_months_renew=0.0,
        upon_expiration=UponExpiration.market, term_growth=False,
    )
    fields.update(overrides)
    return MarketLeasingProfile(**fields)


def make_lease(**overrides):
    fields = dict(
        tenant_name="Tenant", area=100_000, lease_type="industrial",
        start_date=BEGIN, term_months=12,  # expires 2026-12
        base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
        market_leasing_profile="Market",
        upon_expiration=UponExpiration.market,
    )
    fields.update(overrides)
    return Lease(**fields)


def first_spec(profile=None, lease=None):
    profile = profile or make_profile()
    lease = lease or make_lease()
    chain = resolve_lease_chain(lease, MONTHS, BEGIN, FLAT,
                                {profile.name: profile})
    return chain[1]


class TestSegmentRentProjection:
    """Downtime and free-rent posting (spec §4.2/§2.3 [AE pp. 538, 239])."""

    # blended rent: 12 $/SF/yr × 100,000 / 12 = 100,000/mo (flat inflation)

    def test_downtime_posts_base_and_negative_vacancy(self):
        """Downtime months post the blended market rent to Base Rental
        Revenue AND its negative to Absorption & Turnover Vacancy, so
        Scheduled nets to zero while PGR stays full-occupancy
        (spec §4.2/§2.3; [AE p. 538])."""
        seg = first_spec()
        flows = project_segment_rent(seg, MONTHS)
        assert seg.downtime_months == 3  # 2027-01 .. 2027-03
        for month in ("2027-01", "2027-02", "2027-03"):
            period = pd.Period(month, freq="M")
            assert flows.base_rent[period] == pytest.approx(100_000)
            assert flows.absorption_vacancy[period] == pytest.approx(-100_000)
        occupied_first = pd.Period("2027-04", freq="M")
        assert flows.base_rent[occupied_first] == pytest.approx(100_000)
        assert flows.absorption_vacancy[occupied_first] == 0.0

    def test_weighted_free_rent_fractional_final_month(self):
        """Weighted free rent (0.5 × 3 = 1.5 months) abates the front of
        the term with a fractional final month [AE p. 239; spec §4.2]."""
        seg = first_spec()
        flows = project_segment_rent(seg, MONTHS)
        assert seg.free_rent_months == pytest.approx(1.5)
        month1 = pd.Period("2027-04", freq="M")
        assert flows.free_rent[month1] == pytest.approx(-100_000)
        assert flows.free_rent[month1 + 1] == pytest.approx(-50_000)
        assert flows.free_rent[month1 + 2] == 0.0
        # never abated during downtime
        assert flows.free_rent[pd.Period("2027-01", freq="M")] == 0.0

    def test_free_rent_profile_can_exclude_base_rent(self):
        """The profile's elements govern what abates [AE p. 254]: a profile
        with abate_base_rent = false posts no Free Rent for the segment."""
        seg = first_spec()
        profile = FreeRentProfile(name="Nothing", abate_base_rent=False)
        flows = project_segment_rent(seg, MONTHS, free_rent_profile=profile)
        assert flows.free_rent.abs().sum() == 0.0

    def test_contract_segment_rejected(self):
        chain = resolve_lease_chain(make_lease(), MONTHS, BEGIN, FLAT,
                                    {"Market": make_profile()})
        with pytest.raises(ValueError, match="speculative"):
            project_segment_rent(chain[0], MONTHS)


class TestOccupancyFromChains:
    """Occupied area drops by (1 − p) × area during downtime (spec §4.2)."""

    def test_downtime_partial_occupancy(self):
        profile = make_profile()
        chain = resolve_lease_chain(make_lease(), MONTHS, BEGIN, FLAT,
                                    {profile.name: profile})
        occupied = occupied_area_from_chains([chain], MONTHS)
        assert occupied[pd.Period("2026-06", freq="M")] == 100_000  # contract
        for month in ("2027-01", "2027-02", "2027-03"):  # downtime, p = 0.5
            assert occupied[pd.Period(month, freq="M")] == pytest.approx(50_000)
        assert occupied[pd.Period("2027-04", freq="M")] == 100_000  # spec term

    def test_vacated_space_is_empty(self):
        lease = make_lease(upon_expiration=UponExpiration.vacate,
                           market_leasing_profile=None)
        chain = resolve_lease_chain(lease, MONTHS, BEGIN, FLAT, {})
        occupied = occupied_area_from_chains([chain], MONTHS)
        assert occupied[pd.Period("2026-12", freq="M")] == 100_000
        assert occupied[pd.Period("2027-01", freq="M")] == 0.0


class TestSegmentRecoveries:
    """Speculative net recoveries: pro-rata share [AE p. 405] over occupied
    months only — downtime posts nothing (golden #1 FY2029 confirms)."""

    def test_net_share_over_occupied_months_only(self):
        seg = first_spec()
        cam = ExpenseItem(name="CAM", amount=240_000,
                          unit=ExpenseUnit.dollars_per_year)
        series = pd.Series(20_000.0, index=MONTHS)
        recovery = project_segment_recoveries(
            seg, MONTHS, [(cam, series)], rentable_area=400_000
        )
        assert recovery[pd.Period("2027-03", freq="M")] == 0.0  # downtime
        assert recovery[pd.Period("2027-04", freq="M")] == pytest.approx(
            20_000 * 100_000 / 400_000
        )
        assert recovery[pd.Period("2026-06", freq="M")] == 0.0  # contract window

    def test_user_structures_need_a_context(self):
        """A structure-method segment resolves through a RecoveryContext
        (run.py supplies one); without it the call fails loudly."""
        profile = make_profile(recoveries={"method": "structure",
                                           "structure_ref": "Custom"})
        seg = first_spec(profile=profile)
        cam = ExpenseItem(name="CAM", amount=240_000,
                          unit=ExpenseUnit.dollars_per_year)
        with pytest.raises(ValueError, match="RecoveryContext"):
            project_segment_recoveries(
                seg, MONTHS, [(cam, pd.Series(20_000.0, index=MONTHS))],
                rentable_area=400_000,
            )


class TestRunIntegration:
    """run_property with rollover: ledger identities and guards."""

    def make_model(self, **overrides):
        fields = dict(
            property=PropertyInfo(name="Mini", property_type="industrial",
                                  analysis_begin=BEGIN, analysis_term_years=4),
            area_measures=AreaMeasures(
                property_size=100_000,
                rentable_area_mode=RentableAreaMode.fixed,
                rentable_area_fixed=100_000,
            ),
            inflation=FLAT,
            market_leasing_profiles=[make_profile()],
            expenses=[ExpenseItem(name="CAM", amount=120_000,
                                  unit=ExpenseUnit.dollars_per_year)],
            rent_roll=[make_lease()],
        )
        fields.update(overrides)
        return PropertyModel(**fields)

    def test_rollover_flows_into_ledger(self):
        from engine.calc.run import run_property

        result = run_property(self.make_model())
        frame = result.ledger.frame
        downtime = pd.Period("2027-02", freq="M")
        assert frame.loc[downtime, "Base Rental Revenue"] == pytest.approx(100_000)
        assert frame.loc[downtime, "Absorption & Turnover Vacancy"] == pytest.approx(-100_000)
        assert frame.loc[downtime, "Scheduled Base Rental Revenue"] == pytest.approx(0.0)
        assert frame.loc[downtime, "Expense Recovery Revenue"] == pytest.approx(0.0)
        assert result.occupancy[downtime] == pytest.approx(0.5)
        occupied = pd.Period("2027-07", freq="M")  # past free rent
        assert frame.loc[occupied, "Scheduled Base Rental Revenue"] == pytest.approx(100_000)
        assert frame.loc[occupied, "Expense Recovery Revenue"] == pytest.approx(10_000)

    def test_mlp_percentage_rent_guarded(self):
        from engine.calc.run import run_property

        profile = make_profile(percentage_rent={
            "sales_volume": {"amount": 400.0,
                             "unit": "dollars_per_area_per_year"},
            "breakpoint_layers": [{"pct": 6.0}],
        })
        with pytest.raises(NotImplementedError, match="percentage rent"):
            run_property(self.make_model(market_leasing_profiles=[profile]))
