"""Unit tests for the Phase 4 Step 4 tenant/occupancy reports:
Occupancy (#15) — engine/reports/occupancy.py — and Lease Summary (#11) +
Lease Expiration (#12) — engine/reports/lease_reports.py.

These are views over the run's occupancy series and resolved chains, so
the acceptance (NEXT_STEPS_TO_PHASE4 Step 4) is: Occupancy satisfies
occupied ≤ rentable and reconciles to the run's series; Lease Expiration
SF sums to rentable (no phantom leases) and each report reconciles to its
RunResult source. Engineered properties only (occupancy/lease reports have
no golden CSV anchor).
"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from engine.calc.run import run_property
from engine.reports import (
    Period,
    Report,
    assert_occupied_within_rentable,
    lease_expiration,
    lease_summary,
    occupancy,
    reconcile_expiration_area,
    reconcile_lease_summary,
    reconcile_occupancy,
)
from engine.models import (
    AreaMeasures,
    ExpenseItem,
    ExpenseUnit,
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
PSF_YR = MoneyUnit.dollars_per_area_per_year
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                 timing_basis=TimingBasis.analysis_year)
RENTABLE = 300_000.0


@pytest.fixture(scope="module")
def result():
    """Clean two-tenant property (fixed rentable = the two contract areas,
    no absorption/reabsorption), so expiring SF sums exactly to rentable.
    Anchor: 200k SF, 120-mo term → expires FY2035. Roller: 100k SF, 36-mo
    term, vacates → expires FY2028, leaving the building 2/3 occupied."""
    profile = MarketLeasingProfile(
        name="M", term_months=24, renewal_probability=50.0, months_vacant=4.0,
        market_base_rent_new=MoneyRate(amount=12.0, unit=PSF_YR),
        market_base_rent_renew=PctOfNew(pct_of_new=100.0),
        free_rent_months_new=2.0, free_rent_months_renew=0.0,
        upon_expiration=UponExpiration.market, term_growth=False)
    anchor = Lease(tenant_name="Anchor", area=200_000, lease_type="industrial",
                   start_date=BEGIN, term_months=120,
                   base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
                   upon_expiration=UponExpiration.vacate, suite="100")
    roller = Lease(tenant_name="Roller", area=100_000, lease_type="industrial",
                   start_date=BEGIN, term_months=36,
                   base_rent=MoneyRate(amount=12.0, unit=PSF_YR),
                   market_leasing_profile="M",
                   upon_expiration=UponExpiration.vacate, suite="200")
    model = PropertyModel(
        property=PropertyInfo(name="MT", property_type="industrial",
                              analysis_begin=BEGIN, analysis_term_years=5),
        area_measures=AreaMeasures(
            property_size=RENTABLE, rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=RENTABLE),
        inflation=FLAT, market_leasing_profiles=[profile],
        expenses=[ExpenseItem(name="CAM", amount=300_000.0,
                              unit=ExpenseUnit.dollars_per_year)],
        rent_roll=[anchor, roller])
    return run_property(model)


class TestOccupancy:
    def test_monthly_reconciles_to_run_series(self, result):
        report = occupancy(result, period=Period.monthly)
        assert isinstance(report, Report) and report.meta.number == 15
        assert report.meta.monetary is False
        diff = reconcile_occupancy(report, result)
        assert diff.abs().to_numpy().max() == pytest.approx(0.0, abs=1e-12)

    @pytest.mark.parametrize("period", list(Period))
    def test_occupied_within_rentable_every_period(self, result, period):
        report = occupancy(result, period=period)
        assert_occupied_within_rentable(report)  # never raises
        assert (report.frame["available_area"] >= -1e-6).all()

    def test_columns(self, result):
        report = occupancy(result, period=Period.annual)
        assert list(report.frame.columns) == [
            "occupied_area", "rentable_area", "available_area", "occupancy"]

    def test_annual_mean_occupancy(self, result):
        """Year 4 (Roller gone): 200k of 300k occupied → 2/3."""
        frame = occupancy(result, period=Period.annual).frame
        assert frame.loc[4, "occupancy"] == pytest.approx(2.0 / 3.0, abs=1e-9)
        assert frame.loc[1, "occupancy"] == pytest.approx(1.0, abs=1e-9)
        assert frame.loc[4, "available_area"] == pytest.approx(100_000.0)

    def test_period_occupancy_is_mean_over_months(self, result):
        """Annual occupied area = mean of the 12 monthly occupied areas."""
        annual = occupancy(result, period=Period.annual).frame
        monthly = result.occupied_area
        assert annual.loc[1, "occupied_area"] == pytest.approx(
            monthly.iloc[:12].mean())

    def test_non_monthly_reconcile_raises(self, result):
        report = occupancy(result, period=Period.annual)
        with pytest.raises(ValueError, match="monthly"):
            reconcile_occupancy(report, result)


class TestLeaseSummary:
    def test_one_row_per_tenant_reconciles(self, result):
        report = lease_summary(result)
        assert report.meta.number == 11 and report.meta.monetary is False
        assert set(report.frame["tenant"]) == {"Anchor", "Roller"}
        recon = reconcile_lease_summary(report, result)
        assert recon["area_diff"].abs().max() == pytest.approx(0.0, abs=1e-9)
        assert recon["start_matches"].all() and recon["end_matches"].all()

    def test_rent_columns(self, result):
        frame = lease_summary(result).frame
        row = frame.set_index("tenant").loc["Anchor"]
        # $10/SF/yr on 200k SF → 2,000,000/yr, 166,666.67/mo, $10/SF/yr
        assert row["annual_base_rent"] == pytest.approx(2_000_000.0)
        assert row["monthly_base_rent"] == pytest.approx(2_000_000.0 / 12)
        assert row["base_rent_psf_yr"] == pytest.approx(10.0)
        assert row["area"] == pytest.approx(200_000.0)
        assert row["suite"] == "100"
        assert row["term_months"] == 120

    def test_total_area_metadata(self, result):
        report = lease_summary(result)
        assert report.meta.extra["total_area"] == pytest.approx(RENTABLE)


class TestLeaseExpiration:
    def test_sf_sums_to_rentable(self, result):
        """No phantom leases → every space expires once → expiring SF sums
        to the rentable area (the plan's acceptance)."""
        report = lease_expiration(result)
        assert report.meta.number == 12 and report.meta.monetary is False
        assert report.frame["expiring_sf"].sum() == pytest.approx(RENTABLE)
        assert reconcile_expiration_area(report, result) == pytest.approx(
            0.0, abs=1e-9)

    def test_by_year_count_sf_pct_rent(self, result):
        frame = lease_expiration(result).frame.set_index("fiscal_year")
        # Roller (100k, 36-mo from 2026-01 → 2028-12) expires FY2028
        assert frame.loc[2028, "expiring_leases"] == 1
        assert frame.loc[2028, "expiring_sf"] == pytest.approx(100_000.0)
        assert frame.loc[2028, "pct_of_building"] == pytest.approx(1.0 / 3.0)
        # Anchor (200k, 120-mo) expires FY2035
        assert frame.loc[2035, "expiring_sf"] == pytest.approx(200_000.0)
        assert frame.loc[2035, "pct_of_building"] == pytest.approx(2.0 / 3.0)
        # expiring rent: Anchor $10/SF/yr × 200k = 2,000,000
        assert frame.loc[2035, "expiring_annual_rent"] == pytest.approx(
            2_000_000.0)

    def test_fiscal_year_end_shifts_buckets(self, result):
        """A June fiscal-year-end moves a December expiration into the next
        fiscal year label (fiscal year named for the year it ends)."""
        june = lease_expiration(result, fiscal_year_end_month=6).frame
        # Roller expires 2028-12 → with FYE June that is fiscal 2029
        assert 2029 in set(june["fiscal_year"])
        assert 2028 not in set(june["fiscal_year"])

    def test_pct_of_building_uses_rentable(self, result):
        report = lease_expiration(result)
        assert report.meta.extra["rentable_area"] == pytest.approx(RENTABLE)
        # every pct = sf / rentable
        for row in report.frame.itertuples():
            assert row.pct_of_building == pytest.approx(
                row.expiring_sf / RENTABLE)


class TestPhantomLeaseCase:
    """When absorption/reabsorption re-leases existing space, expiring SF
    exceeds rentable — the report still reconciles to the contract-area
    source exactly (each chain counted once), documenting the difference."""

    def test_reconcile_holds_even_when_sf_exceeds_rentable(self):
        from pathlib import Path
        from engine.models.io import load_property
        fixture = (Path(__file__).resolve().parents[1] / "golden" /
                   "freeport" / "freeport.icprop.json")
        res = run_property(load_property(fixture))
        report = lease_expiration(res, fiscal_year_end_month=6)
        # reconciles to the summed contract area regardless of phantoms
        assert reconcile_expiration_area(report, res) == pytest.approx(
            0.0, abs=1e-6)
        # and here that total genuinely exceeds rentable (phantom re-leasing)
        assert report.frame["expiring_sf"].sum() > float(
            res.rentable_area.iloc[0])
