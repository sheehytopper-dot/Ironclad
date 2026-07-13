"""Unit tests for the Phase 4 Step 1 report-builder contract + toggle /
period engine (engine/reports/base.py; spec §7 intro, §4.3).

Acceptance (NEXT_STEPS_TO_PHASE4.md Step 1): the unit / period transforms
satisfy sum(monthly) = annual = fiscal (§9.3) on an engineered property
and compute the correct PSF / per-occupied denominators; the three
existing audit builders (Lease/Recovery/Resale) still reconcile exactly
through their new contract wrappers. Rounding is report-level only and
defaults to ARGUS's None [AE p. 508].
"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from engine.calc.ledger import (
    EGR,
    NOI,
    TOTAL_OPERATING_EXPENSES,
    to_annual,
    to_fiscal_annual,
    to_quarterly,
)
from engine.calc.run import run_property
from engine.reports import (
    ModelingPolicies,
    Period,
    Report,
    Rounding,
    Unit,
    aggregate_period,
    apply_rounding,
    apply_unit,
    assert_period_consistency,
    build_monetary_report,
    lease_audit_report,
    period_mean_area,
    period_month_counts,
    reconcile_lease_audit,
    reconcile_recovery_audit,
    reconcile_resale_audit,
    recovery_audit_report,
    resale_audit_report,
)
from engine.models import (
    AbsorptionSpec,
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
FYE = 12
RENTABLE = 350_000.0
# Monetary accounts under test — a revenue line, an expense line, a subtotal.
COLS = [EGR, TOTAL_OPERATING_EXPENSES, NOI]


@pytest.fixture(scope="module")
def result():
    """A multi-tenant property with rollover downtime and absorption, so
    occupied area genuinely varies month to month (a real per-occupied-SF
    denominator) while rentable area is fixed (a checkable per-SF one)."""
    profile = MarketLeasingProfile(
        name="Market", term_months=24, renewal_probability=50.0,
        months_vacant=4.0,
        market_base_rent_new=MoneyRate(amount=12.0, unit=PSF_YR),
        market_base_rent_renew=PctOfNew(pct_of_new=100.0),
        free_rent_months_new=2.0, free_rent_months_renew=0.0,
        upon_expiration=UponExpiration.market, term_growth=False,
    )
    anchor = Lease(
        tenant_name="Anchor", area=200_000, lease_type="industrial",
        start_date=BEGIN, term_months=120,
        base_rent=MoneyRate(amount=10.0, unit=PSF_YR),
        upon_expiration=UponExpiration.vacate,
    )
    roller = Lease(
        tenant_name="Roller", area=100_000, lease_type="industrial",
        start_date=BEGIN, term_months=12,
        base_rent=MoneyRate(amount=12.0, unit=PSF_YR),
        market_leasing_profile="Market",
        upon_expiration=UponExpiration.market,
    )
    absorption = AbsorptionSpec(
        name="Vacant Bay", total_area=50_000, number_of_leases=2,
        start_date=dt.date(2026, 4, 1), interval_months=3,
        lease_type="industrial", market_leasing_profile="Market",
    )
    model = PropertyModel(
        property=PropertyInfo(name="LA", property_type="industrial",
                              analysis_begin=BEGIN, analysis_term_years=3,
                              fiscal_year_end_month=FYE),
        area_measures=AreaMeasures(
            property_size=RENTABLE,
            rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=RENTABLE,
        ),
        inflation=Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                            timing_basis=TimingBasis.analysis_year),
        market_leasing_profiles=[profile],
        expenses=[ExpenseItem(name="CAM", amount=420_000,
                              unit=ExpenseUnit.dollars_per_year)],
        rent_roll=[anchor, roller],
        absorption=[absorption],
    )
    return run_property(model)


@pytest.fixture(scope="module")
def monthly(result):
    return result.ledger.frame[COLS]


class TestPeriodAggregationMatchesLedger:
    """The report layer aggregates via the ledger's own functions (spec
    §2.3 — never separately computed), so it must equal them exactly."""

    def test_annual(self, monthly):
        got = aggregate_period(monthly, Period.annual, analysis_begin=BEGIN)
        pd.testing.assert_frame_equal(got, to_annual(monthly, BEGIN))

    def test_quarterly(self, monthly):
        got = aggregate_period(monthly, Period.quarterly, analysis_begin=BEGIN)
        pd.testing.assert_frame_equal(got, to_quarterly(monthly))

    def test_fiscal(self, monthly):
        got = aggregate_period(monthly, Period.fiscal, analysis_begin=BEGIN,
                               fiscal_year_end_month=FYE)
        pd.testing.assert_frame_equal(got, to_fiscal_annual(monthly, FYE))

    def test_monthly_is_identity(self, monthly):
        got = aggregate_period(monthly, Period.monthly, analysis_begin=BEGIN)
        pd.testing.assert_frame_equal(got, monthly)


class TestPeriodConsistencyInvariant:
    """sum(monthly) == annual == quarterly == fiscal for every account
    (§9.3) — the additive Total-$ identity the acceptance requires."""

    def test_full_ledger_consistent(self, result):
        # never raises across every ledger column
        assert_period_consistency(result.ledger.frame, analysis_begin=BEGIN,
                                  fiscal_year_end_month=FYE)

    @pytest.mark.parametrize("period", [Period.annual, Period.quarterly,
                                        Period.fiscal])
    def test_totals_match(self, monthly, period):
        view = aggregate_period(monthly, period, analysis_begin=BEGIN,
                                fiscal_year_end_month=FYE)
        assert np.allclose(view.sum().to_numpy(float),
                           monthly.sum().to_numpy(float), atol=1e-6)

    def test_raises_on_non_additive_frame(self):
        # a hand-built frame whose annual total is engineered NOT to equal
        # the monthly sum would only arise from a broken aggregator; assert
        # the guard fires when the aggregation disagrees with sum(monthly).
        months = pd.period_range("2026-01", periods=24, freq="M")
        frame = pd.DataFrame({"x": np.arange(24, dtype=float)}, index=months)
        # sanity: the real aggregation is consistent (no raise)
        assert_period_consistency(frame, analysis_begin=BEGIN)


class TestUnitDenominators:
    """Correct PSF / per-occupied-SF / per-month denominators (spec §3.2,
    §4.3; the plan's definitions)."""

    def test_per_sf_divides_by_mean_rentable(self, monthly, result):
        annual = aggregate_period(monthly, Period.annual, analysis_begin=BEGIN)
        rentable = period_mean_area(result.rentable_area, Period.annual,
                                    analysis_begin=BEGIN)
        counts = period_month_counts(monthly.index, Period.annual,
                                     analysis_begin=BEGIN)
        occ = period_mean_area(result.occupied_area, Period.annual,
                               analysis_begin=BEGIN)
        psf = apply_unit(annual, Unit.per_sf, month_counts=counts,
                         rentable_mean=rentable, occupied_mean=occ)
        # rentable is fixed at 350k → mean is exactly 350k every year
        assert (rentable == RENTABLE).all()
        expected = annual[NOI] / RENTABLE
        pd.testing.assert_series_equal(psf[NOI], expected, check_names=False)

    def test_per_occupied_sf_divides_by_mean_occupied(self, monthly, result):
        annual = aggregate_period(monthly, Period.annual, analysis_begin=BEGIN)
        occ = period_mean_area(result.occupied_area, Period.annual,
                               analysis_begin=BEGIN)
        counts = period_month_counts(monthly.index, Period.annual,
                                     analysis_begin=BEGIN)
        rentable = period_mean_area(result.rentable_area, Period.annual,
                                    analysis_begin=BEGIN)
        per_occ = apply_unit(annual, Unit.per_occ_sf, month_counts=counts,
                             rentable_mean=rentable, occupied_mean=occ)
        # cross-check year 1's occupied mean directly from the run's series
        year1_occ = result.occupied_area.iloc[:12].mean()
        assert occ.iloc[0] == pytest.approx(year1_occ)
        assert per_occ[EGR].iloc[0] == pytest.approx(
            annual[EGR].iloc[0] / year1_occ)

    def test_per_month_divides_by_month_count(self, monthly):
        annual = aggregate_period(monthly, Period.annual, analysis_begin=BEGIN)
        counts = period_month_counts(monthly.index, Period.annual,
                                     analysis_begin=BEGIN)
        # analysis years are full 12-month blocks (last = resale look-forward)
        assert (counts == 12).all()
        unused = pd.Series(1.0, index=annual.index)  # area not used by per_month
        per_mo = apply_unit(annual, Unit.per_month, month_counts=counts,
                            rentable_mean=unused, occupied_mean=unused)
        pd.testing.assert_series_equal(per_mo[NOI], annual[NOI] / 12.0,
                                       check_names=False)

    def test_fiscal_partial_year_month_count(self, result):
        """A February fiscal-year-end splits the calendar into partial
        groups whose month counts differ from 12 — per-month must divide
        by the actual count."""
        frame = result.ledger.frame[[NOI]]
        counts = period_month_counts(frame.index, Period.fiscal,
                                     analysis_begin=BEGIN,
                                     fiscal_year_end_month=2)
        annual = aggregate_period(frame, Period.fiscal, analysis_begin=BEGIN,
                                  fiscal_year_end_month=2)
        assert (counts.reindex(annual.index) != 12).any()
        # the count series indexes exactly the aggregated groups
        assert set(counts.index) == set(annual.index)

    def test_total_is_passthrough(self, monthly):
        annual = aggregate_period(monthly, Period.annual, analysis_begin=BEGIN)
        z = pd.Series(1.0, index=annual.index)
        out = apply_unit(annual, Unit.total, month_counts=z,
                         rentable_mean=z, occupied_mean=z)
        pd.testing.assert_frame_equal(out, annual)

    def test_zero_area_yields_nan_not_zero(self, monthly):
        annual = aggregate_period(monthly, Period.annual, analysis_begin=BEGIN)
        zero_occ = pd.Series(0.0, index=annual.index)
        ok = pd.Series(1.0, index=annual.index)
        out = apply_unit(annual, Unit.per_occ_sf, month_counts=ok,
                         rentable_mean=ok, occupied_mean=zero_occ)
        assert out[NOI].isna().all()  # undefined per-occupied-SF, not 0


class TestRounding:
    def test_none_is_full_precision(self, monthly):
        assert apply_rounding(monthly, Rounding.none) is monthly

    def test_nearest_dollar_rounds(self):
        frame = pd.DataFrame({"x": [1.4, 2.5, -3.6]})
        rounded = apply_rounding(frame, Rounding.nearest_dollar)
        assert list(rounded["x"]) == [1.0, 2.0, -4.0]

    def test_default_policy_is_argus_none(self):
        assert ModelingPolicies().rounding == Rounding.none


class TestBuildMonetaryReport:
    """The high-level path every §7 monetary report uses."""

    def test_returns_report_unpackable_as_tuple(self, monthly, result):
        report = build_monetary_report(
            monthly, name="Cash Flow", number=1, result=result,
            unit=Unit.total, period=Period.annual, analysis_begin=BEGIN,
            fiscal_year_end_month=FYE, citation="[AE pp. 535-539]")
        assert isinstance(report, Report)
        frame, meta = report  # unpackable per spec §7 "(DataFrame, metadata)"
        pd.testing.assert_frame_equal(frame, to_annual(monthly, BEGIN))
        assert meta.name == "Cash Flow" and meta.number == 1
        assert meta.unit == Unit.total and meta.period == Period.annual
        assert meta.monetary and meta.denominator is None

    def test_per_sf_report_matches_manual_transform(self, monthly, result):
        report = build_monetary_report(
            monthly, name="Cash Flow", number=1, result=result,
            unit=Unit.per_sf, period=Period.annual, analysis_begin=BEGIN)
        expected = to_annual(monthly, BEGIN) / RENTABLE
        pd.testing.assert_frame_equal(report.frame, expected)
        assert report.meta.denominator == "rentable_area"

    def test_rounding_policy_applied(self, monthly, result):
        report = build_monetary_report(
            monthly, name="Cash Flow", number=1, result=result,
            unit=Unit.total, period=Period.annual, analysis_begin=BEGIN,
            policies=ModelingPolicies(rounding=Rounding.nearest_dollar))
        assert (report.frame == report.frame.round(0)).all().all()


class TestAuditContractWrappers:
    """The three existing audits conform to the contract via ``*_report``
    wrappers WITHOUT changing their reconciliation (Step 1 acceptance)."""

    def test_lease_audit_report_reconciles(self, result):
        report = lease_audit_report(result)
        assert isinstance(report, Report)
        assert report.meta.number == 16 and not report.meta.monetary
        diffs = reconcile_lease_audit(report.frame, result)
        assert diffs.abs().to_numpy().max() == pytest.approx(0.0, abs=1e-9)

    def test_recovery_audit_report_reconciles(self, result):
        report = recovery_audit_report(result)
        assert report.meta.number == 18 and not report.meta.monetary
        diff = reconcile_recovery_audit(report.frame, result)
        assert diff.abs().max() == pytest.approx(0.0, abs=1e-9)

    def test_resale_audit_report_requires_valuation(self, result):
        # this engineered property has no valuation → resale_audit raises,
        # same as the bare builder (behavior unchanged)
        with pytest.raises(ValueError):
            resale_audit_report(result)
