"""Unit tests for the Phase 4 Step 2 reports: Cash Flow (#1) and Benchmark
Comparison (#24) — engine/reports/cash_flow.py, engine/reports/benchmark.py.

Cash Flow is a pure view of ``ledger.frame`` (spec §7 report 1;
[AE pp. 535-539]) — its acceptance is exact reconciliation to the ledger
across every period and the identity of the Total-$ view (never input
tuning). Benchmark Comparison (spec §7 report 24; §9.1) diffs the fiscal
cash flow against a published-CSV transcription at $500/line; its mechanics
are tested here on a synthetic frame, and the four goldens exercise it for
real in tests/golden/ (reproducing the by-design red counts exactly).
"""
import datetime as dt

import numpy as np
import pandas as pd
import pytest

from engine.calc.ledger import (
    CFBDS,
    EGR,
    NOI,
    SCHEDULED_BASE_RENTAL_REVENUE,
    TOTAL_OPERATING_EXPENSES,
    to_fiscal_annual,
)
from engine.calc.run import run_property
from engine.reports import (
    Period,
    Report,
    Unit,
    benchmark_comparison,
    cash_flow,
    load_expected_cash_flow,
    miss_lines,
    reconcile_cash_flow,
)
from engine.reports.cash_flow import SUBTOTAL_ACCOUNTS
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


@pytest.fixture(scope="module")
def result():
    """Multi-tenant property with rollover downtime and absorption — every
    Cash Flow section is populated and occupied area varies month to month."""
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
        market_leasing_profile="Market", upon_expiration=UponExpiration.market,
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
            property_size=RENTABLE, rentable_area_mode=RentableAreaMode.fixed,
            rentable_area_fixed=RENTABLE),
        inflation=Inflation(general_rate=[YearRate(year=1, rate=0.0)],
                            timing_basis=TimingBasis.analysis_year),
        market_leasing_profiles=[profile],
        expenses=[ExpenseItem(name="CAM", amount=420_000,
                              unit=ExpenseUnit.dollars_per_year)],
        rent_roll=[anchor, roller], absorption=[absorption],
    )
    return run_property(model)


class TestCashFlowReconciliation:
    """A pure view of the ledger reconciles to it exactly, every period."""

    @pytest.mark.parametrize("period", list(Period))
    def test_reconciles_to_ledger_exactly(self, result, period):
        report = cash_flow(result, period=period, fiscal_year_end_month=FYE,
                           analysis_begin=BEGIN)
        diff = reconcile_cash_flow(report, result, fiscal_year_end_month=FYE,
                                   analysis_begin=BEGIN)
        assert diff.abs().to_numpy().max() == pytest.approx(0.0, abs=1e-9)

    def test_returns_report_unpackable(self, result):
        report = cash_flow(result, period=Period.annual, analysis_begin=BEGIN)
        assert isinstance(report, Report)
        frame, meta = report
        assert meta.name == "Cash Flow" and meta.number == 1
        assert meta.citation == "[AE pp. 535-539]"

    def test_accounts_are_rows_in_ledger_order(self, result):
        report = cash_flow(result, period=Period.fiscal, fiscal_year_end_month=FYE,
                           analysis_begin=BEGIN)
        assert list(report.frame.index) == list(result.ledger.frame.columns)
        assert report.frame.index.name == "account"

    def test_subtotals_equal_their_components(self, result):
        """The report carries the ledger's own rollups — e.g. NOI = EGR +
        Total Operating Expenses [AE p. 539] — cell for cell."""
        report = cash_flow(result, period=Period.annual, analysis_begin=BEGIN)
        f = report.frame
        assert np.allclose(f.loc[NOI].to_numpy(float),
                           (f.loc[EGR] + f.loc[TOTAL_OPERATING_EXPENSES])
                           .to_numpy(float), atol=1e-6)


class TestCashFlowTreeMetadata:
    def test_tree_flags_subtotals_and_indents_detail(self, result):
        report = cash_flow(result, period=Period.fiscal, analysis_begin=BEGIN)
        tree = {row["account"]: row for row in report.meta.extra["tree"]}
        assert tree[SCHEDULED_BASE_RENTAL_REVENUE]["is_subtotal"] is True
        assert tree[SCHEDULED_BASE_RENTAL_REVENUE]["level"] == 0
        assert tree["Base Rental Revenue"]["is_subtotal"] is False
        assert tree["Base Rental Revenue"]["level"] == 1
        # every subtotal constant is flagged
        for name in SUBTOTAL_ACCOUNTS:
            assert tree[name]["is_subtotal"] is True

    def test_operating_expense_detail_tagged_by_section(self, result):
        report = cash_flow(result, period=Period.annual, analysis_begin=BEGIN)
        tree = {row["account"]: row for row in report.meta.extra["tree"]}
        assert tree["CAM"]["section"] == "operating_expense"


class TestCashFlowUnits:
    def test_per_sf_is_total_over_rentable(self, result):
        total = cash_flow(result, period=Period.fiscal, unit=Unit.total,
                          fiscal_year_end_month=FYE, analysis_begin=BEGIN)
        psf = cash_flow(result, period=Period.fiscal, unit=Unit.per_sf,
                        fiscal_year_end_month=FYE, analysis_begin=BEGIN)
        # rentable is fixed at 350k → per-SF is exactly total / 350k
        expected = total.frame.loc[NOI] / RENTABLE
        pd.testing.assert_series_equal(psf.frame.loc[NOI], expected,
                                       check_names=False)

    def test_reconcile_rejects_non_total_unit(self, result):
        psf = cash_flow(result, period=Period.fiscal, unit=Unit.per_sf,
                        analysis_begin=BEGIN)
        with pytest.raises(ValueError, match="Total"):
            reconcile_cash_flow(psf, result, analysis_begin=BEGIN)


class TestCashFlowDefaultBegin:
    def test_analysis_begin_derived_from_months(self, result):
        # omitting analysis_begin must reproduce the explicit-begin report
        derived = cash_flow(result, period=Period.fiscal, fiscal_year_end_month=FYE)
        explicit = cash_flow(result, period=Period.fiscal,
                             fiscal_year_end_month=FYE, analysis_begin=BEGIN)
        pd.testing.assert_frame_equal(derived.frame, explicit.frame)


# ------------------------------------------------------------------ #
# Benchmark Comparison (#24) mechanics                                #
# ------------------------------------------------------------------ #

class TestBenchmarkMechanics:
    def _fiscal(self):
        # a tiny 2-year fiscal frame: one line on tolerance, one over
        return pd.DataFrame(
            {"Net Operating Income": {2027: 1_000_000.0, 2028: 2_000_000.0},
             "Base Rental Revenue": {2027: 500_000.0, 2028: 500_000.0}})

    def test_within_and_beyond_tolerance_flags(self):
        fiscal = self._fiscal()
        expected = {
            "Net Operating Income": {2027: 1_000_400.0, 2028: 2_000_600.0},
            "Base Rental Revenue": {2027: 500_000.0, 2028: 500_000.0},
        }
        report = benchmark_comparison(fiscal, expected, fiscal_years=[2027, 2028])
        f = report.frame
        # 2027 NOI diff -400 within $500; 2028 NOI diff -600 beyond
        noi = f[f["account"] == "Net Operating Income"].set_index("fiscal_year")
        assert bool(noi.loc[2027, "within_tolerance"]) is True
        assert bool(noi.loc[2028, "within_tolerance"]) is False
        assert report.meta.extra["miss_count"] == 1
        assert report.meta.extra["line_years"] == 4

    def test_account_to_column_mapping(self):
        fiscal = pd.DataFrame({"Capital Reserves": {2027: -50_000.0}})
        expected = {"Capital Expenses": {2027: -50_000.0}}
        report = benchmark_comparison(
            fiscal, expected, fiscal_years=[2027],
            account_to_column={"Capital Expenses": "Capital Reserves"})
        assert report.meta.extra["miss_count"] == 0
        assert report.frame.loc[0, "column"] == "Capital Reserves"

    def test_skip_accounts_excluded(self):
        fiscal = self._fiscal()
        expected = {"Net Operating Income": {2027: 9.9e9, 2028: 9.9e9},
                    "Base Rental Revenue": {2027: 500_000.0, 2028: 500_000.0}}
        report = benchmark_comparison(
            fiscal, expected, fiscal_years=[2027, 2028],
            skip_accounts={"Net Operating Income"})
        assert set(report.frame["account"]) == {"Base Rental Revenue"}
        assert report.meta.extra["miss_count"] == 0

    def test_missing_ledger_column_raises(self):
        fiscal = pd.DataFrame({"Net Operating Income": {2027: 1.0}})
        with pytest.raises(ValueError, match="missing line"):
            benchmark_comparison(fiscal, {"Ghost Line": {2027: 1.0}},
                                 fiscal_years=[2027])

    def test_miss_lines_formatting(self):
        fiscal = self._fiscal()
        expected = {"Net Operating Income": {2027: 1_000_000.0, 2028: 2_000_600.0},
                    "Base Rental Revenue": {2027: 500_000.0, 2028: 500_000.0}}
        report = benchmark_comparison(fiscal, expected, fiscal_years=[2027, 2028])
        lines = miss_lines(report)
        assert lines == [
            "  Net Operating Income FY2028: engine 2,000,000 vs "
            "OM 2,000,600 (diff -600)"]


class TestBenchmarkOnGoldens:
    """The four goldens reproduce their exact by-design miss counts through
    the reusable builder (the same numbers tests/golden/ asserts)."""

    from pathlib import Path as _P
    GOLDEN = _P(__file__).resolve().parents[1] / "golden"
    GATE3 = {"Tenant Improvements", "Leasing Commissions",
             "Capital Expenditures", "Capital Reserves", "Total Capital Costs",
             "Cash Flow Before Debt Service"}

    def _counts(self, fixture, fye, years, account_to_column=None):
        from engine.models.io import load_property
        model = load_property(self.GOLDEN / fixture /
                              f"{fixture}.icprop.json")
        fiscal = to_fiscal_annual(run_property(model).ledger.frame,
                                  fiscal_year_end_month=fye)
        expected = load_expected_cash_flow(
            self.GOLDEN / fixture / "expected_annual_cash_flow.csv", years)
        gate2 = benchmark_comparison(
            fiscal, expected, fiscal_years=years, skip_accounts=self.GATE3,
            account_to_column=account_to_column)
        gate3 = benchmark_comparison(
            fiscal, expected, fiscal_years=years,
            skip_accounts=set(expected) - self.GATE3,
            account_to_column=account_to_column)
        return (gate2.meta.extra["miss_count"], gate3.meta.extra["miss_count"])

    def test_clorox_gate1_green(self):
        g2, _ = self._counts("clorox_northlake", 5, [2027, 2028],
                             account_to_column={"Capital Expenses":
                                                "Capital Reserves"})
        assert g2 == 0  # Gate 1 (FY2027-28) reconciles line-for-line

    def test_freeport_by_design_reds(self):
        assert self._counts("freeport", 6, list(range(2027, 2038))) == (137, 33)

    def test_cedar_alt_by_design_reds(self):
        assert self._counts("cedar_alt", 5, list(range(2027, 2038))) == (47, 12)
