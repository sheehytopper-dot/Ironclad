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
    CONTRACTUAL_STATUSES,
    Period,
    Report,
    assert_expiration_within_building,
    assert_occupied_within_rentable,
    lease_expiration,
    lease_summary,
    occupancy,
    reconcile_lease_expiration,
    reconcile_lease_summary,
    reconcile_occupancy,
)
from engine.models import (
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
    TimingBasis,
    UponExpiration,
    YearRate,
)

BEGIN = dt.date(2026, 1, 1)
PSF_YR = MoneyUnit.dollars_per_area_per_year
FLAT = Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                 timing_basis=TimingBasis.analysis_year)
RENTABLE = 300_000.0


def clean_model():
    """Clean two-tenant property (fixed rentable = the two contract areas,
    no absorption/reabsorption, both leases status=contract). Anchor: 200k
    SF, 120-mo term → expires FY2035. Roller: 100k SF, 36-mo term, vacates →
    expires FY2028, leaving the building 2/3 occupied. Because there are no
    phantom leases here, the contract expiring SF happens to equal rentable
    — but that is NOT asserted as an invariant (DEVIATIONS.md §25)."""
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
    return PropertyModel(
        property=PropertyInfo(name="MT", property_type="industrial",
                              analysis_begin=BEGIN, analysis_term_years=5),
        area_measures=AreaMeasures(
            property_size=RENTABLE, rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=RENTABLE),
        inflation=FLAT, market_leasing_profiles=[profile],
        expenses=[ExpenseItem(name="CAM", amount=300_000.0,
                              unit=ExpenseUnit.dollars_per_year)],
        rent_roll=[anchor, roller])


@pytest.fixture(scope="module")
def model():
    return clean_model()


@pytest.fixture(scope="module")
def result(model):
    return run_property(model)


@pytest.fixture(scope="module")
def freeport():
    """The real OM fixture: 28 contract chains (incl. the suite-100 OKI
    double-entry), 1 MTM, 1 speculative absorption chain. Returns
    ``(model, result)``."""
    from pathlib import Path
    from engine.models.io import load_property
    fixture = (Path(__file__).resolve().parents[1] / "golden" /
               "freeport" / "freeport.icprop.json")
    model = load_property(fixture)
    return model, run_property(model)


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

    def test_distinct_demised_area_metadata(self, result):
        """meta carries a DISTINCT demised area (deduped by suite), never a
        double-counted total masquerading as the building (DEVIATIONS §25).
        Here the two suites are distinct so it equals their sum."""
        report = lease_summary(result)
        assert "total_area" not in report.meta.extra  # the wrong field is gone
        assert report.meta.extra["distinct_demised_area"] == pytest.approx(
            300_000.0)
        # default now includes all tenancy (real + projected); this clean
        # fixture has only contract chains, so both rows are Contractual
        assert report.meta.extra["included_statuses"] == [
            "contract", "mtm", "speculative"]
        assert set(report.frame["status"]) == {"Contractual"}
        assert list(report.frame["lease_status"]) == ["contract", "contract"]


class TestLeaseExpiration:
    def test_structural_reconcile_against_model_input(self, model, result):
        """The report reconciles to the MODEL INPUT (a source the builder
        never reads) — count, total SF, and per-year count/SF all zero
        (DEVIATIONS §25). This CAN fail; it is not a self-subtraction."""
        report = lease_expiration(result)
        assert report.meta.number == 12 and report.meta.monetary is False
        diffs = reconcile_lease_expiration(report, model)
        assert diffs.abs().max() == pytest.approx(0.0, abs=1e-9)

    def test_reconcile_is_failable(self, model, result):
        """DEVIATIONS §25: the model-input reconcile CAN fail — corrupt a
        written expiring-SF cell and it flags a nonzero diff (not a
        self-subtraction)."""
        report = lease_expiration(result)
        report.frame.loc[0, "expiring_sf"] += 1000.0
        assert reconcile_lease_expiration(report, model).abs().max() > 0.0

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
        for row in report.frame.itertuples():
            assert row.pct_of_building == pytest.approx(
                row.expiring_sf / RENTABLE)

    @pytest.mark.parametrize("fye", [3, 6, 9, 12])
    def test_per_year_sanity_bound_across_conventions(self, result, fye):
        """The per-year SANITY BOUND (not an invariant) holds on this clean
        property for every fiscal-year-end convention (DEVIATIONS §25)."""
        report = lease_expiration(result, fiscal_year_end_month=fye)
        assert_expiration_within_building(report, result)  # never raises


class TestStatusFilterAndTurnover:
    """The [AE p. 818] lease-status inclusion filter, and the legitimacy of
    >100% cumulative expiring SF (DEVIATIONS §25). Freeport has 28 contract
    chains (incl. the suite-100 OKI double-entry), 1 MTM, and 1 speculative
    absorption chain (the module-level ``freeport`` fixture)."""

    def test_default_includes_all_tenancy_with_provenance_label(self, freeport):
        """Default now includes the full picture (owner directive): 28
        contract + 1 MTM + 1 speculative absorption chain = 30, each row
        labeled Contractual / Speculative, reconciling to the model input."""
        model, res = freeport
        rep = lease_expiration(res)
        assert rep.meta.extra["included_statuses"] == [
            "contract", "mtm", "speculative"]
        assert int(rep.frame["expiring_leases"].sum()) == 30
        assert set(rep.frame["status"]) == {"Contractual", "Speculative"}
        # the absorption chain is the lone Speculative expiration
        spec = rep.frame[rep.frame["status"] == "Speculative"]
        assert int(spec["expiring_leases"].sum()) == 1
        assert reconcile_lease_expiration(rep, model).abs().max() == pytest.approx(
            0.0, abs=1e-6)

    def test_reconcile_catches_mislabeled_provenance(self, freeport):
        """Mislabeling a Contractual expiration as Speculative is caught by
        the per-(year, provenance) reconcile — the label is verified, not
        assumed (DEVIATIONS §25 discrimination)."""
        model, res = freeport
        report = lease_expiration(res)
        idx = report.frame.index[report.frame["status"] == "Contractual"][0]
        report.frame.loc[idx, "status"] = "Speculative"
        diffs = reconcile_lease_expiration(report, model)
        assert diffs["max_key_sf_diff"] > 0.0 or diffs["max_key_count_diff"] > 0.0

    def test_contractual_only_selectable(self, freeport):
        """Contractual-only stays selectable — 28 contract + 1 MTM = 29,
        no Speculative rows, still reconciles."""
        model, res = freeport
        rep = lease_expiration(res, statuses=CONTRACTUAL_STATUSES)
        assert int(rep.frame["expiring_leases"].sum()) == 29
        assert set(rep.frame["status"]) == {"Contractual"}
        assert reconcile_lease_expiration(
            rep, model, statuses=CONTRACTUAL_STATUSES).abs().max() == (
            pytest.approx(0.0, abs=1e-6))

    def test_summary_distinct_demised_dedupes_suite_100(self, freeport):
        """Suite 100 is two sequential contract leases (OKI + OKI Renewal);
        distinct demised area counts it once and stays UNDER the building —
        never the double-counted 128,087 the old total_area reported.
        (Contract-only isolates the suite-100 dedup.)"""
        _model, res = freeport
        report = lease_summary(res, statuses=(LeaseStatus.contract,))
        demised = report.meta.extra["distinct_demised_area"]
        assert demised == pytest.approx(122_870.0)         # deduped
        assert demised < float(res.rentable_area.iloc[0])  # 123,099; honest

    @pytest.mark.parametrize("fye", [3, 6, 9, 12])
    def test_turnover_over_100pct_but_sanity_bound_holds(self, freeport, fye):
        """Cumulative expiring SF exceeds the building (legitimate turnover:
        suite 100 expires twice over the term), yet no SINGLE fiscal year
        exceeds rentable — the sanity bound holds across every FYE
        convention (worst single year is 28.9% at FYE=6, 39.9% at FYE=9;
        DEVIATIONS §25 — conventions named, never a bare number)."""
        _model, res = freeport
        rep = lease_expiration(res, fiscal_year_end_month=fye)
        # cumulative >100% of the building over the term is legitimate
        assert rep.frame["expiring_sf"].sum() > float(res.rentable_area.iloc[0])
        # ...but no single year does — the sanity bound never raises
        assert_expiration_within_building(rep, res)
